# ProjektZeit herunterladen und starten

Image: `ghcr.io/tojollinor/projektzeit-web:latest`

- [Repository](https://github.com/tojollinor/ProjektZeit-Web)
- [Quellcode als ZIP](https://github.com/tojollinor/ProjektZeit-Web/archive/refs/heads/main.zip)
- [Compose herunterladen](https://raw.githubusercontent.com/tojollinor/ProjektZeit-Web/main/compose.yaml)
- [ENV-Vorlage herunterladen](https://raw.githubusercontent.com/tojollinor/ProjektZeit-Web/main/.env.example)
- [GitHub-Builds](https://github.com/tojollinor/ProjektZeit-Web/actions)

Die Links liefern jeweils den zuletzt gepushten Stand.

## Neue Installation

`compose.yaml` und `.env.example` in einen eigenen Ordner laden; die Vorlage in `.env` umbenennen. Dort `APP_PUBLIC_URL` und die drei Passwörter setzen.

```bash
docker compose pull
docker compose up -d
docker compose ps
```

`BIND_ADDRESS=127.0.0.1` erlaubt nur Zugriff vom Docker-Host. Für deinen LAN-Server kann hier `10.1.1.14` stehen. `HTTP_PORT=8080` ist der veröffentlichte Port. Für HTTP im LAN `APP_SECURE_COOKIE=0` und `APP_PUBLIC_URL=http://10.1.1.14:8080`; für HTTPS `APP_SECURE_COOKIE=1` und die tatsächliche HTTPS-Adresse verwenden.

In Komodo die Compose-Datei als Stack übernehmen und alle Werte aus der ENV-Vorlage separat hinterlegen. MariaDB startet als eigener Dienst ohne nach außen geöffneten Datenbankport.

## Vorhandene Installation

Vor dem Wechsel auf MariaDB [UPGRADE-0.7.md](UPGRADE-0.7.md) ausführen. Die Alt-Daten werden nicht automatisch importiert. Wenn die alte SQLite-Datei vorhanden und MariaDB noch leer ist, verhindert der Server den normalen Start und verlangt den Import.

Der Schlüssel in `projektzeit-data` und die MariaDB-Daten in `mariadb-data` müssen zusammen gesichert werden. `docker compose down -v` löscht die Volumes und ist kein Update-Befehl.
