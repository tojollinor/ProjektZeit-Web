# Projekt-Tags und Projektkopien

Unter **Projekte** stehen zwei Erweiterungen bereit:

- **Tags verwalten**: Tags anlegen, umbenennen oder archivieren. Ein Tag gilt allgemein für die eigenen Projekte oder für einen bestimmten Kunden. Archivierte Tags bleiben an bestehenden Projekten und in Auswertungen erhalten; neue Zuordnungen und Kopien übernehmen sie nicht.
- **Projekt kopieren**: Neuen, eindeutigen Namen vergeben. Kunde und aktive, passende Tags werden übernommen. Das neue Projekt ist aktiv. Zeiten, Anbieterzuordnungen, Rechnungsstatus und alte Buchungen werden nicht kopiert. Die Herkunft wird angezeigt.

Der lokale Kunden-/Tagfilter unter Projekte zeigt einen Zeitvergleich. Er berücksichtigt abgeschlossene manuelle Zeitabschnitte und zugeordnete Anbieterintervalle über die gesamte Projekthistorie. Überschneidungen zählen innerhalb eines Projekts einmal; laufende Zeiten und Tickets ohne tatsächliches Zeitintervall werden nicht als Dauer erfunden. Die Summe ist ein Projektvergleich, keine Mitarbeiterarbeitszeit oder Rechnungssumme. Mehrere Projekte können sich zeitlich überschneiden.

Tags folgen der vorhandenen Eigentümerstruktur: Benutzer verwalten ihre eigenen Tags und Projekte. Es gibt in diesem Paket keinen unternehmensweiten, gemeinsamen Tagkatalog. Anfragen werden serverseitig auf Benutzer- und Kundenbereich geprüft; Änderungen verwenden die vorhandenen CSRF-Prüfungen und Speicherbelege.

## Kurzer Abnahmetest

1. Ein allgemeines und ein kundenspezifisches Tag anlegen.
2. Beide einem Projekt dieses Kunden zuordnen; bei einem anderen Kunden darf das kundenspezifische Tag nicht auswählbar sein.
3. Das Projekt mit neuem Namen kopieren. Kunde und Tags müssen vorhanden, Zeiten und Abrechnung leer sein.
4. Nach dem Tag filtern und die Dauern der beiden Projekte vergleichen.
5. Ein Tag archivieren: historische Zuordnungen bleiben sichtbar; weitere Kopien übernehmen dieses Tag nicht.

Automatisch geprüft: SQLite-Funktionstests, produktiver HTTP-Handler mit CSRF und wiederholter Anfragekennung, DOM-Tests für Filter, Dialoge, Speichersperre, Fehler und sichere Textdarstellung. MariaDB wird zusätzlich durch den GitHub-Workflow getestet. DOM-Tests ersetzen keine visuelle Live-Browser-Abnahme.
