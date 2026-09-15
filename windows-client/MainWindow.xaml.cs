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
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;

namespace ProjektZeit;

public partial class MainWindow : Window
{
    sealed record StoredSettings(string Server, string Token, string Pbx);
    sealed record Choice(long Id, string Name, long? CustomerId = null);
    sealed class SessionExpiredException : Exception
    {
        public SessionExpiredException() : base("Die Sitzung ist abgelaufen. Bitte erneut anmelden.") { }
    }

    const string ClientId = "projektzeit-windows";
    readonly HttpClient http = new(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(35) };
    readonly string settingsFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ProjektZeit", "session.dat");
    readonly string? launchUri;
    readonly DispatcherTimer heartbeat = new() { Interval = TimeSpan.FromSeconds(30) };
    readonly DispatcherTimer clock = new() { Interval = TimeSpan.FromSeconds(1) };
    readonly List<Choice> projects = [];

    string origin = "";
    string token = "";
    string pbx = "";
    string workState = "stopped";
    string activeProject = "";
    DateTimeOffset? workStarted;
    DateTimeOffset? pauseStarted;
    DateTimeOffset? projectStarted;
    CancellationTokenSource? pending;
    bool initialized;
    bool busy;

    public MainWindow() : this(null) { }

    public MainWindow(string? launchUri)
    {
        this.launchUri = launchUri;
        InitializeComponent();
        Loaded += async (_, _) => await InitializeAsync();
        heartbeat.Tick += async (_, _) => { if (!busy && token.Length > 0) await RefreshQuietly(); };
        clock.Tick += (_, _) => UpdateClock();
        Closed += (_, _) => { heartbeat.Stop(); clock.Stop(); pending?.Cancel(); pending?.Dispose(); http.Dispose(); };
    }

    async Task InitializeAsync()
    {
        if (initialized) return;
        initialized = true;
        var loginMessage = LoadSettings();
        AppShell.Visibility = Visibility.Collapsed;
        LoginShell.Visibility = Visibility.Collapsed;

        try
        {
            if (launchUri is not null)
            {
                var link = ParseLaunchUri(launchUri);
                if (!string.Equals(origin, link.Server, StringComparison.OrdinalIgnoreCase)) token = "";
                origin = link.Server;
                ServerInput.Text = origin;
                if (token.Length == 0 || !await SessionIsValid())
                {
                    ShowLogin();
                    LoginCancelButton.Visibility = Visibility.Visible;
                    await AuthenticateAsync(origin);
                }
                ShowApp();
                await RefreshAll();
                await ConnectStarfaceCore(link.Request, link.Server);
                return;
            }

            if (token.Length > 0 && origin.Length > 0 && await SessionIsValid())
            {
                ShowApp();
                await RefreshAll();
                return;
            }
        }
        catch (Exception error)
        {
            loginMessage = error.Message;
        }

        token = "";
        SaveSettings();
        ShowLogin(loginMessage);
    }

    string? LoadSettings()
    {
        try
        {
            if (!File.Exists(settingsFile)) return null;
            var clear = ProtectedData.Unprotect(File.ReadAllBytes(settingsFile), null, DataProtectionScope.CurrentUser);
            var saved = JsonSerializer.Deserialize<StoredSettings>(clear);
            if (saved is null) return null;
            origin = saved.Server ?? "";
            token = saved.Token ?? "";
            pbx = saved.Pbx ?? "";
            ServerInput.Text = origin;
            return null;
        }
        catch
        {
            token = "";
            return "Die gespeicherte Sitzung war nicht lesbar. Bitte erneut anmelden.";
        }
    }

