# ProjektZeit Web 0.8.0

Webbasierte Zeiterfassung mit Kunden, Projekten, Zeitkategorien, bearbeitbaren Stempelungen und Tageszeitstrahl. Arbeitsbeginn/-ende begrenzen die Arbeitszeit; Lücken werden als „unproduktiv“ erfasst. Projektwechsel beendet den laufenden Timer atomar.

## Start

1. `.env.example` nach `.env` kopieren.
2. `APP_PUBLIC_URL` auf die tatsächliche Browser-Adresse setzen; Admin-, Datenbank- und Root-Passwort eintragen.
3. `docker compose pull` und `docker compose up -d` ausführen.

MariaDB 11.4 speichert die Daten dauerhaft im Volume `mariadb-data`. Der Schlüssel für Schnittstellen-Zugangsdaten bleibt im bisherigen Volume `projektzeit-data`. SQLite ist nur noch für lokale Tests und den Alt-Datenimport vorgesehen. Vor einem bestehenden Deployment unbedingt [Upgrade-Anleitung](UPGRADE-0.7.md) lesen.

## Schnittstellen

- STARFACE 10: OAuth 2.0 Authorization Code + PKCE. STARFACE-Adresse, Client-ID und Client-Secret werden in der ProjektZeit-Weboberfläche konfiguriert und serverseitig verschlüsselt gespeichert. Der Windows-Client übernimmt nur den lokalen Loopback-Callback. Access- und Refresh-Token liegen anschließend ebenfalls verschlüsselt auf dem Server und können ohne laufenden Windows-Client weiterverwendet werden. Siehe [Upgrade und OAuth-Konfiguration](UPGRADE-0.7.md).
- TeamViewer: Script-Token mit Leserechten für Kontoinformationen und Verbindungsberichte; kein Benutzername oder TOTP nötig. Die Verbindungsdiagnose gleicht Konto, Unternehmensprofil, Lizenz und die letzten 30 Tage der Berichte direkt mit der API ab. Der persönliche TeamViewer-Schalter unter **Einstellungen → Verbindungsprotokolle** ist nicht Bestandteil der öffentlichen API und muss bei fehlenden Berichten im TeamViewer-Konto kontrolliert werden.
- Zammad: Benutzername/Passwort über Basic Authentication, sofern auf der Instanz freigegeben.

Eigene Seiten für Zammad, STARFACE und TeamViewer enthalten durchsuchbare
Arbeitslisten und lokale Archive. Zammad gilt beim vollständigen Abgleich als
führender Bestand; persönliche Ticketlisten enthalten nur tatsächlich
zugeordnete Tickets. STARFACE-Anruflisten erkennen anhand des gelieferten
Verlaufs erfolgreiche Rückrufe und
schließen dazugehörige ältere verpasste Anrufe. Providerdaten erzeugen keine
Stempelungen, bis sie bewusst einem Projekt zugeordnet werden.

Compose verwendet die festen Containernamen `projektzeit-web` und `projektzeit-db`. Die Zeitzone wird für beide über `TZ=Europe/Berlin` in der separaten `.env` gesetzt. Bei mehreren Installationen auf demselben Docker-Host müssen die Containernamen angepasst werden.

## Windows-Client und App

Die API unter `/api/v1` unterstützt Bearer-Anmeldung, Ablauf und Widerruf. [API-Vertrag mit Beispielen](API-CLIENTS.md).

Ein nativer Windows-Client ist als WPF-Anwendung unter `windows-client/` enthalten. GitHub Actions baut daraus eine selbstständige Windows-EXE und veröffentlicht sie im Release `windows-client`. Der Client startet die ProjektZeit-Anmeldung mit Authorization Code und PKCE im Standardbrowser, speichert den daraus erzeugten Sitzungstoken benutzergebunden mit Windows DPAPI und unterstützt Arbeitsbeginn/-ende, Pausen sowie Projektstart, -wechsel und -stopp. Ein ProjektZeit-Passwort wird im Client nicht mehr eingegeben.

