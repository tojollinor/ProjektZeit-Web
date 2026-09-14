# ProjektZeit 0.7.2 – Folgekorrekturen aus dem Live-Test

Dieses Update behebt die bestätigten Fehler der Live-Prüfung von 0.7.1 und setzt die gewünschte Benutzerliste um.

- **Benutzer:** Durchsuchbare Liste mit Name, Benutzername, Rollen und Aktivstatus. Ein Klick öffnet das Detailfenster mit Stammdaten, Rollen und Arbeitszeit einschließlich Urlaubskonto. Erstellen öffnet direkt den neuen Benutzer. Berechtigungen und Schutz des Systemadministrators bleiben wirksam.
- **Kunden:** Kontaktinformationen in der Übersicht werden ausschließlich über die Kunden-ID zugeordnet. Nach Speichern werden Kopfbereich und Details gemeinsam erneuert; „Ansprechpartner hinzufügen“ bleibt auch nach Abbrechen verfügbar. Die Reihenfolge der Stammdatenbereiche bleibt gleich.
- **Notdienst und Dialoge:** Aktionsbuttons lösen kein unbeabsichtigtes Formular-Submit bzw. Neuladen mehr aus. Auch reine Anzeigedialoge verhindern die Standard-Übermittlung des Formulars. Deaktivierte Mitarbeiter verschwinden aus neuen Planungen ohne Seitenreload.
- **Zuordnungen:** Neue Projektzuordnungen laden aktuelle Kunden; gelöschte Kunden stehen nicht mehr zur Auswahl. Nur aktive Projekte mit Kunde werden angeboten.
- **API:** Persönliche API-Einstellungen werden einmal angelegt. Wiederholtes Navigieren vervielfacht die Panels nicht mehr. Das Modul benötigt keinen globalen DOM-Observer mehr; vorhandene Einstellungsbereiche werden nicht ständig erneut verschoben.
- **STARFACE:** Der Menüstatus berücksichtigt dieselbe zentrale Client-Konfiguration wie OAuth. Alte persönliche Zugangsdaten überdecken kein fehlendes zentrales Client Secret mehr. In diesem Zustand erscheint der Administratorhinweis ohne erfolglose Anmeldeoption.
- **Projekte:** Die veraltete zusätzliche Aktiv-Liste wurde entfernt. Der bestehende Projektkatalog übernimmt Statusverwaltung und Übersicht; Projektanlage und Timer bleiben verfügbar.
- **Darstellung:** Ticketlisten scrollen im eigenen Bereich. Auch die zweite feste Tabellenspalte verwendet die Theme-Farben. „Downloads“ ist der konsistente Seitentitel; „Abwesenheiten & Abgleich“ bleibt im Admin-Untermenü. Benutzerlisten und Dialoge enthalten Regeln für schmale Ansichten.
- **Leistungsdetails:** TeamViewer- und STARFACE-Details zeigen verständliche Felder für Gerät/Teilnehmer, Beginn, Ende und Dauer statt eines technischen Rohdatenblocks. Fehlende Werte bleiben als unbekannt erkennbar.

## Prüfung

- Python-Suite: 138 Tests, lokal 4 umgebungsabhängig übersprungen; keine Fehler.
- Alle sechs UI-Testgruppen mit isoliertem Anwendungsserver bzw. DOM bestanden.
- Zusätzliche Timeline-, STARFACE- und Arbeitsbereichstests sowie Syntaxprüfung aller JavaScript- und Python-Dateien bestanden.
- Regressionen prüfen insbesondere zwei Kunden mit unterschiedlichen Ansprechpartnern, Speichern/Abbrechen von Stammdaten, API-Eindeutigkeit nach Navigation, Benutzeranlage und Arbeitszeittab im Dialog, entfernte Kunden in Projektzuordnungen sowie entfernte Mitarbeiter im Notdienst.
- Die Release-CI führt zusätzlich die Tests gegen MariaDB aus. Ein deploybares Image entsteht erst nach erfolgreicher PR-CI, Merge und erfolgreichem Main-Publish.

Die geänderte Version wurde noch nicht auf der Live-Instanz visuell geprüft. Desktop, echte mobile Ansicht sowie Dark/Light werden nach Installation erneut kontrolliert. Die automatisierten DOM-Tests ersetzen diese Prüfung nicht. E-Mail-Fehlerfälle werden automatisiert geprüft; in diesem Durchlauf wurden keine echten E-Mails versandt. Die noch unvollständige Benachrichtigungsregel-Verwaltung ist nicht Bestandteil dieses Reparaturupdates.