    void SaveSettings()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(settingsFile)!);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new StoredSettings(origin, token, pbx));
        File.WriteAllBytes(settingsFile, ProtectedData.Protect(bytes, null, DataProtectionScope.CurrentUser));
    }

    void ShowLogin(string? message = null)
    {
        heartbeat.Stop();
        clock.Stop();
        AppShell.Visibility = Visibility.Collapsed;
        LoginShell.Visibility = Visibility.Visible;
        ServerInput.Text = origin;
        LoginButton.IsEnabled = true;
        ServerInput.IsEnabled = true;
        LoginCancelButton.Visibility = Visibility.Collapsed;
        LoginStatus.Text = message ?? "Noch nicht verbunden.";
        LoginStatus.Foreground = new SolidColorBrush(message is null ? Color.FromRgb(148, 166, 190) : Color.FromRgb(255, 143, 152));
        ServerInput.Focus();
    }

    void ShowApp()
    {
        LoginShell.Visibility = Visibility.Collapsed;
        AppShell.Visibility = Visibility.Visible;
        ServerText.Text = origin;
        SetConnection("Verbunden", true);
        heartbeat.Start();
        clock.Start();
    }

    static string Normalize(string input)
    {
        input = input.Trim().TrimEnd('/');
        if (!input.Contains("://")) input = "https://" + input;
        if (!Uri.TryCreate(input, UriKind.Absolute, out var uri) || uri.Scheme != "https" || string.IsNullOrWhiteSpace(uri.Host) ||
            uri.UserInfo.Length > 0 || uri.Query.Length > 0 || uri.Fragment.Length > 0 || uri.AbsolutePath != "/" || input.Any(char.IsWhiteSpace) || input.Contains('\\'))
            throw new Exception("Bitte eine gültige HTTPS-Serveradresse ohne Anmelde- oder API-Pfad eingeben.");
        return uri.GetLeftPart(UriPartial.Authority);
    }

    static (string Server, string Request) ParseLaunchUri(string value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) || !uri.Scheme.Equals("projektzeit", StringComparison.OrdinalIgnoreCase) ||
            !uri.Host.Equals("starface", StringComparison.OrdinalIgnoreCase) || uri.AbsolutePath != "/connect")
            throw new Exception("Der ProjektZeit-Verbindungslink ist ungültig.");
        var query = Query(uri.Query);
        var server = Normalize(query.GetValueOrDefault("server") ?? "");
        var request = query.GetValueOrDefault("request") ?? "";
        if (request.Length is < 32 or > 300) throw new Exception("Die STARFACE-Verbindungsanfrage ist unvollständig oder abgelaufen.");
        return (server, request);
    }

    static string Base64Url(byte[] data) => Convert.ToBase64String(data).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    static string Url(string value) => Uri.EscapeDataString(value);
    static DateTimeOffset? Date(JsonElement parent, string name)
    {
        if (!parent.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String) return null;
        return DateTimeOffset.TryParse(value.GetString(), out var parsed) ? parsed : null;
    }

    async Task<JsonElement> Api(string path, object? body = null, bool authenticate = true, CancellationToken cancellation = default)
    {
        if (origin.Length == 0) throw new Exception("Bitte zuerst einen ProjektZeit-Server angeben.");
        using var request = new HttpRequestMessage(body is null ? HttpMethod.Get : HttpMethod.Post, origin + path);
        if (authenticate && token.Length > 0) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        if (body is not null) request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        using var response = await http.SendAsync(request, cancellation);
        var text = await response.Content.ReadAsStringAsync(cancellation);
        JsonElement result;
        try { result = JsonSerializer.Deserialize<JsonElement>(text); }
        catch { throw new Exception($"Der Server lieferte keine gültige API-Antwort (HTTP {(int)response.StatusCode})."); }
        if (response.StatusCode == HttpStatusCode.Unauthorized && authenticate)
        {
            token = "";
            SaveSettings();
            SetConnection("Sitzung abgelaufen", false);
            throw new SessionExpiredException();
        }
        if (!response.IsSuccessStatusCode)
            throw new Exception(result.TryGetProperty("error", out var error) ? error.GetString() ?? "Anfrage fehlgeschlagen." : $"HTTP {(int)response.StatusCode}");
        return result;
    }

    async Task<bool> SessionIsValid()
    {
        try { await Api("/api/v1/me"); return true; }
        catch { return false; }
    }

    async Task Run(Func<Task> action, bool cancellable = false)
    {
        if (busy) return;
        busy = true;
        BusyBar.Visibility = Visibility.Visible;
        if (cancellable) SetCancellationVisible(true);
        UpdateControls();
        try { await action(); }
        catch (OperationCanceledException) { SetStatus("Vorgang abgebrochen.", true); }
        catch (SessionExpiredException error) { SetStatus(error.Message, true); ShowLogin(error.Message); }
        catch (HttpRequestException) { SetConnection("Server nicht erreichbar", false); SetStatus("Server nicht erreichbar oder TLS-Verbindung fehlgeschlagen.", true); }
        catch (Exception error) { SetStatus(error.Message, true); }
        finally
        {
            busy = false;
            BusyBar.Visibility = Visibility.Collapsed;
            SetCancellationVisible(false);
            UpdateControls();
        }
    }

    void SetCancellationVisible(bool visible)
    {
        CancelButton.Visibility = visible && AppShell.Visibility == Visibility.Visible ? Visibility.Visible : Visibility.Collapsed;
        LoginCancelButton.Visibility = visible && LoginShell.Visibility == Visibility.Visible ? Visibility.Visible : Visibility.Collapsed;
    }

    void SetStatus(string message, bool error = false)
    {
        StatusText.Text = message;
        StatusText.Foreground = new SolidColorBrush(error ? Color.FromRgb(255, 143, 152) : Color.FromRgb(148, 166, 190));
        LoginStatus.Text = message;
        LoginStatus.Foreground = StatusText.Foreground;
    }

    void SetConnection(string message, bool connected)
    {
        ConnectionText.Text = message;
        ConnectionDot.Fill = new SolidColorBrush(connected ? Color.FromRgb(25, 191, 134) : Color.FromRgb(253, 186, 116));
    }

    void SetStarface(string message, bool connected)
    {
        StarfaceState.Text = message;
        StarfaceDot.Fill = new SolidColorBrush(connected ? Color.FromRgb(25, 191, 134) : Color.FromRgb(113, 128, 150));
    }

    static void Browser(string address)
    {
        try { Process.Start(new ProcessStartInfo(address) { UseShellExecute = true }); }
        catch { throw new Exception("Windows konnte den Standardbrowser nicht öffnen. Bitte einen Standardbrowser festlegen."); }
    }

    async void BrowserLogin(object sender, RoutedEventArgs e) => await Run(async () =>
    {
        origin = Normalize(ServerInput.Text);
        token = "";
        await AuthenticateAsync(origin);
        ShowApp();
        await RefreshAll();
        SetStatus("Sicher im Browser angemeldet.");
    }, true);

    async Task AuthenticateAsync(string server)
    {
        origin = Normalize(server);
        ServerInput.Text = origin;
        ServerInput.IsEnabled = false;
        LoginButton.IsEnabled = false;
        pending?.Dispose();
        pending = new CancellationTokenSource(TimeSpan.FromMinutes(5));
        var listener = new TcpListener(IPAddress.Loopback, 0);
        try
        {
            listener.Start();
            var port = ((IPEndPoint)listener.LocalEndpoint).Port;
            var redirect = $"http://127.0.0.1:{port}/callback";
            var verifier = Base64Url(RandomNumberGenerator.GetBytes(64));
            var challenge = Base64Url(SHA256.HashData(Encoding.ASCII.GetBytes(verifier)));
            var stateValue = Base64Url(RandomNumberGenerator.GetBytes(32));
            var address = origin + "/client/authorize?response_type=code&client_id=" + ClientId +
                          "&redirect_uri=" + Url(redirect) + "&code_challenge=" + Url(challenge) +
                          "&code_challenge_method=S256&state=" + Url(stateValue) + "&client_name=" + Url("ProjektZeit für Windows");
            SetStatus("Browser geöffnet. Bitte dort anmelden und die Verbindung erlauben.");
            Browser(address);
            var callback = await ReceiveLoopback(listener, stateValue, "/callback", pending.Token);
            if (callback.TryGetValue("error", out var denied)) throw new Exception(denied == "access_denied" ? "Anmeldung wurde im Browser abgebrochen." : "Browseranmeldung fehlgeschlagen: " + denied);
            if (!callback.TryGetValue("code", out var code) || code.Length < 24) throw new Exception("Der Browser lieferte keinen gültigen Anmeldecode.");
            SetStatus("Anmeldung wird sicher abgeschlossen …");
            var result = await Api("/api/v1/client-auth/token", new { grant_type = "authorization_code", client_id = ClientId, redirect_uri = redirect, code, code_verifier = verifier }, false, pending.Token);
            token = result.GetProperty("access_token").GetString() ?? throw new Exception("Der Server lieferte keinen Sitzungstoken.");
            SaveSettings();
        }
        finally
        {
            listener.Stop();
            pending?.Dispose();
            pending = null;
            ServerInput.IsEnabled = true;
            LoginButton.IsEnabled = true;
        }
    }

    static async Task<Dictionary<string, string>> ReceiveLoopback(TcpListener listener, string expectedState, string expectedPath, CancellationToken cancellation)
    {
        while (true)
        {
            using var client = await listener.AcceptTcpClientAsync(cancellation);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            timeout.CancelAfter(TimeSpan.FromSeconds(6));
            await using var stream = client.GetStream();
            var bytes = new List<byte>();
            var one = new byte[1];
            while (bytes.Count < 16_000 && await stream.ReadAsync(one, timeout.Token) > 0)
            {
                bytes.Add(one[0]);
                if (bytes.Count >= 4 && bytes[^4] == 13 && bytes[^3] == 10 && bytes[^2] == 13 && bytes[^1] == 10) break;
            }
            Dictionary<string, string>? data = null;
            try
            {
                var first = Encoding.ASCII.GetString(bytes.ToArray()).Split('\n')[0].Trim().Split(' ');
                if (first.Length == 3 && first[0] == "GET")
                {
                    var uri = new Uri("http://127.0.0.1" + first[1]);
                    var query = Query(uri.Query);
                    if (uri.AbsolutePath == expectedPath && query.GetValueOrDefault("state") == expectedState && (query.ContainsKey("code") || query.ContainsKey("error"))) data = query;
                }
            }
            catch { }
            var ok = data is not null;
            var html = "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>ProjektZeit</title><style>body{font:16px system-ui;background:#0b111b;color:#f5f8fc;display:grid;place-items:center;min-height:100vh;margin:0}.box{max-width:480px;padding:28px;border:1px solid #2b3d56;border-radius:16px;background:#141e2d}h1{font-size:24px}</style><div class=box><h1>" + (ok ? "Anmeldung empfangen" : "Ungültige Rückleitung") + "</h1><p>" + (ok ? "Du kannst dieses Fenster schließen und zu ProjektZeit zurückkehren." : "Bitte starte die Anmeldung im Windows-Client erneut.") + "</p></div>";
            var payload = Encoding.UTF8.GetBytes(html);
            var header = Encoding.ASCII.GetBytes($"HTTP/1.1 {(ok ? "200 OK" : "400 Bad Request")}\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {payload.Length}\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n\r\n");
            await stream.WriteAsync(header, cancellation);
            await stream.WriteAsync(payload, cancellation);
            if (data is not null) return data;
        }
    }

    async Task RefreshAll()
    {
        var me = await Api("/api/v1/me");
        var dashboard = await Api("/api/v1/dashboard");
        var work = await Api("/api/v1/worktime/state", new { });
        var integrations = await Api("/api/v1/integrations");
        Render(me, dashboard, work, integrations);
        SetConnection("Verbunden", true);
        SetStatus("Daten sind aktuell.");
    }

    async Task RefreshQuietly()
    {
        try { await RefreshAll(); }
        catch (SessionExpiredException error) { ShowLogin(error.Message); }
        catch { SetConnection("Verbindung wird erneut geprüft", false); }
    }

    void Render(JsonElement me, JsonElement dashboard, JsonElement work, JsonElement integrations)
    {
        var user = me.GetProperty("user");
        IdentityText.Text = (user.TryGetProperty("username", out var username) ? username.GetString() : "Benutzer") + " · Windows-Client";
        projects.Clear();
        foreach (var row in dashboard.GetProperty("projects").EnumerateArray())
        {
            if (row.TryGetProperty("active", out var active) && !active.GetBoolean()) continue;
            long? customerId = row.TryGetProperty("customer_id", out var customer) && customer.ValueKind == JsonValueKind.Number ? customer.GetInt64() : null;
            projects.Add(new Choice(row.GetProperty("id").GetInt64(), row.GetProperty("name").GetString() ?? "Projekt", customerId));
        }
        var customers = new List<Choice> { new(0, "Alle Kunden") };
        foreach (var row in dashboard.GetProperty("customers").EnumerateArray()) customers.Add(new Choice(row.GetProperty("id").GetInt64(), row.GetProperty("name").GetString() ?? "Kunde"));
        var oldCustomer = (CustomerSelect.SelectedItem as Choice)?.Id ?? 0;
        CustomerSelect.ItemsSource = customers;
        CustomerSelect.SelectedItem = customers.FirstOrDefault(item => item.Id == oldCustomer) ?? customers[0];
        CategorySelect.ItemsSource = dashboard.GetProperty("categories").EnumerateArray().Select(row => new Choice(row.GetProperty("id").GetInt64(), row.GetProperty("name").GetString() ?? "Kategorie")).ToList();
        if (CategorySelect.Items.Count > 0 && CategorySelect.SelectedIndex < 0) CategorySelect.SelectedIndex = 0;
        FillProjects();

        workState = work.GetProperty("state").GetString() ?? "stopped";
        var workItem = work.GetProperty("work");
        workStarted = workItem.ValueKind == JsonValueKind.Object ? Date(workItem, "started_at") : null;
        var pauseItem = work.GetProperty("pause");
        pauseStarted = pauseItem.ValueKind == JsonValueKind.Object ? Date(pauseItem, "started_at") : null;
        activeProject = "";
        projectStarted = null;
        foreach (var row in dashboard.GetProperty("entries").EnumerateArray())
        {
            var open = !row.TryGetProperty("ended_at", out var ended) || ended.ValueKind == JsonValueKind.Null;
            var idle = row.TryGetProperty("is_idle", out var isIdle) && isIdle.GetInt32() != 0;
            if (!open || idle) continue;
            activeProject = row.GetProperty("project").GetString() ?? "Projekt";
            projectStarted = Date(row, "started_at");
            break;
        }

        pbx = "";
        var linked = false;
        foreach (var row in integrations.GetProperty("integrations").EnumerateArray())
        {
            if (row.GetProperty("provider").GetString() != "starface") continue;
            pbx = row.TryGetProperty("domain", out var domain) ? domain.GetString() ?? "" : "";
            linked = row.TryGetProperty("has_secret", out var secret) && secret.GetBoolean();
        }
        StarfaceDomain.Text = pbx.Length > 0 ? pbx : "Keine Serveradresse hinterlegt";
        SetStarface(linked ? "Verbunden" : pbx.Length > 0 ? "Noch nicht verbunden" : "Nicht eingerichtet", linked);
        StarfaceConnectButton.IsEnabled = pbx.Length > 0;
        SaveSettings();
        UpdateControls();
        UpdateClock();
    }

    void FillProjects()
    {
        var customer = (CustomerSelect.SelectedItem as Choice)?.Id ?? 0;
        var old = (ProjectSelect.SelectedItem as Choice)?.Id ?? 0;
        var filtered = projects.Where(project => customer == 0 || project.CustomerId == customer).ToList();
        ProjectSelect.ItemsSource = filtered;
        ProjectSelect.SelectedItem = filtered.FirstOrDefault(project => project.Id == old);
        if (ProjectSelect.SelectedIndex < 0 && filtered.Count > 0) ProjectSelect.SelectedIndex = 0;
        UpdateControls();
    }

    void UpdateControls()
    {
        var working = workState != "stopped";
        var paused = workState == "pause";
        WorkStateText.Text = paused ? "Pause läuft" : working ? "Arbeitstag läuft" : "Noch nicht begonnen";
        CurrentProjectText.Text = paused ? "Projektzeit pausiert" : activeProject.Length > 0 ? activeProject : "Kein Projekt läuft";
        WorkButton.Content = working ? "Arbeit beenden" : "Arbeit beginnen";
        WorkButton.Background = new SolidColorBrush(working ? Color.FromRgb(219, 79, 98) : Color.FromRgb(25, 191, 134));
        PauseButton.Content = paused ? "Pause beenden" : "Pause";
        WorkButton.IsEnabled = !busy && !paused;
        PauseButton.IsEnabled = !busy && working;
        StartProjectButton.IsEnabled = !busy && working && !paused && ProjectSelect.SelectedItem is Choice && CategorySelect.SelectedItem is Choice;
        StopProjectButton.IsEnabled = !busy && working && !paused && activeProject.Length > 0;
        ProjectHint.Text = !working ? "Beginne zuerst deinen Arbeitstag." : paused ? "Beende zuerst die Pause." : ProjectSelect.Items.Count == 0 ? "Für diese Auswahl gibt es kein aktives Projekt." : activeProject.Length > 0 ? "Ein neues Projekt beendet automatisch die bisherige Projektzeit." : "Bereit zum Starten.";
    }

    void UpdateClock()
    {
        var start = workState == "pause" ? pauseStarted : projectStarted ?? workStarted;
        var elapsed = start.HasValue ? DateTimeOffset.Now - start.Value.ToLocalTime() : TimeSpan.Zero;
        if (elapsed < TimeSpan.Zero) elapsed = TimeSpan.Zero;
        ElapsedText.Text = $"{(int)elapsed.TotalHours:00}:{elapsed.Minutes:00}:{elapsed.Seconds:00}";
    }

    async Task WorkAction(string action, string success)
    {
        await Api("/api/v1/worktime/action", new { action });
        await RefreshAll();
        SetStatus(success);
    }

    async void ToggleWork(object sender, RoutedEventArgs e) => await Run(() => WorkAction(workState == "stopped" ? "begin" : "end", workState == "stopped" ? "Arbeitsbeginn gespeichert." : "Arbeitsende gespeichert."));
    async void TogglePause(object sender, RoutedEventArgs e) => await Run(() => WorkAction(workState == "pause" ? "resume" : "pause", workState == "pause" ? "Pause beendet." : "Pause gestartet."));
    void CustomerChanged(object sender, SelectionChangedEventArgs e) => FillProjects();
    void SelectionChanged(object sender, SelectionChangedEventArgs e) => UpdateControls();

    async void StartProject(object sender, RoutedEventArgs e) => await Run(async () =>
    {
        if (ProjectSelect.SelectedItem is not Choice project || CategorySelect.SelectedItem is not Choice category) return;
        await Api("/api/v1/timer/start", new { project_id = project.Id, category_id = category.Id, note = NoteText.Text.Trim() });
        NoteText.Clear();
        await RefreshAll();
        SetStatus("Projekt gestartet.");
    });

    async void StopProject(object sender, RoutedEventArgs e) => await Run(async () =>
    {
        await Api("/api/v1/timer/stop", new { });
        await RefreshAll();
        SetStatus("Projektzeit beendet. Der Arbeitstag läuft weiter.");
    });

    async void Check(object sender, RoutedEventArgs e) => await Run(async () =>
    {
        var list = await Api("/api/v1/integrations");
        JsonElement? starface = null;
        foreach (var row in list.GetProperty("integrations").EnumerateArray()) if (row.GetProperty("provider").GetString() == "starface") starface = row;
        if (starface is null || !starface.Value.GetProperty("has_secret").GetBoolean()) { SetStarface("Nicht verbunden", false); throw new Exception("STARFACE ist noch nicht mit deinem Konto verbunden."); }
        var domain = starface.Value.GetProperty("domain").GetString() ?? "";
        var probe = await Api("/api/v1/integrations/test", new { provider = "starface", domain, username = "", secret = "" });
        var ok = probe.TryGetProperty("ok", out var state) && state.GetBoolean();
        SetStarface(ok ? "Verbindung geprüft" : "Prüfung fehlgeschlagen", ok);
        SetStatus(ok ? "STARFACE-Verbindung erfolgreich geprüft." : "STARFACE antwortet nicht wie erwartet.", !ok);
    });

    async void ConnectStarface(object sender, RoutedEventArgs e) => await Run(() => ConnectStarfaceCore(), true);

    async Task ConnectStarfaceCore(string? launchRequest = null, string? linkServer = null)
    {
        if (token.Length == 0) throw new SessionExpiredException();
        if (linkServer is not null && !string.Equals(origin, linkServer, StringComparison.OrdinalIgnoreCase)) throw new Exception("Der Verbindungslink gehört zu einem anderen ProjektZeit-Server.");
        pending?.Dispose();
        pending = new CancellationTokenSource(TimeSpan.FromMinutes(5));
        var listener = new TcpListener(IPAddress.Loopback, 0);
        try
        {
            listener.Start();
            var port = ((IPEndPoint)listener.LocalEndpoint).Port;
            var redirect = $"http://127.0.0.1:{port}";
            object payload = launchRequest is null ? new { domain = pbx, redirect_uri = redirect } : new { launch_request = launchRequest, redirect_uri = redirect };
            SetStarface("Browseranmeldung läuft", false);
            SetStatus("STARFACE-Anmeldeadresse wird vorbereitet …");
            var start = await Api("/api/v1/integrations/starface/start", payload, true, pending.Token);
            if (start.TryGetProperty("domain", out var returnedDomain)) pbx = returnedDomain.GetString() ?? pbx;
            var address = start.GetProperty("url").GetString() ?? throw new Exception("STARFACE lieferte keine Anmeldeadresse.");
            if (!Uri.TryCreate(address, UriKind.Absolute, out var uri) || uri.Scheme != "https" || uri.UserInfo.Length > 0) throw new Exception("STARFACE lieferte eine unsichere Anmeldeadresse.");
            var expectedState = Query(uri.Query).GetValueOrDefault("state") ?? "";
            Browser(address);
            SetStatus("STARFACE-Anmeldung im Browser abschließen …");
            var result = await ReceiveLoopback(listener, expectedState, "/", pending.Token);
            await Api("/api/v1/integrations/starface/finish", result, true, pending.Token);
            SetStarface("Verbunden", true);
            StarfaceDomain.Text = pbx;
            SaveSettings();
            SetStatus("STARFACE erfolgreich verbunden.");
        }
        finally
        {
            listener.Stop();
            pending?.Dispose();
            pending = null;
        }
    }

    async void Logout(object sender, RoutedEventArgs e) => await Run(async () =>
    {
        if (token.Length > 0) try { await Api("/api/v1/auth/revoke", new { }); } catch { }
        token = "";
        SaveSettings();
        SetConnection("Abgemeldet", false);
        ShowLogin();
    });

    void OpenWeb(object sender, RoutedEventArgs e)
    {
        try { Browser(origin.Length > 0 ? origin : Normalize(ServerInput.Text)); }
        catch (Exception error) { SetStatus(error.Message, true); }
    }

    void CancelOperation(object sender, RoutedEventArgs e) => pending?.Cancel();

    static Dictionary<string, string> Query(string query)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var part in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var values = part.Split('=', 2);
            var key = Uri.UnescapeDataString(values[0].Replace("+", " "));
            var value = values.Length > 1 ? Uri.UnescapeDataString(values[1].Replace("+", " ")) : "";
            result[key] = value;
        }
        return result;
    }
}
