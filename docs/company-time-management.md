# Verbindlicher Umsetzungsumfang

Freigabe: Benutzer hat nach Sammelphase ausdrücklich Umsetzung beauftragt.
Basis: main 226bbe12f831f6998c43ae6140606e4c50c20c90.

## Akzeptanzkriterien

- Projekte: eigene Projektzeiterfassung, Providerzuordnungen, eindeutige automatische Kundenzuordnung, Detaildialog zuerst; bestehendes/neues Projekt, Kundenverknüpfungen verwaltbar, zeitbezogene Vorschläge, keine doppelten Zeiten.
- Zeiterfassung: persönliche Arbeitsstempel, Pausen und Projektblöcke ohne technische Rohereignisse; Zeitkonto, Soll/Ist und Ansichten.
- Arbeitszeitmodell: pro Mitarbeiter ab Datum, tägliches/wöchentliches/monatliches Soll, Arbeitstage und Gewichtung; Monatsverteilung schließt Feiertage ein; Gutschrift erst am abgeschlossenen Tag, Feiertagsarbeit zusätzlich; Sekunden ohne Rundungsverlust.
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
