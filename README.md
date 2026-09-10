# ProjektZeit Web – Docker-Prototyp

**Direkt starten:** [GitHub-Download, Compose-Stack, ENV und Portainer](SCHNELLSTART.md).

Dieser Prototyp stellt eine responsive Weboberfläche und eine versionierte JSON-API unter `/api/v1` bereit. Benutzer, Sitzungen, Kunden, Projekte, Kategorien und Stempelungen werden in SQLite gespeichert. Daten jedes normalen Benutzers sind voneinander getrennt; nur Administratoren sehen die Benutzerverwaltung. Der Tageszeitstrahl zeigt alle Stempelungen in einer gemeinsamen Zeile mit zeitgetreuen Balken. Das Mausrad zoomt am Mauszeiger; die horizontale Scrollleiste verschiebt den sichtbaren Bereich. „Ganzer Tag“ setzt den Zoom zurück. Ein Klick auf einen Balken öffnet die Details. Historische Überschneidungen werden weiterhin als Konflikt gemeldet.

Der lokale Testzugang lautet `admin` / `admin`. Er wird nur akzeptiert, solange `DEMO_MODE=1` gesetzt ist.

## Arbeitstag und Projektwechsel (v0.5.0)

- **Arbeitsbeginn** öffnet die Arbeitszeit. Bis ein Projekt gestartet wird, läuft eine automatische Stempelung **unproduktiv**.
- Die Schnellwahl zeigt alle aktivierten Projekte. Ein Klick beendet das bisherige Projekt und startet das gewählte Projekt am selben Zeitpunkt. Es läuft höchstens ein Projekt pro Benutzer.
- **Projekt stoppen · unproduktiv** beendet das Projekt; die Arbeitszeit läuft weiter. **Arbeitsende** beendet sowohl das Projekt als auch die Arbeitszeit.
- Unter **Zeiterfassung → Aktive Projekte** können Projekte für die Schnellwahl ein- und ausgeschaltet werden. Ihre bisherigen Zeiten bleiben erhalten.
- **Bearbeiten** erlaubt bei abgeschlossenen Projektstempelungen Änderungen an Projekt, Kategorie, Start, Ende und Bemerkung. Überschneidungen werden abgewiesen. Innerhalb der zugehörigen Arbeitszeit werden unproduktive Lücken neu berechnet.
- Bei unproduktiven Stempelungen lässt sich eine Bemerkung ergänzen oder nach dem Ende ein Projekt für den ganzen Zeitraum oder einen Teil davon nachtragen. Bei laufenden Stempelungen ist nur die Bemerkung bearbeitbar.
- Arbeitsbeginn und Arbeitsende werden dauerhaft gespeichert, auch über Browser- und Server-Neustarts. Bereits vorhandene historische Stempelungen bleiben erhalten. Alte Überschneidungen werden nicht automatisch verändert und lassen sich über **Bearbeiten** korrigieren.

Das Datenbankschema wird beim Start additiv erweitert. Vor einem Versionswechsel die SQLite-Datenbank sichern.

## Einstellungen → Schnittstellen (v0.6.0)

Administratoren können für ihren eigenen ProjektZeit-Benutzer drei Verbindungen konfigurieren. Zugangsdaten anderer Benutzer werden nicht angezeigt oder verwendet. Jede Karte enthält Domain, Benutzername, Passwort bzw. Token sowie **Speichern**, **Debug · Verbindung testen** und **Verknüpfung entfernen**. Testen verwendet die aktuellen Eingaben, speichert sie aber nicht. Ein leeres Passwortfeld behält gespeicherte Zugangsdaten nur bei unveränderter Domain und unverändertem Benutzer bei.

