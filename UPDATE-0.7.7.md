# ProjektZeit 0.7.7 – TeamViewer-Verbindungsdiagnose

Dieses Update erweitert die persönliche TeamViewer-Verbindung um eine konkrete Diagnose für ausbleibende Verbindungsberichte.

- **Aktueller Hinweis:** Direkt an der TeamViewer-Verbindung steht der aktuelle Pfad **TeamViewer → Einstellungen → Verbindungsprotokolle**. Zusätzlich erinnert die Ansicht an das angemeldete Firmenkonto, entfernte Benutzer-, Gruppen- und Datumsfilter sowie die Zugehörigkeit zum bisherigen Unternehmensprofil.
- **API-Prüfung:** Der bisherige Verbindungstest prüft jetzt neben dem Token auch das zugehörige TeamViewer-Konto, das Unternehmensprofil, die gemeldete Lizenz und die Verbindungsberichte der letzten 30 Tage.
- **Klare Zustände:** Aktuelle Berichte, eine leere Berichtsliste, fehlende Kontorechte, fehlende Berichtsrechte und ein ungültiger Token werden getrennt ausgewiesen. Eine erlaubte, aber leere Berichtsliste wird nicht als vollständig unauffällig dargestellt.
- **Minimale Rechte:** Für den vollständigen Abgleich werden ausschließlich Leserechte für Kontoinformationen und Verbindungsberichte empfohlen. Fehlt nur das Kontorecht, bleibt der eigentliche Berichtstest verwendbar. Fehlt das Berichtsrecht, wird ein neuer Script-Token verlangt.
- **API-Grenze:** TeamViewer veröffentlicht den persönlichen Schalter für ausgehende Verbindungsprotokolle nicht über die öffentliche API. ProjektZeit kann ihn daher weder auslesen noch automatisch ändern. Da bestehende Script-Tokens ebenfalls nicht erweitert werden können, führt die Oberfläche bei fehlenden Rechten gezielt zur Erstellung eines neuen Tokens.

## Betrieb

Bestehende TeamViewer-Tokens und gespeicherte Verbindungen bleiben erhalten. Wer nur Verbindungsberichte lesen darf, kann die Verbindung weiter verwenden; für die zusätzliche Konto- und Unternehmensprüfung ist ein neuer Token mit beiden Leserechten erforderlich.

Vor dem Update Datenbank und Datenverzeichnis gemeinsam sichern. Installationsbereit ist 0.7.7 erst nach erfolgreichem Merge und erfolgreichem Main-Publish.
