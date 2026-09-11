# ProjektZeit Windows-Client (WPF)

Zuerst erscheint das separate ProjektZeit-Anmeldefenster. Die URL-Beispiele sind
Hinweise, keine vorbelegten Server. Nach erfolgreichem Login öffnet sich die
Hauptoberfläche mit kleiner Statusanzeige. Diese prüft `/api/v1/me` alle 30 Sekunden
(während laufender Benutzeraktionen pausiert). Netzwerkfehler werden als nicht
verbunden angezeigt; eine abgelaufene Sitzung erfordert erneute Anmeldung.
STARFACE verwendet ausschließlich `pbx-login` und prüft `/rest/users/me`.

Die aktuelle EXE wird aus dem WPF-Projekt `ProjektZeit.Windows.csproj` gebaut.
Lokaler Build mit .NET 8 SDK: `dotnet publish windows-client/ProjektZeit.Windows.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o dist`.
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

## STARFACE-Verbindung aus der Weboberfläche

STARFACE-Adresse, Client-ID und Client-Secret werden zentral in der ProjektZeit-
Weboberfläche gepflegt. Der Windows-Client erhält das Client-Secret nicht.

1. EXE einmal manuell starten. Sie registriert für den aktuellen Benutzer den URI-Handler
   `projektzeit://`, wenn noch kein funktionierender Handler vorhanden ist.
2. In ProjektZeit unter Einstellungen die STARFACE-Adresse, Client-ID und das
   Client-Secret speichern.
3. In der Weboberfläche **STARFACE verbinden** wählen.
4. Der Browser öffnet einen kurzlebigen Link `projektzeit://starface/connect?...`.
   Der Link enthält nur die ProjektZeit-Serveradresse und einen einmal verwendbaren
   Zufallstoken mit fünf Minuten Gültigkeit.
5. Windows startet den ProjektZeit-Client. Ist die gespeicherte ProjektZeit-Sitzung
   noch gültig, beginnt die STARFACE-Anmeldung direkt; andernfalls wird zuerst die
   ProjektZeit-Anmeldung angezeigt.
6. Der Client öffnet den Standardbrowser für die STARFACE-Anmeldung und wartet lokal
   auf `http://127.0.0.1:PORT` auf den OAuth-Rücksprung.
7. Authorization Code und State werden an den ProjektZeit-Server übertragen. Dort
   werden Client-ID und Client-Secret für den Token-Tausch verwendet. Access- und
   Refresh-Token bleiben verschlüsselt auf dem Server.

Nach erfolgreicher Verbindung kann der Windows-Client geschlossen werden. Weitere
STARFACE-Aufrufe und Refreshes laufen direkt zwischen ProjektZeit-Server und STARFACE.

Der URI-Handler ist absichtlich zukunftssicher gehalten: Eine portable EXE schreibt
die Registrierung nicht bei jedem Start neu und überschreibt keinen vorhandenen,
weiterhin gültigen Handler. Ein späterer Installer kann denselben `projektzeit://`-
Handler auf seinen Installationspfad setzen. Dadurch muss die Weboberfläche beim
Wechsel von portablem Client zu einer installierten Version nicht geändert werden.

Der lokale Listener bindet ausschließlich 127.0.0.1 an einen zufälligen Port.
Client-Secret, STARFACE-Passwort, PKCE-Verifier und OAuth-Tokens werden nicht in den
`projektzeit://`-URI geschrieben. Der Einmal-Starttoken ist an den angemeldeten
ProjektZeit-Benutzer gebunden und nach Verwendung ungültig.

Arbeitsbeginn/-ende schreiben direkt in die zentrale Datenbank. Projektwahl,
Stempelungen und Übersichten sind über „Webübersicht öffnen“ erreichbar (eigene
Browser-Anmeldung). Kein Offlinebetrieb und noch kein vollständiger nativer
Projekt-Timer. „Abmelden“ widerruft die Client-Sitzung; bloßes Schließen lässt die
Sitzung verschlüsselt für den nächsten Start gespeichert, bis sie serverseitig
abläuft oder widerrufen wird.