- **TeamViewer:** Domain `https://webapi.teamviewer.com`, optional Benutzername als Kontobezeichnung, **Script-Token** statt Kontopasswort. Im Token unter **Verbindungsprotokollierung** Leserechte für Berichte vergeben. Der Test ruft `/api/v1/ping` und `/api/v1/reports/connections?limit=5` auf. Lizenz und Berechtigungen müssen den Zugriff erlauben. [Hersteller-Anleitung](https://www.teamviewer.com/en-us/global/support/knowledge-base/teamviewer-remote/for-developers/use-the-teamviewer-api/)
- **STARFACE:** Domain der Anlage, Login-ID und Passwort. REST-Challenge-Anmeldung über `/rest/login` mit `X-Version: 2`; anschließend Benutzerdaten über `/rest/users`. Interner Login und der dokumentierte Active-Directory-Secret-Aufbau sind vorgesehen. **Anrufzeiten werden hier noch nicht abgerufen:** Die passende UCI-/Anruflisten-Anbindung muss anhand der installierten STARFACE-Version ermittelt werden. [REST-Dokumentation](https://knowledge.starface.de/x/cpLGAg)
- **Zammad:** Domain, Benutzername und Passwort. Basic Authentication muss auf dem Zammad-Server erlaubt sein. Der Test liest `/api/v1/users/me` und `/api/v1/tickets?page=1&per_page=5`. Ticketrechte bestimmen die zugänglichen Daten. [Authentifizierung](https://docs.zammad.org/en/latest/api/intro.html)

Der Debug-Bericht zeigt HTTP-Status, Antwortzeiten, vorhandene Feldnamen, eine gefilterte Vorschau mit maximal fünf Datensätzen und eine Prüfung relevanter Felder. Passwörter, Authentifizierungstokens und vollständige Rohantworten werden nicht ausgegeben. Eine erfolgreiche Anmeldung ist kein Nachweis für vollständige Zeitdaten. Es werden keine Tickets, Anrufe oder Fernwartungen gestartet und keine Stempelungen automatisch importiert.

Nur HTTPS wird unterstützt; Zertifikate werden geprüft. Interne LAN-Adressen sind für lokale Installationen möglich, Loopback/Link-Local/reservierte Ziele und Weiterleitungen werden abgewiesen. Bei internen Zertifizierungsstellen deren CA auf dem Server bereitstellen (z. B. über `SSL_CERT_FILE` mit eingebundener CA-Datei). Die STARFACE muss vom Container aus erreichbar sein.

Zugangsdaten werden mit Fernet verschlüsselt in SQLite gespeichert. Der Schlüssel wird standardmäßig einmalig als `integration.key` im Datenvolume erzeugt. **Datenbank und Schlüssel gemeinsam sichern**, aber nie in GitHub hochladen. Alternativ einen stabilen Fernet-Schlüssel über `INTEGRATION_KEY` bereitstellen. Ein nachträglicher Schlüsselwechsel erfordert eine erneute Eingabe der gespeicherten Zugangsdaten. Die lokalen Tests verwenden simulierte API-Antworten; der Echtbetrieb muss mit den eigenen Instanzen und Zugangsdaten getestet werden.

## CSV-Import und -Export

In der Übersicht stehen die Schaltflächen **CSV importieren** und **CSV exportieren** bereit. Der Export enthält die Spalten `Kunde;Projekt;Zeitkategorie;Start;Ende;Dauer;Sekunden;Bemerkung;Art` und ist durch UTF-8-BOM sowie Semikolon-Trennung für deutsches Excel geeignet. Er enthält auch unproduktive Stempelungen. Beim Import werden Zeilen mit `Art=unproduktiv` übersprungen: Diese Zeit entsteht aus den in der Datenbank gespeicherten Arbeitszeiten. CSV ist daher ein Projektzeiten-Austauschformat, keine vollständige Datenbanksicherung.

Beim Import sind mindestens `Projekt`, `Start` und `Ende` erforderlich. Fehlende Kunden, Projekte und Zeitkategorien werden automatisch angelegt; vollständig identische Stempelungen werden übersprungen. Überschneidende Projektzeiten werden abgewiesen. Als Datum werden ISO-Zeitstempel und `TT.MM.JJJJ HH:MM:SS` akzeptiert. Zeitangaben ohne Zeitzone werden als Server-Ortszeit behandelt; für den Austausch zwischen Windows und Docker ISO-Zeitstempel mit Zeitzone verwenden. Pro Import sind maximal 900 KB vorgesehen.

## Auf GitHub veröffentlichen

1. Bei GitHub ein leeres Repository anlegen, am einfachsten mit dem Namen `projektzeit-web`.
2. Den Inhalt dieses Projektordners in das Repository hochladen und auf den Branch `main` pushen.
3. Unter **Actions** läuft automatisch `Docker-Image veröffentlichen`.
4. Das fertige Image erscheint unter **Packages** als `ghcr.io/DEIN-NAME/projektzeit-web:latest`.

Für Pulls ohne GitHub-Anmeldung muss das Package in dessen Einstellungen auf **Public** gestellt werden. Bei einem privaten Package meldet man den Docker-Server vorher mit einem GitHub-Token mit der Berechtigung `read:packages` an:

```powershell
$env:GITHUB_TOKEN | docker login ghcr.io -u DEIN-GITHUB-NAME --password-stdin
```

Die Action veröffentlicht Images für `linux/amd64` und `linux/arm64`. Ein Tag wie `v0.2.0` erzeugt zusätzlich die Versionstags `0.2.0` und `0.2`.

## Fertiges Image mit Compose laden

1. `.env.example` nach `.env` kopieren.
2. Ein eigenes Passwort mit mindestens zwölf Zeichen eintragen. `DEMO_MODE=0` und `SEED_DEMO=0` sind voreingestellt. Außerdem `PROJEKTZEIT_IMAGE` auf das eigene GHCR-Image ändern. Für einen ausschließlich lokalen Test kann stattdessen `.env.demo.example` als `.env` verwendet werden (`admin/admin`).
3. Auf dem Docker-Server im Projektordner ausführen:

```powershell
docker compose pull
docker compose up -d
```

4. `http://localhost:8080` öffnen und mit `ADMIN_USER` / `ADMIN_PASSWORD` anmelden.

Stoppen:

```powershell
docker compose down
```

Die SQLite-Daten bleiben im Docker-Volume `projektzeit-data` erhalten. `docker compose down -v` würde dieses Volume löschen und sollte nur bewusst verwendet werden.

Ein Update benötigt danach nur:

```powershell
docker compose pull
docker compose up -d
```

## Lokal selbst bauen

```powershell
Copy-Item .env.example .env
# .env bearbeiten: Image und Passwort setzen, bevor gebaut wird.
docker compose -f compose.yaml -f compose.build.yaml up --build -d
```

## Test ohne Docker

```powershell
$env:ADMIN_USER='admin'
$env:ADMIN_PASSWORD='admin'
$env:DEMO_MODE='1'
$env:DATA_DIR='.\data'
python -m pip install -r requirements.txt
python app.py
```

## Sicherheit vor einer Internetfreigabe

- Ausschließlich über HTTPS hinter einem Reverse Proxy veröffentlichen.
- `DEMO_MODE=0` und `APP_SECURE_COOKIE=1` setzen sowie ein individuelles starkes Admin-Passwort verwenden. `admin/admin` ist ausschließlich ein lokaler Testzugang.
- Den Container-Port im Compose-Beispiel zunächst nur an `127.0.0.1` binden.
- Regelmäßige Sicherungen des Docker-Volumes einrichten.
- Für eine öffentliche Produktivversion zusätzlich E-Mail-basierte Kontowiederherstellung, 2FA, Audit-Protokoll und einen externen Identity Provider (OIDC) ergänzen. Eine grundlegende Anmelde-Drosselung ist im Prototyp bereits enthalten.

Die API-Struktur ist als Grundlage für die spätere Smartphone-App vorgesehen. Für die App sollte die Anmeldung später auf kurzlebige Access-Tokens plus Refresh-Tokens oder OIDC erweitert werden.
