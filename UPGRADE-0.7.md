# Upgrade 0.6 → 0.7: MariaDB und STARFACE OAuth

## ENV und Stack

Die separate ENV-Konfiguration bleibt erhalten. Neu sind:

| Variable | Bedeutung |
| --- | --- |
| APP_PUBLIC_URL | Browser-Adresse von ProjektZeit, z. B. `https://zeit.firma.de`, ohne Unterpfad |
| DB_PASSWORD | Starkes Passwort des MariaDB-Anwendungsbenutzers |
| DB_ROOT_PASSWORD | Anderes starkes Passwort für den Datenbankadministrator |
| STARFACE_OAUTH_ALLOWED_ORIGINS | Nur bei abweichenden Discovery-Endpunkten: explizit vertrauenswürdige HTTPS-Ursprünge, kommagetrennt |

ProjektZeit verwendet für STARFACE fest den öffentlichen OAuth-Client `rest-client` mit Authorization Code + PKCE/S256. Dafür wird kein Client-Secret verwendet.

APP_PUBLIC_URL richtet weder DNS noch einen Reverse-Proxy ein. Der Browser muss diese Adresse erreichen. Bei HTTPS APP_SECURE_COOKIE=1 setzen; für einen HTTP-LAN-Test 0. Der Webportal-Callback lautet genau:

`https://DEINE-PROJEKTZEIT-DOMAIN/api/v1/integrations/starface/callback`

Der native Windows-Client verwendet dagegen eine lokale Loopback-Rücksprungadresse `http://127.0.0.1:PORT`, wobei der Port dynamisch gewählt wird.

## Bestehende SQLite-Daten übernehmen

Die Migration liest SQLite unverändert und schreibt ausschließlich in eine leere MariaDB-Datenbank. IDs, Benutzerpasswörter, Kunden, Projekte, Kategorien, Arbeitstage, Stempelungen und verschlüsselte Schnittstellen-Konfigurationen bleiben erhalten. Browser- und Client-Sitzungen werden nicht übernommen. STARFACE muss anschließend neu per OAuth verknüpft werden.

1. Bisherigen Webdienst stoppen. Das gesamte bisherige Volume `projektzeit-data` sichern, einschließlich `projektzeit.db` und `integration.key`. Falls bisher INTEGRATION_KEY manuell gesetzt war, denselben Schlüssel weiterhin an den Webcontainer übergeben; alternativ vor der Umstellung gesichert als `integration.key` bereitstellen. Keinen neuen Schlüssel für alte verschlüsselte Daten erzeugen.
2. Compose und ENV aktualisieren; denselben Stack-/Compose-Projektnamen verwenden, damit das vorhandene Volume weiter eingebunden wird.
3. Neue Images laden und nur MariaDB starten:

```bash
docker compose pull
docker compose up -d db
```

4. Sobald MariaDB gesund ist, den Import einmalig ausführen. Das bisherige Volume ist im Einmal-Container unter `/app/data` eingebunden:

```bash
docker compose run --rm --no-deps projektzeit-web python migrate_sqlite.py /app/data/projektzeit.db
```

5. Die Ausgabe enthält die Anzahl importierter Zeilen pro Tabelle. Bei Fehlern wird die Datenänderung zurückgerollt. Ein zweiter Import in eine bereits gefüllte Datenbank wird verweigert. Die alte SQLite-Datei bleibt als unveränderte Quelle bestehen.
6. `docker compose up -d` ausführen, anmelden und Kunden/Projekte/Gesamtzeiten prüfen.

In Komodo dieselben Befehle über das Server-Terminal im Verzeichnis des Stacks ausführen, mit derselben ENV-Konfiguration. Nicht einen neuen Stacknamen für das Upgrade wählen. Die neue Anwendung stoppt mit einem Migrationshinweis, wenn sie eine alte SQLite-Datei und eine leere MariaDB findet.

Rückweg: vorheriges Image und alte Compose-Konfiguration mit SQLite wieder verwenden. Änderungen, die nach dem Import in MariaDB entstanden sind, sind in der SQLite-Sicherung nicht enthalten. Vor jedem weiteren Versionswechsel beide Volumes konsistent sichern; dafür den Webdienst während des Backups stoppen.

## STARFACE 10 einrichten

1. APP_PUBLIC_URL korrekt setzen und Webcontainer neu bereitstellen.
2. ProjektZeit verwendet `rest-client` als **Public Client**, ohne Client-Secret. Der Flow ist Authorization Code + PKCE/S256.
3. Der Windows-Client verwendet `http://127.0.0.1:PORT` als Loopback-Redirect. Der Port wird zur Laufzeit gewählt. ProjektZeit verwendet für Authorization- und Token-Anfrage exakt dieselbe Redirect-URI.
4. Die Integration fordert ausschließlich `pbx-login` an. Die Live-Probe prüft das eigene Konto über `/rest/users/me`; `pbx-admin` wird dafür nicht angefordert.
5. Einstellungen → STARFACE → Domain eingeben → **Mit STARFACE anmelden**. Die Anmeldung erfolgt auf der STARFACE bzw. ihrem Identitätsanbieter. Nach erfolgreicher Rückleitung in ProjektZeit den Verbindungstest starten.
6. Wenn Discovery-Endpunkte auf einen anderen Anbieter zeigen, dessen HTTPS-Ursprung gezielt in STARFACE_OAUTH_ALLOWED_ORIGINS ergänzen. Keine Wildcards. Ungültige Zertifikate werden nicht umgangen.

ProjektZeit wertet zusätzlich die OAuth-Discovery aus. Wenn STARFACE keinen Public-Client-Modus (`none`) oder kein PKCE/S256 meldet, wird dies vor dem Login als konkrete Konfigurationsmeldung angezeigt. Bei `invalid_client` zeigt die Diagnose außerdem den verwendeten Client-Modus und die Redirect-URI, jedoch keine Codes, Verifier oder Tokens.

Die Rückleitung ist an Benutzer, Sitzung und einen zehn Minuten gültigen Einmal-State gebunden. Tokens und PKCE-Verifier werden verschlüsselt gespeichert. Refresh-Tokens werden beim nächsten Zugriff erneuert. Fehlt ein Refresh-Token oder wird er abgewiesen, erneut anmelden. Nach „Verknüpfung entfernen“ werden lokal Tokens und ausstehende Anmeldevorgänge gelöscht; eine Anbieter-seitige Sitzung kann separat bei STARFACE beendet werden.

Die Implementierung ist gegen simulierte OAuth-Antworten getestet. Redirect-Freigabe und echter Login müssen an deiner STARFACE geprüft werden. Echte Anruflisten sind weiterhin noch nicht umgesetzt.

[STARFACE: Authentifizierung für Integrationen ab Version 10](https://knowledge.starface.de/spaces/flyingpdf/pdfpageexport.action?pageId=325419009)

## TeamViewer und Zammad

TeamViewer bleibt beim Script-Token ohne Benutzerfeld und ohne TOTP. Vorhandene Tokens bleiben verwendbar. Zammad verwendet weiterhin die bestehende Basic-Anmeldung. Alle Provider-Seiten trennen Beispiele und Live-Proben sichtbar; keine Beispieldaten werden als Arbeitszeit gespeichert.
