# ProjektZeit Web 0.6.0 – GitHub, Docker und Portainer

## 1. Einmalig auf GitHub hochladen

Das Paket enthält den Quellcode und die Container-Bauanleitung, kein bereits gebautes Image. GitHub baut das Image nach dem Upload automatisch. Alles ist auf `tojollinor/projektzeit-web` vorbereitet. Es wurde hier noch nichts zu GitHub hochgeladen; die Links funktionieren erst nach dem Upload, Image-Pulls erst nach erfolgreichem Build und passender Package-Freigabe.

1. [Neues GitHub-Repository erstellen](https://github.com/new), empfohlen: `projektzeit-web`, Branch `main`.
2. ZIP entpacken. Den **Inhalt** einschließlich `.github/workflows/docker-publish.yml`, `.env.example` und `.dockerignore` in die Repository-Wurzel hochladen, nicht das ZIP oder einen übergeordneten Ordner. Am einfachsten mit GitHub Desktop oder Git. Niemals lokale `.env`, Datenbanken oder `integration.key` hochladen; das Downloadpaket enthält diese nicht.
3. Unter **Actions → Docker-Image veröffentlichen** den erfolgreichen Durchlauf abwarten. Python- und Zeitstrahltests laufen vor dem Image-Build. Gebaut wird für AMD64 und ARM64.
4. Das Package unter **Packages → Package settings → Change visibility** auf **Public** stellen, wenn es ohne Anmeldung herunterladbar sein soll. Ein öffentliches Repository allein genügt hierfür nicht.
5. Über ein Git-Tag `v0.6.0` kann zusätzlich ein festes Image-Tag `0.6.0` veröffentlicht werden. `latest` wird bei Push auf `main` aktualisiert.

## 2. Schnellliste der Links

Die Links sind für dein Repository `tojollinor/projektzeit-web` fertig eingetragen.

- [Repository](https://github.com/tojollinor/projektzeit-web)
- [Gesamten Quellcode als ZIP herunterladen](https://github.com/tojollinor/projektzeit-web/archive/refs/heads/main.zip)
- [Compose-Stack herunterladen](https://raw.githubusercontent.com/tojollinor/projektzeit-web/main/compose.yaml)
- [ENV-Vorlage herunterladen](https://raw.githubusercontent.com/tojollinor/projektzeit-web/main/.env.example)
- [Build-Status auf GitHub](https://github.com/tojollinor/projektzeit-web/actions)

Image: `ghcr.io/tojollinor/projektzeit-web:latest`

## 3. Auf dem Docker-Server herunterladen und starten

Voraussetzung: Docker Engine und Docker Compose v2. Folgende Befehle für Linux in einem **neuen, leeren Ordner** ausführen. Die Download-URLs gelten für ein öffentliches Repository; für ein privates Repository die Dateien über einen angemeldeten GitHub-Download beziehen.

```bash
mkdir projektzeit-deploy
cd projektzeit-deploy
curl -fL https://raw.githubusercontent.com/tojollinor/projektzeit-web/main/compose.yaml -o compose.yaml
curl -fL https://raw.githubusercontent.com/tojollinor/projektzeit-web/main/.env.example -o .env
chmod 600 .env
nano .env
```

In `.env` mindestens Image und Passwort anpassen. Ohne Passwort verweigert Compose den Start. Ein eigenes Passwort mit mindestens zwölf Zeichen verwenden; bei `$` und `#` den Wert in einfache Anführungszeichen setzen, z. B. `ADMIN_PASSWORD='dein-individuelles-Passwort'`.

```bash
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

Auf dem Docker-Host: [ProjektZeit öffnen](http://localhost:8080). Von einem anderen Rechner funktioniert `localhost` nicht; siehe BIND_ADDRESS unten. Windows: die beiden Links im Browser herunterladen, ENV-Datei `.env` nennen, bearbeiten und dieselben Docker-Befehle im Downloadordner ausführen.

## 4. ENV-Einstellungen

| Variable | Standard / Bedeutung |
| --- | --- |
| PROJEKTZEIT_IMAGE | `ghcr.io/tojollinor/projektzeit-web:latest` |
| ADMIN_USER | `admin`; Administratorkonto beim ersten Anlegen |
| ADMIN_PASSWORD | Pflichtfeld, mindestens zwölf Zeichen bei DEMO_MODE=0 |
| DEMO_MODE | `0`; `1` erlaubt das schwache lokale Testpasswort |
| SEED_DEMO | `0`; `1` legt Beispieldaten für neu erzeugte Admin-Konten an |
| BIND_ADDRESS | `127.0.0.1`: nur Docker-Host; `0.0.0.0`: Zugriff über Server-IP, Firewall beachten |
| HTTP_PORT | `8080`: Port auf dem Docker-Host |
| APP_SECURE_COOKIE | `0` für lokalen HTTP-Test; bei HTTPS auf `1` stellen |
| TZ | `Europe/Berlin`: Ortszeit für zeitzonenlose CSV-Zeitangaben; intern UTC |
| INTEGRATION_KEY | Leer lassen: Schlüssel wird dauerhaft im Datenvolume erzeugt. Optional stabilen Fernet-Schlüssel setzen |

**Wichtig:** ADMIN_PASSWORD initialisiert das Konto, ändert aber nicht nachträglich dessen gespeichertes Passwort. Eine vorhandene Demo-Datenbank wird durch DEMO_MODE=0 nicht automatisch sicher. Bestehende schwache Passwörter vor Freigabe in der Benutzerverwaltung ändern.

## 5. Portainer-Stack (Docker Standalone, nicht Swarm)

1. **Stacks → Add stack**, Name `projektzeit`.
2. Inhalt von `compose.yaml` in den Web-Editor kopieren.
3. Unter **Environment variables** die Werte aus `.env.example` eintragen bzw. die angepasste Datei laden. Image und eigenes Admin-Passwort sind Pflicht. Kein ENV-Passwort in das öffentliche GitHub-Repository schreiben.
4. Für einen LAN-Test BIND_ADDRESS auf die LAN-IP des Docker-Hosts oder `0.0.0.0` setzen und den Zugriff per Firewall auf vertrauenswürdige Rechner begrenzen.
5. **Deploy the stack**; anschließend `http://SERVER-IP:8080` öffnen. Für Internetzugriff HTTPS-Reverse-Proxy verwenden und APP_SECURE_COOKIE=1 setzen. Ein Proxy in einem separaten Container benötigt eine ausdrücklich konfigurierte gemeinsame Netzwerkverbindung oder eine erreichbare Host-Adresse; dessen `127.0.0.1` ist nicht der Docker-Host.

## 6. Updates, Daten und API-Verbindungen

```bash
docker compose pull
docker compose up -d
```

Vor Updates den Dienst mit `docker compose stop` stoppen und das komplette Datenvolume über das Backup-Werkzeug deines Docker-Servers sichern; danach wieder starten. SQLite-Datenbank und `integration.key` gehören zusammen. Bei einem expliziten INTEGRATION_KEY auch diesen sicher sichern. Das Volume heißt üblicherweise `<stackname>_projektzeit-data`. Stack-/Projektname für spätere Updates beibehalten, sonst kann ein anderes Volume entstehen. **Nicht `docker compose down -v` verwenden:** Das würde die Daten löschen.

Der Container nutzt das normale Docker-Netzwerk mit ausgehenden Verbindungen. DNS, Firewall, Routing und TLS-Zertifikate müssen auf deinem Server funktionieren. Unter **Einstellungen → Schnittstellen → Debug · Verbindung testen** mit echten Zugangsdaten prüfen. TeamViewer benötigt einen Script-Token mit **Verbindungsprotokollierung → Verbindungseinträge anzeigen**; keine Schreibrechte nötig. STARFACE muss aus dem Container erreichbar sein. Zugangsdaten werden erst in der Website eingegeben, nicht in GitHub.

Bei privatem GHCR-Package vor dem Pull mit einem GitHub-Token mit `read:packages` anmelden, z. B. über `docker login ghcr.io -u tojollinor` und den Token an der Passwortabfrage eingeben. Den Token nicht in den Stack oder Git speichern.

## Prüfstand und Quellen

Das Image wird erst von GitHub Actions gebaut; lokal steht hier kein Docker-Daemon zur Verfügung. Die Anwendung bleibt ein Prototyp: HTTPS, sichere Passwörter und Backups sind nötig; dies ersetzt keine vollständige Sicherheitsprüfung für den Internetbetrieb.

- [Docker: ENV-Variablen und Pflichtwerte](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [GitHub: Container Registry und öffentliche/private Images](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
