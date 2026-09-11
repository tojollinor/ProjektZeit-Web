# ProjektZeit Windows-Client (erste Version)

Im Webportal unter **Einstellungen → Windows-Client herunterladen** ist die EXE
direkt mit dem GitHub-Release `windows-client` verknüpft. Der erste erfolgreiche
Windows-Build legt diesen Release an; weitere Builds ersetzen dessen EXE.
Alternativ: GitHub Actions → **Windows-Client bauen** → erfolgreicher Lauf → Artefakt
**ProjektZeit-Windows** herunterladen, ZIP entpacken, EXE starten.
Die EXE ist nicht signiert; Windows kann einen SmartScreen-Hinweis anzeigen.
Alternativ mit Python inklusive Tk starten: `python windows-client/client.py`.

1. Zuerst das aktualisierte Server-Image deployen.
2. HTTPS-ProjektZeit-Adresse und ProjektZeit-Zugang eingeben.
3. STARFACE-Domain eingeben, „STARFACE im Browser verknüpfen“ wählen.
4. Im Browser bei STARFACE anmelden; Erfolg anschließend im Client abwarten.

Der lokale Listener bindet ausschließlich 127.0.0.1 an einen zufälligen Port.
PKCE-Verifier und OAuth-Tokens bleiben auf dem Server. Der Anmeldecode wird mit
dem sitzungsgebundenen State über HTTPS übertragen. Keine Passwörter oder Tokens
werden vom Client auf Festplatte gespeichert. STARFACE-Verknüpfungen benötigen
derzeit ProjektZeit-Adminrechte. Nach Erfolg kann der Client geschlossen werden.
Der Server kann den gespeicherten Refresh-Token bei weiteren API-Abfragen nutzen.
Periodische Hintergrundimporte sind damit noch nicht implementiert.

Arbeitsbeginn/-ende schreiben direkt in die zentrale Datenbank. Projektwahl,
Stempelungen und Übersichten sind über „Webübersicht öffnen“ erreichbar (eigene
Browser-Anmeldung). Kein Offlinebetrieb und noch kein vollständiger nativer
Projekt-Timer. „Abmelden“ widerruft die Client-Sitzung; bloßes Schließen entfernt
sie nur aus dem Arbeitsspeicher, serverseitig läuft sie regulär ab.
