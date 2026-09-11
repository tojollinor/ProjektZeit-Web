# ProjektZeit Web 0.7.0

Webbasierte Zeiterfassung mit Kunden, Projekten, Zeitkategorien, bearbeitbaren Stempelungen und Tageszeitstrahl. Arbeitsbeginn/-ende begrenzen die Arbeitszeit; Lücken werden als „unproduktiv“ erfasst. Projektwechsel beendet den laufenden Timer atomar.

## Start

1. `.env.example` nach `.env` kopieren.
2. `APP_PUBLIC_URL` auf die tatsächliche Browser-Adresse setzen; Admin-, Datenbank- und Root-Passwort eintragen.
3. `docker compose pull` und `docker compose up -d` ausführen.

MariaDB 11.4 speichert die Daten dauerhaft im Volume `mariadb-data`. Der Schlüssel für Schnittstellen-Zugangsdaten bleibt im bisherigen Volume `projektzeit-data`. SQLite ist nur noch für lokale Tests und den Alt-Datenimport vorgesehen. Vor einem bestehenden Deployment unbedingt [Upgrade-Anleitung](UPGRADE-0.7.md) lesen.

## Schnittstellen

- STARFACE 10: Browser-Anmeldung mit OAuth 2.0 Authorization Code + PKCE, verschlüsselte Tokens und automatische Erneuerung bei einem API-Aufruf. Die angezeigte Rücksprungadresse muss beim STARFACE OAuth-Client freigegeben sein. Siehe [Upgrade und OAuth-Konfiguration](UPGRADE-0.7.md).
- TeamViewer: Script-Token mit Leserechten für Verbindungsberichte; kein Benutzername oder TOTP nötig.
- Zammad: Benutzername/Passwort über Basic Authentication, sofern auf der Instanz freigegeben.

Eigene Seiten für Zammad, STARFACE und TeamViewer enthalten durchsuchbare, klar gekennzeichnete Beispiellisten. „Echte Daten laden“ lädt für Administratoren TeamViewer-Verbindungen der letzten 30 Tage (maximal 100 angezeigt, mit Gerätenamen und Dauer) beziehungsweise bis zu 100 Zammad-Tickets mit Ticketnummer und Organisationsnamen. Ein Ticketklick öffnet die Ticketdetails und Nachrichten direkt in ProjektZeit. STARFACE prüft das aktuell angemeldete Konto über `/rest/users/me`; echte Anruflisten sind noch nicht umgesetzt. Beispiele erzeugen keine Stempelungen.

Compose verwendet die festen Containernamen `projektzeit-web` und `projektzeit-db`. Die Zeitzone wird für beide über `TZ=Europe/Berlin` in der separaten `.env` gesetzt. Bei mehreren Installationen auf demselben Docker-Host müssen die Containernamen angepasst werden.

## Windows-Client und App

Die API unter `/api/v1` unterstützt Bearer-Anmeldung, Ablauf und Widerruf. [API-Vertrag mit Beispielen](API-CLIENTS.md).

Ein nativer Windows-Client ist als WPF-Anwendung unter `windows-client/` enthalten. GitHub Actions baut daraus eine selbstständige Windows-EXE und veröffentlicht sie im Release `windows-client`. Der Client speichert den ProjektZeit-Sitzungstoken benutzergebunden mit Windows DPAPI, kann Arbeitsbeginn/-ende schreiben und die STARFACE-Verknüpfung per Browser-OAuth starten. Ein vollständiger nativer Projekt-Timer und Offlinebetrieb sind noch nicht umgesetzt. Eine Smartphone-App ist noch nicht enthalten.

## GitHub / Komodo

Repository: [tojollinor/ProjektZeit-Web](https://github.com/tojollinor/ProjektZeit-Web)

Image: `ghcr.io/tojollinor/projektzeit-web:latest`

Der Workflow testet SQLite, MariaDB und den Zeitstrahl, bevor er AMD64-/ARM64-Images baut und zu GHCR veröffentlicht. Für anonymen Pull das **Package** auf Public stellen.

In Komodo den Inhalt von `compose.yaml` als Stack verwenden und die ENV-Werte separat eintragen. Der Stack benötigt keine Änderungen an den Platzhaltern. `APP_PUBLIC_URL` konfiguriert die Rücksprungadresse; DNS und HTTPS-Reverse-Proxy werden separat eingerichtet.

Updates: `docker compose pull`, danach `docker compose up -d`. Stacknamen beibehalten, damit dieselben Volumes verwendet werden.

## Entwicklung

`python -m pip install -r requirements.txt`

`python -m unittest discover -s tests -p 'test_*.py'`

`node tests/timeline.cjs`

Mit `DB_BACKEND=sqlite`, `DEMO_MODE=1` und `ADMIN_PASSWORD=admin` ist ein isolierter lokaler Test möglich; kein Testzugang wird auf der Loginseite angezeigt. Für den regulären Compose-Stack gilt DEMO_MODE=0.

## Logo

Das enthaltene ProjektZeit-Logo wurde für dieses Projekt erstellt und stammt aus der bisherigen Windows-Anwendung.
