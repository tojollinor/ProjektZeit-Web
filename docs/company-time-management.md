# Verbindlicher Umsetzungsumfang

Freigabe: Benutzer hat nach Sammelphase ausdrücklich Umsetzung beauftragt.
Basis dieses Gesamtpakets: main 0fde712a090af81c0bb2c67b1ec954543c84ca38.

## Akzeptanzkriterien

- Projekte: eigene Projektzeiterfassung, Providerzuordnungen, eindeutige automatische Kundenzuordnung, Detaildialog zuerst; bestehendes/neues Projekt, Kundenverknüpfungen verwaltbar, zeitbezogene Vorschläge, keine doppelten Zeiten.
- Zeiterfassung: persönliche Arbeitsstempel, Pausen und Projektblöcke ohne technische Rohereignisse; Zeitkonto, Soll/Ist und Ansichten.
- Arbeitszeitmodell: pro Mitarbeiter ab Datum, tägliches/wöchentliches/monatliches Soll, ausgewählte, gleichmäßig gewichtete Arbeitstage; Monatsverteilung schließt Feiertage ein; Gutschrift erst am abgeschlossenen Tag, Feiertagsarbeit zusätzlich; Sekunden ohne Rundungsverlust.
- Abwesenheiten: bezahlter Urlaub, unbezahlt und Zeitausgleich; ganze Tage/Stunden, Jahresanspruch, Rest-/Vorschau; eigene Tagesarten mit Regeln; Konflikte, Krankheit vor Urlaub ohne doppelte Gutschrift.
- Freigaben: konfigurierbare Genehmigung; Fremdeinträge vom Mitarbeiter bestätigen; Rollen inkl. separater Eigengenehmigung; sichtbare Richtlinien, offene Anträge behalten Regelversion; Storno (auch teilweise/rückwirkend) durch Mitarbeiter beantragt und genehmigt, keine erfundene Arbeitszeit.
- Korrekturen: gesperrt/Antrag/direkt, revisionsfähiger Verlauf, abgeschlossene Monate nur mit Korrekturbuchung.
- Buchhaltung: Mitarbeiterkonto und Kundenabrechnung unabhängig; Auszahlungen, Monatsabschluss, Pflicht-Leistungstext gegliedert nach Leistungsdatum/Nachname/Vorname, keine automatische Rechnung.
- Kalender: Tag/Woche/Monat/Liste, Filter, Details, Abwesenheit anderer ohne Grund, Zugriff auf andere Arbeitsdaten rollenabhängig.
- Notdienst: wiederholender Plan nach Reihenfolge/Intervall, Wochen-/Tages-/Stundentausch bestätigt, Rotation bleibt; KEINE kurzfristigen Übergaben; Kennzeichnung bis zur Abrechnung, Geschäftszeiten nur Vorschlag.
- Tags: global/kundenspezifisch, Mehrfachzuordnung ohne Doppelsumme, archivieren/umbenennen/zusammenführen; optionale Projektvorlage/Kopie ohne alte Aktivitäten. KEINE Budgets.
- Zeitkategorien: frei verwaltbar, Büro/außerhalb/ungeklärt, Fernwartung Büro als Vorgabe; Zeitabschnitte und Tagesauswertung außerhalb >8h ohne automatische Spesenzusage.
- Provider: dauerhafter zentraler Abgleich ohne geöffnete UI, inkrementell/Lückenkontrolle, Benutzerrechte; TeamViewer UNTERNEHMENSWEIT 3600 einzelne Requests im rollenden 24h-Fenster, persistent und instanzübergreifend; Tag/Nacht, Reserven, Rate-Limit-Wartezeiten, fair, kein Doppeljob; STARFACE/Zammad Limits unbekannt konfigurierbar, nicht unbegrenzt.
- Werkstatt: deaktivierte isolierte Tests mit Start/Stop/Laufzeit/Speichergrenze, bereinigte Logs, keine Buchungen; tatsächliche Provider-Livefähigkeit wird nicht vorausgesetzt.
- Bedienung: relevante Aktionsbuttons gesperrt+Spinner, bestätigt grün 3s/Fehler rot 4s, Fehler bleibt, Eingaben erhalten; unsicherer Speicherstatus separat; serverseitige Duplikatvermeidung.
- Fehlerbilder: Admin null.classList, Zammad Offen zeigt geschlossen, mobile abgeschnittene Texte/Abstände.
- Betrieb: konkrete automatisierte HTTP/DOM/Rechte/Kollision/DST/Migrations-/MariaDBtests, Wiederherstellungsanleitung, Änderungs-/Kontobuchungen nachvollziehbar; Branch→PR→grüne CI→Merge→grüner Main-Publish.

