# ProjektZeit 0.7.4 – Gemeinsame Kunden und klare Verbindungszustände

- Kunden sind unternehmensweit sichtbar, wenn die Rolle Kundenzugriff erlaubt. Kontakt-, Verknüpfungs-, Bearbeitungs- und Verlaufsrechte werden separat geprüft, auch über persönliche API-Token. Persönliche Integrationszugänge und Providerarchive bleiben getrennt. Bestehende Kunden werden nicht automatisch zusammengeführt.
- Die Kundendetails zeigen unten einen Änderungsverlauf mit Bearbeiter, Datum und alten/neuen Werten. Neue Änderungen und ihr Audit-Eintrag werden gemeinsam gespeichert. Frühere Änderungen ohne Protokoll werden nicht nachträglich erfunden.
- Unter Adminoptionen stehen Unternehmensstammdaten und die Standard-Feiertagsregion. Neue Arbeitszeitmodelle verwenden diese Vorauswahl; vorhandene Mitarbeiterregionen bleiben erhalten.
- Zammad zeigt standardmäßig eigene Tickets. „Ohne Besitzer“ steht separat am Ende der Zuordnungsauswahl; unbekannte Besitzer gelten nicht als eigene oder unbesetzte Tickets. Verknüpfte Besitzer erscheinen mit dem ProjektZeit-Benutzernamen in Tabelle und Detailansicht. Die Identität wird über die verknüpfte Zammad-Anmelde-E-Mail derselben Instanz bestimmt.
- Alle drei Providertabellen bieten einen Spalteneditor zum Ein-/Ausblenden, Sortieren und Ändern der Breite. Einstellungen gelten je Benutzer, Anbieter und Gerät. Mobile Karten bleiben schmal und zeigen den Ticketbesitzer.
- STARFACE, TeamViewer und Zammad öffnen bei fehlender Verbindung einen erklärenden Dialog. Die Einstellungen lassen sich darüber direkt öffnen. STARFACE unterscheidet fehlendes zentrales Client Secret und fehlende persönliche Verbindung. Ohne Verbindung werden keine archivierten Telefonate angezeigt; die Daten bleiben gespeichert.
- TeamViewer-Einstellungen verlinken zur Token-Erstellung und erklären das benötigte Leserecht für Verbindungseinträge sowie die Lizenzabhängigkeit. Fehlgeschlagene Tests behaupten nicht, dass Datenfelder bereits geprüft wurden.
- Sitzungsverlauf ist standardmäßig eingeklappt. Import & Export enthält wieder die Import-/Exportaktionen. Benutzerstatus wird per Dropdown und Speichern geändert; 2FA-Rücksetzen steht daneben im gleichen Buttonstil. Rollen und Richtlinien haben bedienbare Hilfetexte. Nur vorbereitete, noch nicht durchgesetzte Richtlinien sind ausdrücklich als noch nicht aktiv gekennzeichnet und gesperrt.
- Arbeitszeitkorrekturen übernehmen den ausgewählten Tag. Mitarbeiterabrechnung steht unter Buchhaltung. Projekt-Zeitstrahl heißt „Übersicht“. Rückrufbuttons stehen nebeneinander rechts; Benachrichtigungen haben einen größeren, zuverlässig bedienbaren Schließen-Button. Farbfelder zeigen eine gefüllte Vorschau; angezeigte Zeitstempel sind auf Deutsch und Europe/Berlin formatiert.
- Die globale Überschreibung der Browser-MutationObserver-API wurde entfernt, damit Browserintegrationen die ursprünglichen Ereignisse erhalten. Ein echter Bitwarden-Test bleibt nach Installation erforderlich.

## Prüfung

Lokale Python-, HTTP-/DOM- und JavaScript-Tests prüfen unter anderem globale Kunden und eingeschränkte API-Antworten, Benutzeranlage und Deaktivierung, Rollen, Unternehmensregionen, Spalteneditor ohne zusätzliche Providerabrufe, Navigation bei fehlender Verbindung, direkte Zeitkorrekturen mit Pausen/Verlauf, Kalender und 2FA. Die Release-CI prüft zusätzlich MariaDB und den Docker-Build für AMD64/ARM64.

Direkter Browserzugriff steht in dieser Sitzung nicht zur Verfügung. Eine erneute visuelle Live-Prüfung von Desktop/Mobil, Dark/Light und Bitwarden kann deshalb noch nicht bestätigt werden. Echte Providerzugänge und SMTP-Zustellung wurden nicht erneut getestet; automatische Ereignis-E-Mails bleiben unaktiviert. Es wurden keine echten E-Mails oder Auszahlungen ausgelöst.

Das Update ist erst nach grüner PR-CI und erfolgreicher Veröffentlichung des Main-Docker-Images bereit. Die Instanz wird anschließend vom Betreiber aktualisiert.
