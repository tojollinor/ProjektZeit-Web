# ProjektZeit für Windows 0.8.0

Der native WPF-Client bündelt die täglichen Kernfunktionen in einer modernen
Oberfläche: Arbeitsbeginn und -ende, Pause, Projektwahl, Projektwechsel,
Projektstopp, Statusanzeige sowie die STARFACE-Verknüpfung. Alle Buchungen werden
direkt am ProjektZeit-Server gespeichert; es gibt bewusst keinen Offlinepuffer.

## Anmeldung im Browser

Der Client nimmt kein ProjektZeit-Passwort mehr entgegen.

1. ProjektZeit-Server eingeben.
2. **Im Browser anmelden** wählen.
3. Anmeldung und gegebenenfalls 2FA im gewohnten Webportal abschließen.
4. Den Zugriff für „ProjektZeit für Windows“ bestätigen.
5. Der Browser leitet einmalig an den lokalen Client zurück.

Technisch wird OAuth Authorization Code mit PKCE S256 verwendet. Der lokale
Rücksprung-Listener bindet ausschließlich `127.0.0.1` auf einem zufälligen Port.
Authorization Code und PKCE-Verifier sind kurzlebig; das Passwort wird weder an
den Client noch in die Rücksprungadresse übertragen. Der daraus entstandene
Sitzungstoken wird mit Windows DPAPI benutzergebunden unter
`%LOCALAPPDATA%\ProjektZeit\session.dat` gespeichert.

## STARFACE

Die zentral hinterlegte STARFACE-Konfiguration wird im Client angezeigt. Die
Anmeldung öffnet ebenfalls den Standardbrowser. Access- und Refresh-Token sowie
Client-Secret bleiben auf dem ProjektZeit-Server. Der bestehende
`projektzeit://starface/connect`-Handler wird weiterhin registriert, damit eine
im Webportal gestartete STARFACE-Verknüpfung den Client öffnen kann.

## Bauen

Erforderlich ist das .NET 8 SDK unter Windows oder ein Build-Agent mit
Windows-Targeting:

```powershell
dotnet publish windows-client/ProjektZeit.Windows.csproj `
  -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true `
  -o dist
```

Die GitHub-Aktion „Windows-Client bauen“ veröffentlicht die resultierende
`ProjektZeit-Windows.exe` im bestehenden Release `windows-client`. Die portable
EXE ist derzeit nicht codesigniert; Windows kann deshalb einen SmartScreen-Hinweis
anzeigen.
