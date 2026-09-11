using System.IO;
using System.Windows;
using Microsoft.Win32;

namespace ProjektZeit;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        TryRegisterProtocolHandler();
        var launchUri = e.Args.FirstOrDefault(x => x.StartsWith("projektzeit://", StringComparison.OrdinalIgnoreCase));
        var window = new MainWindow(launchUri);
        MainWindow = window;
        window.Show();
    }

    static void TryRegisterProtocolHandler()
    {
        try
        {
            var current = Environment.ProcessPath;
            if (string.IsNullOrWhiteSpace(current) || !File.Exists(current)) return;
            const string root = @"Software\Classes\projektzeit";
            // Starting an updated EXE must replace a registration pointing to an older copy.
            using var key = Registry.CurrentUser.CreateSubKey(root);
            key?.SetValue(null, "URL:ProjektZeit Protocol");
            key?.SetValue("URL Protocol", "");
            using var icon = Registry.CurrentUser.CreateSubKey(root + @"\DefaultIcon");
            icon?.SetValue(null, $"\"{current}\",0");
            using var open = Registry.CurrentUser.CreateSubKey(root + @"\shell\open\command");
            open?.SetValue(null, $"\"{current}\" \"%1\"");
        }
        catch
        {
            // Die EXE bleibt auch ohne Protokollregistrierung manuell nutzbar.
        }
    }

}
