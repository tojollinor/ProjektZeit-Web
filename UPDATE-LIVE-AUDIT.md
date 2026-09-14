# ProjektZeit 0.7.1 – Reparaturen aus dem Live-Test

Dieses Paket behebt die im Test nachgewiesenen Ursachen. Der komplette fachliche und optische Abnahmetest wird nach Aktualisierung der Instanz fortgesetzt.

- **Dashboard:** Eine Funktionsdeklaration innerhalb der Provider-Schleife überschrieb wegen JavaScript-Block-Semantik die globale Dashboard-Zeichenfunktion. Der Provider-Renderer ist jetzt lokal gebunden. Zähler und Zeitstrahl werden wieder initialisiert.
- **Arbeitszeitkonto:** MariaDB liefert `SUM` als Decimal. Die ganzzahlige Sekunden-Summe wird vor der JSON-Ausgabe ausdrücklich in einen Integer umgewandelt. Der Mitarbeiterwechsel löscht alte Werte sofort und bietet bei Fehlern eine erneute Abfrage an.
- **Start nach Anmeldung:** Arbeitszeit- und Kalenderansichten werden durch Anmelde-/Bereitschaftsereignisse initialisiert. Die bisherige 30-Sekunden-Frist entfällt. Ein Fehler beim Dashboard-Laden beendet nicht die Anmeldung.
- **Abfrageschleifen:** Die History-Statusanzeige löste über einen DOM-Observer ständig neue Backend-Anfragen aus. Sie lädt jetzt einmal je neu erzeugter Verbindungskarte. Wiederholte identische HTML-Änderungen und unnötige globale Observer wurden an den bestätigten Stellen entfernt.
- **Löschen/Entfernen:** Rote Buttons wechseln beim ersten Klick zu einem grauen „Confirm“. Erst der zweite Klick führt die Aktion aus. Nach fünf Sekunden, Navigation oder Escape verfällt die Bestätigung. Ladezustand und Ergebnis verwenden die vorhandene Absicherung gegen doppelte Schreibaktionen.
- **Dialoge:** Bestätigungen und Eingabeabfragen verwenden anwendungsinterne Dialoge. Ungespeicherte Formulare können ohne blockierende `confirm`-Dialoge verlassen werden. Die normale Browserwarnung beim Schließen einer Seite mit ungespeicherten Daten bleibt bestehen.
- **Benutzerzugang:** Benutzer können mit der Berechtigung `users.disable` aktiviert/deaktiviert werden. Deaktivieren beendet Sitzungen und widerruft API-Tokens. Eigener Zugang und geschützter Systemadministrator sind abgesichert. Arbeits- und Abrechnungshistorie bleibt bestehen; dies ist keine dauerhafte Löschfunktion.
- **Kunden und Darstellung:** Detailerweiterungen nutzen eine gemeinsame Abfrage. Doppelte Stammdaten-/Kontaktanzeigen wurden entfernt, das Anlegen von Ansprechpartnern bleibt erreichbar. Tabellen scrollen innerhalb ihrer Fläche; Ticketdialoge und weitere Flächen verwenden die Theme-Farben. Navigation und Kalendericons werden nach dynamischer Initialisierung nachgezogen.
- **Version/Updates:** Kleine Versions- und Buildanzeige unter dem Benutzer. Der Link „Auf Aktualisierungen prüfen“ vergleicht mit erfolgreich veröffentlichten Main-Builds. Fehler, laufende Prüfung und unbekannte Buildkennung bleiben ausdrücklich unbekannt; die Prüfung läuft mit Zeitlimit und gemeinsamem Cache. Für eigene Docker-Builds `BUILD_REVISION` als vollständigen Commit-SHA setzen.

## Prüfung

Automatisierte Tests decken den vollständigen lokalen HTTP-/DOM-Start, verzögerte Anmeldung, Dashboard-Achse, ausbleibende Observer-Nachfragen, deduplizierte Kundendetails, Mitarbeiterwechsel bei Fehlern, Benutzeraktivierung, Sitzungssperre, Zwei-Faktor-Anmeldung sowie die neuen Dialog-/Buttonzustände ab. Die MariaDB-CI serialisiert zusätzlich den vollständigen Arbeitszeitbericht.

Desktop/Mobil und beide Farbmodi werden nach dem Deployment erneut visuell geprüft. Dieser Stand ist keine Behauptung, dass sämtliche ursprünglich gewünschten Funktionen bereits vollständig abgenommen sind.
