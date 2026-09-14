# Arbeitszeitmodelle und persönliche Soll-/Ist-Übersicht

## Einrichtung

Unter **Admin-Optionen → Arbeitszeitmodelle** einen Mitarbeiter auswählen. Tägliche, wöchentliche oder monatliche Sollstunden, Arbeitstage, Feiertagsregion und Gültigkeitsbeginn angeben. Die Adminrolle erhält die Berechtigung `staff.models.manage`; diese kann über die vorhandenen Rollen delegiert werden. Mitarbeiter können ihr eigenes Modell und die eigene Übersicht lesen, es aber nicht selbst ändern.

Das erste Modell darf rückwirkend beginnen. Weitere Änderungen gelten frühestens ab heute. Historische Modelle werden nicht überschrieben. Heutige und zukünftige Modelle können bearbeitet werden; eine Versionsprüfung schützt gegen veraltete Formulare. Änderungen werden protokolliert.

Bei einem Modellwechsel mitten im Monat wird jeder Tag nach dem an diesem Tag geltenden Modell berechnet. Die Verteilungsbasis des Monatsmodells bleibt jeweils der gesamte Kalendermonat. Der resultierende Übergangsmonat kann daher von beiden vollständigen Monatswerten abweichen.

## Berechnung

- Täglich: Der Sollwert gilt an jedem ausgewählten Wochentag.
- Wöchentlich: Der Sollwert verteilt sich gleichmäßig auf die ausgewählten Tage einer Montag–Sonntag-Woche.
- Monatlich: Der Sollwert verteilt sich auf alle ausgewählten Wochentage des konkreten Monats, einschließlich Feiertagen. Ganzzahlige Sekundenverteilung erhält den exakten Gesamtwert; Rundungsreste können Tageswerte um eine Sekunde unterscheiden.
- Feiertage: Der Sollwert eines vorgesehenen Arbeitstags wird nach Ablauf dieses Tages gutgeschrieben, gemäß Europe/Berlin. Es gibt keine vorgezogene Gutschrift. Tatsächliche Arbeit an diesem Tag kommt zusätzlich hinzu. Feiertage an ohnehin freien Tagen erzeugen keine Gutschrift.
- Arbeitszeit: Gestempelte Arbeitsblöcke abzüglich zugehöriger Pausen. Überlappungen werden vereinigt. Projekt- und Anbieterzeiten werden nicht zusätzlich als Mitarbeiterarbeitszeit gezählt.
- Offene Arbeitsblöcke: Anzeige bis zum aktuellen Zeitpunkt; für vergangene Tage mit vergessenem Arbeitsende bleibt die Differenz unbekannt.
- Fehlendes Modell: Soll und Differenz bleiben unbekannt, nicht null.

Feiertage stammen aus der fest versionierten Python-Bibliothek `holidays` 0.104 (DE, public). Örtliche Varianten für Bayern/Mariä Himmelfahrt, Sachsen und Thüringen/Fronleichnam verwenden zusätzlich die Kategorie catholic; Augsburg hat eine eigene Region. Die Administration wählt die am Arbeitsort zutreffende Variante. Die Daten werden lokal berechnet, ohne Providerabfragen beim Seitenaufruf.

## Anzeige

Unter **Zeiterfassung → Meine Arbeitszeit** Tag auswählen. Die Karten zeigen Tag, zugehörige vollständige Woche und Monat; die ausklappbare Tabelle zeigt die Tage des Monats. Das Soll ist jeweils das gesamte Periodensoll. Die Differenz berücksichtigt ausschließlich vergangene, vollständig gestempelte Tage, damit künftige Arbeitstage keine vorzeitigen Minusstunden erzeugen. Für heute wird angezeigt, wie viel noch bis zum Soll fehlt. Die aktuelle Tagesansicht aktualisiert sich bei Stempelaktionen und einmal pro Minute, solange sie sichtbar ist; versteckte Ansichten pollen nicht.

**Paketgrenze:** Urlaub, Krankheit, Überträge, Auszahlungen und verbindliche Monatsabschlüsse werden noch nicht berücksichtigt. Die Anzeige ist ausdrücklich noch kein abrechnungsfähiges Stundenkonto. Tage ohne Arbeit werden ohne Abwesenheitsgutschrift gegen das konfigurierte Soll gerechnet.

## Abnahme

1. Ein Modell mit 173 Monatsstunden, Montag–Freitag und zutreffender Region anlegen. Zwei Monate mit unterschiedlicher Arbeitstagezahl vergleichen.
2. Arbeit beginnen, pausieren, fortsetzen und beenden. Arbeitsstunden müssen sich unabhängig von Projektzeiten ergeben.
3. Vergangenen Feiertag auswählen: Tages-Soll wird gutgeschrieben; erfasste Arbeit ergibt ein Plus. Ein zukünftiger Feiertag darf noch keine Gutschrift haben.
4. Ein zukünftiges Modell erstellen und bearbeiten; frühere Tage müssen unverändert bleiben.
5. Als normaler Mitarbeiter die eigene Übersicht prüfen; fremde Modelle dürfen nicht geändert werden.

Automatische Tests decken Monats-/Wochenverteilung, Tagesmodelle, Feiertage, regionale Varianten, Pausen, Zeitumstellung, offene Arbeitsenden, Monatsgrenzen, fehlende Modelle, Berechtigungen, Versionskonflikte und produktive HTTP-Routen ab. DOM-Tests prüfen Formulare und Lade-/Fehlerzustände. Keine visuelle Live-Browser-Abnahme erfolgt.
