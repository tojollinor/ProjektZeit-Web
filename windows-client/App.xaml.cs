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
            using var existing = Registry.CurrentUser.OpenSubKey(root + @"\shell\open\command");
            var command = existing?.GetValue(null) as string;
            var target = CommandTarget(command);
            if (!string.IsNullOrWhiteSpace(target) && File.Exists(target)) return;

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

    static string? CommandTarget(string? command)
    {
        if (string.IsNullOrWhiteSpace(command)) return null;
        command = command.Trim();
        if (command.StartsWith('"'))
        {
            var end = command.IndexOf('"', 1);
            return end > 1 ? command[1..end] : null;
        }
        var space = command.IndexOf(' ');
        return space > 0 ? command[..space] : command;
    }
}