Keine Live-Browser-Abnahme behaupten, solange sie nicht tatsächlich durchgeführt wurde.

## Bedienung und Einrichtung des Gesamtpakets

1. Arbeitszeitmodelle unter Admin-Optionen einrichten. Unter Mitarbeiter & Arbeitszeit Urlaubsansprüche und Richtlinien setzen. Es gibt keine pauschal erfundenen Anfangssalden: diese bucht die Buchhaltung mit Begründung.
2. Zeiterfassung zeigt Stempelungen oder Konto für Tag, Woche und Monat. `staff.view` erlaubt den Mitarbeiterwechsel; Stempelaktionen bleiben persönlich. Projektaktivitäten liegen unter Projekte, Tagesdetails zeigen deren Namen ohne Provider-Rohdaten.
3. Urlaub und unbezahlte Abwesenheit werden im Dialog beantragt. Offene Anträge reservieren Urlaub, erzeugen aber noch keine Stunden. Unter Buchhaltung → Urlaub & Abwesenheiten prüfen berechtigte Personen die Anträge. Fremdeinträge benötigen immer die Bestätigung des Mitarbeiters. Eigengenehmigung benötigt sowohl Rollenrecht als auch Richtlinie.
4. Buchhaltung zeigt Leistungstexte, Stundenauszahlung und Monatsprüfung. Ein abgeschlossener Monat bleibt eingefroren. Später genehmigte Abwesenheitsänderungen erzeugen eine nachvollziehbare Differenzbuchung zum aktuellen Datum.
5. Kalender zeigt Arbeitszeit, Pausen, Projekte, Abwesenheiten und Notdienst. Andere Mitarbeiter sehen bei Abwesenheit keinen Grund. Filter arbeiten mit den bereits geladenen Daten. Rotationen werden über namentliche Mitarbeiter in Reihenfolge eingerichtet; einzelne Zeiträume können durch bestätigten Tausch wechseln.
6. Der automatische Providerabgleich läuft unabhängig von geöffneten Seiten. Das Budget zählt tatsächliche Datenabfragen für alle Mitarbeiter gemeinsam. Erstabgleich, wöchentliche Vollabgleiche und Wiederanlauf nach längerer Lücke ergänzen inkrementelle Abfragen. Harte Laufzeit- und Abfragegrenzen können umfangreiche Archive begrenzen; fehlgeschlagene Jobs behalten den lokalen Cache.

## Betrieb und Abnahmegrenzen

Vor dem Update Datenbank und Datenverzeichnis gemeinsam sichern. Bei SQLite gehört `provider-budget.sqlite3` dazu; bei MariaDB liegen Budgettabellen in derselben Datenbank. Das bisherige Image mit seinem konkreten SHA aufbewahren. Rückkehr zum alten Stand nur zusammen mit der dazugehörigen Datenbanksicherung durchführen, damit neue Buchungen nicht unbemerkt verloren gehen.

Automatisierte Tests prüfen Geschäftslogik, Berechtigungen, Rückdatierung, DOM-Interaktionen und die vorhandenen HTTP-Routen; CI führt zusätzlich MariaDB-Tests und beide Containerarchitekturen aus. Dies ersetzt keine visuelle Browserabnahme auf den Zielgeräten. Echte Provider-Echtzeitereignisse, Windows-Push und mobile Push-Nachrichten sind nicht verifiziert oder als verfügbar ausgewiesen. Werkstattprüfungen sind bewusst begrenzte API-Diagnosen. Eine steuerliche Spesenberechnung erfolgt nicht; ausgewertet werden erfasste Einsatzzeiten außerhalb.
