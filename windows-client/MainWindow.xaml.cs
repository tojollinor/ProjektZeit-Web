using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;

namespace ProjektZeit;
public partial class MainWindow : Window
{
    record Settings(string Server, string User, string Pbx, string Token);
    readonly HttpClient http = new(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(30) };
    readonly string file = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ProjektZeit", "session.dat");
    string origin = "", token = "";
    CancellationTokenSource? pending;
    Window? loginWindow;
    readonly System.Windows.Threading.DispatcherTimer heartbeat = new() { Interval = TimeSpan.FromSeconds(30) };
    bool busy, checking, initialized;
    public MainWindow()
    {
        InitializeComponent();
        Loaded += (_, _) => {
          if(initialized)return; initialized=true;
          try { if (File.Exists(file)) {
            var data = JsonSerializer.Deserialize<Settings>(ProtectedData.Unprotect(File.ReadAllBytes(file), null, DataProtectionScope.CurrentUser))!;
            origin = Normalize(data.Server); token = data.Token;
            Server.Text = origin; User.Text = data.User; Pbx.Text = data.Pbx;
          }} catch { Status.Text="Gespeicherte Sitzung konnte nicht geladen werden."; }
          Controls.Children.Remove(LoginPanel);
          Hide(); ShowLogin();
        };
        heartbeat.Tick += async (_, _) => {
            if (busy || checking || token=="") return;
            checking=true;
            try { await Api("/api/v1/me"); State(WebState,"Verbunden",true); }
            catch { State(WebState,"Nicht verbunden",false); }
            finally {checking=false;}
        };
        Closed += (_, _) => { heartbeat.Stop(); pending?.Cancel(); http.Dispose(); };
    }
    void ShowLogin()
    {
        heartbeat.Stop();
        loginWindow=new Window {Title="Mit ProjektZeit verbinden",Width=460,Height=440,ResizeMode=ResizeMode.NoResize,Background=new SolidColorBrush(Color.FromRgb(16,23,34)),Content=LoginPanel,WindowStartupLocation=WindowStartupLocation.CenterScreen};
        LoginPanel.Margin=new Thickness(24);
        LoginStatus.Text="Bitte anmelden. Beispieladresse oben dient nur als Hinweis.";
        bool? success=loginWindow.ShowDialog();
        loginWindow.Content=null;loginWindow=null;
        if(success==true){Show();Height=570;heartbeat.Start();}else Close();
    }
    static string Normalize(string input)
    {
        input = input.Trim().TrimEnd('/');
        if (!input.Contains("://")) input = "https://" + input;
        if (!Uri.TryCreate(input, UriKind.Absolute, out var u) || u.Scheme != "https" || string.IsNullOrEmpty(u.Host) || u.UserInfo != "" || u.Query != "" || u.Fragment != "" || (u.AbsolutePath != "/" && u.AbsolutePath != "/rest") || input.Any(char.IsWhiteSpace) || input.Contains('\\'))
            throw new Exception("Bitte eine gültige HTTPS-Domain ohne Anmeldepfad eingeben.");
        return u.GetLeftPart(UriPartial.Authority);
    }
    void State(System.Windows.Controls.TextBlock label, string message, bool ok)
    { label.Text = "● " + message; label.Foreground = new SolidColorBrush(ok ? Color.FromRgb(52,211,153) : Color.FromRgb(253,186,116)); }
    async Task<JsonElement> Api(string path, object? body = null)
    {
        if (origin == "") throw new Exception("Bitte zuerst am ProjektZeit-Webserver anmelden.");
        using var request = new HttpRequestMessage(body == null ? HttpMethod.Get : HttpMethod.Post, origin + path);
        if (token != "") request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        if (body != null) request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request);
        if (response.StatusCode == HttpStatusCode.Unauthorized) { token = ""; Save(); State(WebState,"Nicht verbunden – Sitzung abgelaufen",false); State(PbxState,"Nicht geprüft",false); }
        var text = await response.Content.ReadAsStringAsync();
        JsonElement result;
        try { result = JsonSerializer.Deserialize<JsonElement>(text); }
        catch { throw new Exception($"Server lieferte keine API-Antwort (HTTP {(int)response.StatusCode}). Adresse und Serverversion prüfen."); }
        if (!response.IsSuccessStatusCode) throw new Exception(result.TryGetProperty("error",out var error) ? error.GetString() : $"HTTP {(int)response.StatusCode}");
        return result;
    }
    void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new Settings(origin,User.Text,Pbx.Text,token));
        File.WriteAllBytes(file, ProtectedData.Protect(bytes,null,DataProtectionScope.CurrentUser));
    }
    async Task Run(Func<Task> action)
    {
        busy=true; Controls.IsEnabled = false; LoginPanel.IsEnabled=false;
        try { await action(); }
        catch (OperationCanceledException) { Status.Text = "Vorgang abgebrochen oder Zeitlimit erreicht."; }
        catch (HttpRequestException) { Status.Text = "Server nicht erreichbar oder TLS-Verbindung fehlgeschlagen."; State(WebState,"Nicht erreichbar",false); }
        catch (Exception e) { Status.Text = e.Message; }
        finally { Controls.IsEnabled = true; LoginPanel.IsEnabled=true; LoginStatus.Text=Status.Text; busy=false; }
    }
    async void Login(object sender, RoutedEventArgs e) => await Run(async () => {
        var address = Normalize(Server.Text); var password = Password.Password; Password.Clear();
        if (token != "") { try { await Api("/api/v1/auth/revoke",new {}); } catch { } }
        origin = address; token = ""; State(WebState,"Nicht verbunden",false); State(PbxState,"Nicht geprüft",false);
        Status.Text = "Anmeldung am ProjektZeit-Webserver …";
        var result = await Api("/api/v1/auth/token",new {username=User.Text,password,client_name="ProjektZeit WPF"});
        token = result.GetProperty("access_token").GetString()!;
        Save(); State(WebState,"Verbunden",true); Status.Text = "ProjektZeit-Anmeldung erfolgreich. Sitzung sicher gespeichert.";
        if(loginWindow!=null)loginWindow.DialogResult=true;
    });
    async Task Verify()
    {
        State(WebState,"Wird geprüft …",false); State(PbxState,"Nicht geprüft",false);
        await Api("/api/v1/me"); State(WebState,"Verbunden",true);
        var list = await Api("/api/v1/integrations");
        var items = list.GetProperty("integrations");
        var sf = items.EnumerateArray().First(x=>x.GetProperty("provider").GetString()=="starface");
        if (!sf.GetProperty("has_secret").GetBoolean()) { State(PbxState,"Nicht verbunden",false); return; }
        var domain = sf.GetProperty("domain").GetString()!;
        Pbx.Text = domain;
        var probe = await Api("/api/v1/integrations/test",new {provider="starface",domain,username="",secret=""});
        bool ok = probe.GetProperty("ok").GetBoolean();
        State(PbxState,ok ? "Verbunden" : "Nicht verbunden – Prüfung fehlgeschlagen",ok);
        Save();
    }
    async void Check(object s,RoutedEventArgs e) => await Run(async ()=> { await Verify(); Status.Text="Verbindungsprüfung abgeschlossen."; });
    async void Logout(object s,RoutedEventArgs e) => await Run(async ()=> {
        if(token!="") await Api("/api/v1/auth/revoke",new {});
        token=""; Save(); State(WebState,"Nicht verbunden",false); State(PbxState,"Nicht geprüft – serverseitige Verknüpfung bleibt erhalten",false); Status.Text="Abgemeldet.";
        Dispatcher.BeginInvoke(new Action(()=>{Hide();ShowLogin();}));
    });
    static void Browser(string url)
    {
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute=true }); }
        catch { throw new Exception("Windows konnte den Standardbrowser nicht öffnen. Bitte einen Standardbrowser in den Windows-Einstellungen festlegen."); }
    }
    void OpenWeb(object s,RoutedEventArgs e) { try { Browser(Normalize(Server.Text)); } catch(Exception ex) { Status.Text=ex.Message; } }
    async void Begin(object s,RoutedEventArgs e) => await Run(async ()=> {await Api("/api/v1/work/begin",new {}); Status.Text="Arbeitsbeginn gespeichert.";});
    async void End(object s,RoutedEventArgs e) => await Run(async ()=> {await Api("/api/v1/work/end",new {}); Status.Text="Arbeitsende gespeichert.";});
    void CancelLogin(object s,RoutedEventArgs e) => pending?.Cancel();
    async void Connect(object s,RoutedEventArgs e) => await Run(async ()=> {
        if(token=="") throw new Exception("Bitte zuerst am ProjektZeit-Webserver anmelden.");
        var domain=Normalize(Pbx.Text); Pbx.Text=domain; State(PbxState,"Anmeldung läuft …",false);
        pending=new CancellationTokenSource(TimeSpan.FromMinutes(5)); Cancel.Visibility=Visibility.Visible;
        var listener=new TcpListener(IPAddress.Loopback,0);
        try {
            listener.Start(); var port=((IPEndPoint)listener.LocalEndpoint).Port;
            Status.Text="Anmeldeadresse wird vom Webserver angefordert …";
            var start=await Api("/api/v1/integrations/starface/start",new {domain,redirect_uri=$"http://127.0.0.1:{port}"});
            var url=start.GetProperty("url").GetString()!;
            var auth=new Uri(url); if(auth.Scheme!="https" || auth.UserInfo!="") throw new Exception("Ungültige Browseradresse vom Server.");
            var expected=Query(auth.Query)["state"];
            Browser(url); Status.Text="Browser geöffnet. Bitte dort anmelden. Warte auf Rückmeldung …";
            while(true) {
                using var connection=await listener.AcceptTcpClientAsync(pending.Token);
                using var timeout=CancellationTokenSource.CreateLinkedTokenSource(pending.Token); timeout.CancelAfter(TimeSpan.FromSeconds(5));
                using var stream=connection.GetStream();
                var buffer=new byte[1]; var bytes=new List<byte>();
                try { while(bytes.Count<16000) { if(await stream.ReadAsync(buffer,timeout.Token)==0) break; bytes.Add(buffer[0]); if(bytes.Count>=4 && Encoding.ASCII.GetString(bytes.TakeLast(4).ToArray())=="\r\n\r\n") break; } }
                catch(OperationCanceledException) { pending.Token.ThrowIfCancellationRequested(); continue; }
                var line=Encoding.ASCII.GetString(bytes.ToArray()).Split('\n')[0].Trim().Split(' ');
                Dictionary<string,string>? data=null;
                try { if(line.Length==3 && line[0]=="GET" && line[1].StartsWith("/?")) { var q=Query(new Uri("http://127.0.0.1"+line[1]).Query); if(q.GetValueOrDefault("state")==expected && (q.ContainsKey("code") || q.ContainsKey("error"))) data=q; } } catch { }
                var reply=Encoding.UTF8.GetBytes(data==null?"Ungültige Rückleitung.":"Anmeldung empfangen. Bitte Erfolg im ProjektZeit-Client abwarten.");
                var header=Encoding.ASCII.GetBytes($"HTTP/1.1 {(data==null?"400 Bad Request":"200 OK")}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {reply.Length}\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n\r\n");
                await stream.WriteAsync(header,pending.Token); await stream.WriteAsync(reply,pending.Token);
                if(data==null) continue;
                Status.Text="Anmeldung wird auf dem Webserver abgeschlossen …";
                await Api("/api/v1/integrations/starface/finish",data);
                State(PbxState,"Verbunden",true); Save(); Status.Text="STARFACE-Anmeldung erfolgreich vom Webserver bestätigt und gespeichert.";
                break;
            }
        } finally {listener.Stop(); pending.Dispose(); pending=null; Cancel.Visibility=Visibility.Collapsed;}
    });
    static Dictionary<string,string> Query(string query) => query.TrimStart('?').Split('&',StringSplitOptions.RemoveEmptyEntries).Select(x=>x.Split('=',2)).ToDictionary(x=>Uri.UnescapeDataString(x[0]),x=>x.Length==2?Uri.UnescapeDataString(x[1].Replace("+"," ")):"");
}
