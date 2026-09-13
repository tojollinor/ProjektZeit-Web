# Zeiten prüfen und zuordnen

Dieses Update ergänzt Zeiterfassung, Projekte und Buchhaltung um einen gemeinsamen lokalen Zeitbereich. Im Kundendialog liegt er im Reiter **Zeitstrahl**.

- **Zeitstrahl:** Arbeitszeit und Pausen getrennt von Projektzeiten, Telefonaten, Fernwartungen und Tickets; überlappende Ereignisse erhalten eigene Zeilen. Administratoren können innerhalb eines konkreten Kunden oder Projekts die zugehörigen Mitarbeiter anzeigen. Bestehende Eigentumsrechte bleiben bestehen; gleichnamige Kunden verschiedener Benutzer werden nicht automatisch zusammengeführt.
- **Zuordnungseingang:** Ereignisse ohne Projekt auswählen und gemeinsam zuordnen. Hinterlegte Rufnummern, Geräte und E-Mail-Adressen liefern Vorschläge. Vorschläge werden ausdrücklich übernommen.
- **Tagesabschluss:** Fehlende Zuordnungen, ungeprüfte Ereignisse, Überschneidungen und laufende Timer prüfen. Das Beenden der Arbeitszeit bleibt eine eigene Aktion.
- **Geprüfte Buchungen:** Abgeschlossene Zeiten ausdrücklich mit oder ohne Abrechnung freigeben. Überlappende abrechenbare Zeiten desselben Mitarbeiters werden abgewiesen. Eine Prüfung lässt sich wieder öffnen. Änderungen an Zeit oder Projekt machen die bisherige Freigabe ungültig. Tickets ohne gemessene Dauer erzeugen keine abrechenbare Zeit.

Die Freigaben sind eine Prüfgrundlage; sie erzeugen keine Rechnung und verändern keine bestehenden Rechnungen. Alte Ereignisse und Stempelungen werden nicht automatisch freigegeben.

## Betrieb

Der Container startet über `runtime.py`; Produktion und CI verwenden dadurch dieselben Erweiterungen. Beim ersten Start werden lokale Ereignisintervalle einmalig indiziert. Die Dauer dieses ersten Starts hängt vom Archivumfang ab. Bestehende Rohdaten bleiben erhalten.

Dashboard-Daten werden für den ausgewählten Tag geladen. Statistiken aggregieren ihren Zeitraum separat und verteilen Zeiten über Mitternacht und die Berliner Sommer-/Winterzeitgrenzen korrekt. Der neue Zeitbereich zeigt höchstens 1.000 Ereignisse und kennzeichnet eine gekürzte Auswahl; für vollständige Auswertung den Zeitraum oder das Projekt eingrenzen.

Kundendetails verwenden lokale Daten ohne Provideraufruf. Provideraktualisierung erfolgt weiterhin über die vorhandenen Hintergrundjobs. Diagnoseexporte enthalten bereinigte Fehler sowie Server-Timing für Anwendung, Authentifizierung, DB-Verbindungen und Abfragen. Die ausgewiesene Gesamtzeit ist inklusive Teilzeiten; Teilzeiten dürfen nicht zusätzlich aufsummiert werden.

Reine Datenabfragen der neuen Zeitbereiche, des Dashboards und der Kundendetails sowie die Sitzungsvalidierung benötigen keinen globalen MariaDB-Schreiblock. Schreibtransaktionen behalten die bestehende Serialisierung zum Schutz gleichzeitig gestarteter Timer.

## Prüfung

Automatisiert: vollständiger Runtime-Start, HTTP-Anmeldung und neue Leseendpunkte, Rechte-/Eigentumsgrenzen, explizite Freigaben, Überschneidungen, Cachezuordnung, Sommerzeit/Mitternacht, Diagnosebereinigung und Zeitstrahl-Zeilen. GitHub CI prüft zusätzlich den vollständigen Stack gegen MariaDB und baut beide Containerarchitekturen.

Eine Live-Browser-Abnahme des neuen Images ist erst nach dem Update der Installation möglich; automatisierte Tests ersetzen diese Abnahme nicht.
