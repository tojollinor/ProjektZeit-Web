# ProjektZeit Windows-Client (WPF)

Die aktuelle EXE wird aus dem WPF-Projekt `ProjektZeit.Windows.csproj` gebaut.
Lokaler Build mit .NET 8 SDK: `dotnet publish windows-client/ProjektZeit.Windows.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o dist`.
Die STARFACE-Adresse ist zunächst leer. Getrennte Anzeigen melden ProjektZeit-
und STARFACE-Verbindung; STARFACE kann mit einem echten API-Test geprüft werden.
Der ProjektZeit-Sitzungstoken wird nach erfolgreichem Login mit Windows DPAPI
benutzergebunden unter `%LOCALAPPDATA%/ProjektZeit/session.dat` gespeichert.
Passwörter werden nicht gespeichert. Nach Ablauf der Sitzung erneut anmelden.
Die bisherige Python-Datei ist nur noch historischer Quellstand, kein Build-Einstieg.

Im Webportal unter **Einstellungen → Windows-Client herunterladen** ist die EXE
direkt mit dem GitHub-Release `windows-client` verknüpft. Der erste erfolgreiche
Windows-Build legt diesen Release an; weitere Builds ersetzen dessen EXE.
Alternativ: GitHub Actions → **Windows-Client bauen** → erfolgreicher Lauf → Artefakt
**ProjektZeit-Windows** herunterladen, ZIP entpacken, EXE starten.
Die EXE ist nicht signiert; Windows kann einen SmartScreen-Hinweis anzeigen.

1. Zuerst das aktualisierte Server-Image deployen.
2. HTTPS-ProjektZeit-Adresse und ProjektZeit-Zugang eingeben.
3. STARFACE-Domain eingeben, „STARFACE im Browser verknüpfen“ wählen.
4. Im Browser bei STARFACE anmelden; Erfolg anschließend im Client abwarten.

Der lokale Listener bindet ausschließlich 127.0.0.1 an einen zufälligen Port.
PKCE-Verifier und OAuth-Tokens bleiben auf dem Server. Der Anmeldecode wird mit
dem sitzungsgebundenen State über HTTPS übertragen. Keine Passwörter oder Tokens
werden im Klartext vom Client auf Festplatte gespeichert. STARFACE-Verknüpfungen benötigen
derzeit ProjektZeit-Adminrechte. Nach Erfolg kann der Client geschlossen werden.
Der Server kann den gespeicherten Refresh-Token bei weiteren API-Abfragen nutzen.
Periodische Hintergrundimporte sind damit noch nicht implementiert.

Arbeitsbeginn/-ende schreiben direkt in die zentrale Datenbank. Projektwahl,
Stempelungen und Übersichten sind über „Webübersicht öffnen“ erreichbar (eigene
Browser-Anmeldung). Kein Offlinebetrieb und noch kein vollständiger nativer
Projekt-Timer. „Abmelden“ widerruft die Client-Sitzung; bloßes Schließen entfernt
die Sitzung bleibt dagegen verschlüsselt für den nächsten Start gespeichert,
bis sie serverseitig abläuft oder widerrufen wird.
