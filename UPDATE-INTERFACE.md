# Oberfläche und Verwaltung – September 2026

- Dashboard: drei Spalten am Desktop, eine Spalte auf Mobilgeräten; Reihenfolge, Sichtbarkeit und Höhe der vier Widgets werden pro Benutzer gespeichert. Widgets scrollen innerhalb ihrer Fläche.
- Benutzer: Anlage über Plus, Rollen als suchbare Tags. Sollstunden, Arbeitstage, Feiertagsregion und Urlaubsanspruch stehen im Reiter Arbeitszeit des ausgewählten Mitarbeiters.
- Rollen: ein Editor mit Rollenauswahl und Plus. API (Beta) und Systemschutz werden über die bestehenden Rollenberechtigungen geöffnet. Die entfernte Super-Admin-Rolle wird nicht wieder eingeführt.
- Sicherheit: optionale Authenticator-Einrichtung beim Login; globale 2FA-Pflicht mit Einrichtungsfrist. TOTP-Schlüssel sind verschlüsselt, Wiederherstellungscodes gehasht und einmalig verwendbar. Aktivieren der Pflicht beendet vorhandene Sitzungen. Web- und native Token-Anmeldung verlangen denselben zweiten Faktor. Ältere native Clients benötigen dafür Unterstützung des `mfa_required`/`otp`-Dialogs; ohne zweiten Faktor wird kein Token ausgegeben.
- Systemschutz: berechtigtes Zurücksetzen fremder 2FA beendet die zugehörigen Sitzungen und hinterlässt einen Audit-Eintrag.
- SMTP: Verbindungstest ohne E-Mail sowie ausdrücklicher Testmail-Versand. Verständliche Fehler für Anmeldung, TLS, Zeitüberschreitung, Absender und Empfänger. Der Datenbankzugriff ist vor dem Netzwerkaufruf abgeschlossen. Ereignisbasierte automatische Benachrichtigungsregeln sind weiterhin nur vorbereitet.
- Kunden: direkte Kartei, kontrastreiche Kontakte und eigener Reiter Projekte mit aktiven Projekten und kundenbezogener Neuanlage.
- Projekte: echte Reiter, keine zusätzliche Kunden-/Kategorieanlage als Seitenpanels. Zeitkategorien können im Dropdown über (Neu) angelegt werden; Standard-Benutzer erhalten die gesonderte Berechtigung einmalig.
- Arbeitsbereich: Kunden mit aktiven Projekten, Projekt und Zeitkategorie auswählbar. Ein früheres offenes Arbeitsende wird zur Klärung angezeigt; zukünftige Tage erhalten keine laufende Stempelung.
- Provider: Zuordnungspunkte rot/blau/grün, nur eine Zuordnungsaktion pro Zeile, lokale Ticketstatusfilter, kein Ticket-Zeitraumfilter. Korrekte Zähler und Meldungen bei leeren gefilterten Listen. STARFACE-Menü prüft unbekannten Zugang vor dem Öffnen, erklärt fehlendes Client Secret und bietet bei abgelaufener Anmeldung die Verbindungseinstellungen an.

## Prüfung

Python-Regressionstests und bestehende JavaScript-Tests; zusätzlicher Integrationstest startet den echten Runtime-Stack mit einer isolierten Testdatenbank und lädt sämtliche Seitenskripte in jsdom. Er prüft Navigation, initiale Administration, Benutzeranlage, Rollen, Arbeitszeit, Kundenprojekte, Dashboard-Einstellungen, lokale Ticketfilter und Web-/Native-2FA. GitHub CI prüft zusätzlich MariaDB und beide Docker-Plattformen.

Es wurde keine visuelle Live-Browserprüfung auf dem Produktivsystem vorgenommen. SMTP wird lokal simuliert; eine Zustellung mit den tatsächlichen Zugangsdaten muss über den Testbutton geprüft werden. Produktive Zugangsdaten oder Richtlinien werden durch dieses Update nicht automatisch geändert; eine bereits aktivierte 2FA-Pflicht wird nun tatsächlich durchgesetzt.