Beim manuellen Start registriert beziehungsweise aktualisiert die portable EXE den URI-Handler `projektzeit://` für ihren aktuellen Speicherort. Dadurch kann die Weboberfläche mit **STARFACE verbinden** den Client direkt öffnen. Der Handler verweist immer nur auf die lokale EXE; Client-Secret, STARFACE-Passwort und OAuth-Tokens werden niemals in den URI geschrieben. Ein späterer Installer kann denselben Handler auf seinen Installationspfad umstellen.

Offlinebetrieb und eine Smartphone-App sind nicht enthalten.

## GitHub / Komodo

Repository: [tojollinor/ProjektZeit-Web](https://github.com/tojollinor/ProjektZeit-Web)

Image: `ghcr.io/tojollinor/projektzeit-web:latest`

Der Workflow testet SQLite, MariaDB und den Zeitstrahl, bevor er AMD64-/ARM64-Images baut und zu GHCR veröffentlicht. Für anonymen Pull das **Package** auf Public stellen.

In Komodo den Inhalt von `compose.yaml` als Stack verwenden und die ENV-Werte separat eintragen. Der Stack benötigt keine Änderungen an den Platzhaltern. `APP_PUBLIC_URL` wird unter anderem für den sicheren `projektzeit://`-Startlink benötigt; DNS und HTTPS-Reverse-Proxy werden separat eingerichtet.

Updates: `docker compose pull`, danach `docker compose up -d`. Stacknamen beibehalten, damit dieselben Volumes verwendet werden.

## E-Mail und Kontosicherheit

SMTP wird unter **Admin-Optionen → E-Mail / SMTP** eingerichtet. `APP_PUBLIC_URL` muss auf die öffentlich im Browser verwendete ProjektZeit-Adresse zeigen, damit Einmal-Links für E-Mail-Bestätigung und Passwort-Wiederherstellung erzeugt werden können. Danach lassen sich unter **Richtlinien** Sicherheitsmails, E-Mail-Verifizierung sowie numerische oder alphanumerische E-Mail-Codes als zweite Anmeldestufe konfigurieren. 2FA kann optional, für alle Benutzer oder nur für ausgewählte Rollen gelten.

Die zentrale E-Mail-Vorlage lässt sich dort mit Unternehmensname, Logo, Primär-/Akzentfarbe und Fußzeile gestalten, direkt als Desktop-/Mobilvorschau prüfen und per Testmail versenden. Zusätzlich werden Passwort-Historie und -Ablauf, Anmeldesperre sowie Inaktivitäts- und maximale Sitzungsdauer serverseitig durchgesetzt. Als zweite Faktoren stehen TOTP über eine Authenticator-App und E-Mail-Codes zur Verfügung.

Administratoren vergeben bei neuen Benutzern ein vorläufiges Passwort und können einen verpflichtenden Wechsel bei der nächsten Anmeldung setzen. Passwörter werden nie per E-Mail versendet. E-Mail-Codes sind kurzlebig und nur einmal verwendbar; zur Prüfung liegt ausschließlich ihr Hash vor, während ausstehende Nachrichten bis zum Versand verschlüsselt im Datenvolume gespeichert werden.

## Entwicklung

`python -m pip install -r requirements.txt`

`python -m unittest discover -s tests -p 'test_*.py'`

`node tests/timeline.cjs`

Mit `DB_BACKEND=sqlite`, `DEMO_MODE=1` und `ADMIN_PASSWORD=admin` ist ein isolierter lokaler Test möglich; kein Testzugang wird auf der Loginseite angezeigt. Für den regulären Compose-Stack gilt DEMO_MODE=0.

## Logo

Das enthaltene ProjektZeit-Logo wurde für dieses Projekt erstellt und stammt aus der bisherigen Windows-Anwendung.

Die vollständigen Änderungen dieser Version stehen in [UPDATE-0.8.0.md](UPDATE-0.8.0.md).
