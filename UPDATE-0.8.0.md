# ProjektZeit 0.8.0 – konsistente Arbeitsbereiche und Windows-Client

Dieses Update bündelt die überarbeiteten Projekt-, Zeit-, Abrechnungs- und
Administrationsabläufe und ergänzt einen neu gestalteten nativen Windows-Client.

## Oberfläche und mobile Nutzung

- Haupt- und Unterseiten besitzen stabile URL-Pfade. Nach speichernden
  Stammdatenänderungen wird dieselbe Seite neu geladen; aktive Menüeinträge und
  Reiter bleiben dadurch eindeutig.
- Unterbereiche wie Projekte, Buchhaltung, Einstellungen und Admin-Optionen
  verwenden kompakte, einheitliche Reiter. Navigation, Einrückungen,
  Panelabstände und Aktionsbutton-Größen folgen einem gemeinsamen Raster.
- Die mobile Kalenderansicht nutzt eine eigene Tagesagenda statt eines
  zusammengedrückten Desktop-Rasters. Navigation, Filter und Aktionen brechen
  auf kleinen Displays kontrolliert um. Arbeitszeit-, Pausen- und
  Projektkalendereinträge öffnen dieselbe ausführliche Tagesansicht wie die
  Zeiterfassung.
- Zammad-, STARFACE- und TeamViewer-Zeilen zeigen je Darstellungsmodus genau
  einen Farbpunkt für die Zuordnungsqualität. Kachel- und Listenansichten sowie
  Aktionsspalten bleiben auf Mobilgeräten plausibel ausgerichtet.
- Sämtliche Zeitstrahlen lassen sich am Desktop mit dem Mausrad und mobil per
  Zwei-Finger-Geste zoomen. Der Zeitpunkt unter Mauszeiger beziehungsweise
  Fingermitte bleibt beim Zoomen erhalten.

## Projekte, Kunden und Zuordnung

- Der Projektbereich beginnt mit der Projektübersicht; Zeitvergleich und Tags
  liegen daneben in der Reiterleiste. Neue Projekte und Kunden werden über
  kompakte `+`-Aktionen in Dialogen angelegt.
- Wo ein Kunde oder Projekt zugeordnet wird, steht die passende Anlageaktion
  unmittelbar neben dem Auswahlfeld zur Verfügung.
- Während eines begonnenen Arbeitstags kann ein Projekt über einen kompakten
  Dialog gestartet oder gewechselt werden. Laufende Projekte bleiben bis zum
  Abschluss unberücksichtigt; abgeschlossene Projektzeit fließt in das
  Stundenkonto ein.
- Die Kundenübersicht kann dauerhaft zwischen Kacheln und einer Detailliste
  umgeschaltet werden.

## Arbeitszeit und Abrechnung

- Bereits geleistete, abgeschlossene Zeiten können auch ohne hinterlegtes
  Arbeitszeitmodell abgerechnet werden. Das Modell liefert das Soll, ist aber
  keine Voraussetzung für tatsächlich geleistete Stunden.
- Die Richtlinie `Minussaldo nach Auszahlung erlauben` steuert, ob eine
  Auszahlung das Stundenkonto unter null führen darf.
- Gespeicherte Arbeitszeitmodelle lassen sich bearbeiten oder löschen, solange
  ihr Wirkungszeitraum keinen abgeschlossenen Abrechnungsmonat berührt.
- Mitarbeiterabrechnung, Monatsabschluss, Kontobuchungen und Tagesdetails sind
  zu belastbaren Arbeitsansichten ausgebaut. Statusaktionen behalten auch bei
  Textwechseln ihre Größe und stehen tabellarisch in einer Flucht.

## Integrationen

- Zammad ist für den lokalen Ticketbestand führend. Vollabgleiche entfernen
  lokal nicht mehr gelieferte Tickets; Tickets ohne Besitzer erscheinen nicht
  in persönlichen Arbeitslisten.
- Ein späterer, von STARFACE gelieferter erfolgreich angenommener Rückruf
  schließt alle älteren verpassten Anrufe derselben normalisierten Rufnummer
  automatisch. ProjektZeit berücksichtigt den vom Anbieter gelieferten
  `calledBack`-Status; manuelle Rückrufmarkierungen werden lokal gespeichert.
  Ein nicht öffentlich dokumentierter Schreibaufruf an STARFACE wird bewusst
  nicht geraten.
- Die TeamViewer-Verbindung erklärt die clientseitige Sitzungserfassung und
  prüft per API Konto, Unternehmensprofil, Lizenz sowie aktuelle
  Verbindungsberichte, soweit TeamViewer diese Daten freigibt.
- Einstellungen für automatische Unternehmensabgleiche stehen nur noch unter
  Admin-Optionen und nicht zusätzlich in persönlichen Verbindungen.

## Konten und Sicherheit

- Nicht angemeldete oder abgelaufene Sitzungen führen sofort zur Loginseite und
  merken sich die aktuelle URL für die Rückkehr nach erfolgreicher Anmeldung.
- Sind TOTP und E-Mail-2FA eingerichtet, kann die Methode bei jeder Anmeldung
  gewählt werden. Beide Methoden lassen sich in den persönlichen Einstellungen
  wieder entfernen.
- Benutzer und das eigene Konto können gelöscht werden. Arbeits- und
  Abrechnungsbelege bleiben revisionssicher, während Zugang, Sitzungen, Tokens
  und persönliche Profildaten entfernt beziehungsweise anonymisiert werden.
  Ausschließlich das über `ADMIN_USER` konfigurierte Notfallkonto ist geschützt.

## Windows-Client

- Der WPF-Client wurde als moderne Arbeitsoberfläche für Arbeitsbeginn/-ende,
  Pausen, Projektwahl, Projektwechsel, Projektstopp, Status und STARFACE neu
  aufgebaut.
- Die Anmeldung erfolgt im Standardbrowser mit Authorization Code und PKCE
  S256: Server eingeben, **Im Browser anmelden** wählen, Weblogin samt 2FA
  abschließen und Zugriff bestätigen. Der Client erhält kein Passwort.
- Die Rückleitung bindet ausschließlich an einen zufälligen lokalen Port. Codes
  sind einmalig und kurzlebig; Sitzungstokens werden benutzergebunden mit
  Windows DPAPI gespeichert.
- Pull Requests bauen die EXE als CI-Artefakt. Veröffentlichungen auf `main`
  aktualisieren zusätzlich den Download im Release `windows-client`.

## Betrieb und Migration

Die Migration ergänzt Tabellen für einmalige Client-Autorisierungscodes und
nachvollziehbare Kontolöschungen. Bestehende Arbeitszeiten, Projekte,
Abrechnungsabschlüsse, Providerarchive und Zuordnungen bleiben erhalten.

Vor dem Update Datenbank und Datenverzeichnis gemeinsam sichern. Für den
Browserlogin des Windows-Clients muss ProjektZeit über eine gültige
HTTPS-Adresse erreichbar sein. Eine Live-Abnahme der installierten Instanz oder
echte Provideraufrufe gehören bewusst nicht zu den lokalen Codeprüfungen.


## STARFACE-Rückrufstatus

- Manuelles „als zurückgerufen markieren“ wird jetzt über die offizielle UCI-Methode `setCallListEntryCalledBack` an STARFACE zurückgeschrieben; lokal wird erst nach erfolgreicher Serverbestätigung quittiert.
