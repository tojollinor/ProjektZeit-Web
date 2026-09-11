# Upgrade 0.6 → 0.7: MariaDB und STARFACE OAuth

## ENV und Stack

Die separate ENV-Konfiguration bleibt erhalten. Neu sind:

| Variable | Bedeutung |
| --- | --- |
| APP_PUBLIC_URL | Browser-Adresse von ProjektZeit, z. B. `https://zeit.firma.de`, ohne Unterpfad |
| DB_PASSWORD | Starkes Passwort des MariaDB-Anwendungsbenutzers |
| DB_ROOT_PASSWORD | Anderes starkes Passwort für den Datenbankadministrator |
| STARFACE_OAUTH_ALLOWED_ORIGINS | Nur bei abweichenden Discovery-Endpunkten: explizit vertrauenswürdige HTTPS-Ursprünge, kommagetrennt |

STARFACE-Adresse, Client-ID und Client-Secret werden nicht als Docker-ENV gepflegt. Sie werden in der ProjektZeit-Weboberfläche pro Benutzer konfiguriert und mit dem Integrationsschlüssel verschlüsselt gespeichert.

APP_PUBLIC_URL richtet weder DNS noch einen Reverse-Proxy ein. Der Browser muss diese Adresse erreichen. Bei HTTPS APP_SECURE_COOKIE=1 setzen; für einen HTTP-LAN-Test 0. APP_PUBLIC_URL wird außerdem in den kurzlebigen `projektzeit://`-Startlink für den Windows-Client aufgenommen. Geheimnisse werden dort nie übertragen.

Der native Windows-Client verwendet für STARFACE eine lokale Loopback-Rücksprungadresse `http://127.0.0.1:PORT`, wobei der Port dynamisch gewählt wird.

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
2. Unter **Einstellungen → STARFACE** die STARFACE-Adresse eintragen. Die Client-ID ist mit `rest-client` vorbelegt und kann geändert werden. Das zugehörige Client-Secret aus der STARFACE-Administration eintragen und die Konfiguration speichern.
3. ProjektZeit verwendet Authorization Code + PKCE/S256. Meldet die STARFACE Discovery `client_secret_basic`, wird dieses Verfahren bevorzugt. `client_secret_post` wird als Fallback unterstützt. Das Client-Secret wird nur serverseitig entschlüsselt und weder an JavaScript noch an den Windows-Client ausgegeben.
4. **STARFACE verbinden** erzeugt eine zufällige, nur einmal verwendbare Desktop-Anfrage mit fünf Minuten Gültigkeit und öffnet `projektzeit://starface/connect?...`. Der URI enthält nur APP_PUBLIC_URL und den Einmal-Token, keine Zugangsdaten.
5. Die portable Windows-EXE registriert `projektzeit://` beim manuellen Start, sofern kein gültiger Handler existiert. Sie überschreibt einen funktionierenden Handler nicht. Ein späterer Installer kann denselben Handler auf seinen Installationspfad setzen.
6. Der Windows-Client öffnet für den OAuth-Vorgang einen Listener auf `http://127.0.0.1:PORT`, übernimmt die Einmal-Anfrage und öffnet die STARFACE-Anmeldung im Standardbrowser. Authorization- und Token-Anfrage verwenden exakt dieselbe Redirect-URI.
7. Die Integration fordert ausschließlich `pbx-login` an. Die Live-Probe prüft das eigene Konto über `/rest/users/me`; `pbx-admin` wird dafür nicht angefordert.
8. Nach erfolgreicher Anmeldung speichert ProjektZeit Access- und Refresh-Token verschlüsselt auf dem Server. Danach kann der Windows-Client beendet werden; spätere REST-Aufrufe und Token-Erneuerungen laufen direkt zwischen ProjektZeit und STARFACE.
9. Wenn Discovery-Endpunkte auf einen anderen Anbieter zeigen, dessen HTTPS-Ursprung gezielt in STARFACE_OAUTH_ALLOWED_ORIGINS ergänzen. Keine Wildcards. Ungültige Zertifikate werden nicht umgangen.

Bei `invalid_client` zeigt die Diagnose Client-ID, verwendetes Authentifizierungsverfahren und Redirect-URI, jedoch niemals Client-Secret, Authorization Code, PKCE-Verifier oder Tokens. Wenn Client-ID oder Client-Secret geändert werden, werden bestehende STARFACE-OAuth-Tokens verworfen und die Verknüpfung muss erneut durchgeführt werden.

Die Rückleitung ist an Benutzer, ProjektZeit-Sitzung und einen zehn Minuten gültigen OAuth-State gebunden. Zusätzlich ist der Start aus der Weboberfläche an eine fünf Minuten gültige Einmal-Anfrage gebunden. Refresh-Tokens werden beim nächsten Zugriff erneuert. Fehlt ein Refresh-Token oder wird er abgewiesen, erneut verbinden.

Die Implementierung ist gegen simulierte OAuth-Antworten getestet. Echter Login und REST-Zugriff müssen an der jeweiligen STARFACE geprüft werden. Echte Anruflisten sind weiterhin noch nicht umgesetzt.

[STARFACE: Authentifizierung für Integrationen ab Version 10](https://knowledge.starface.de/spaces/flyingpdf/pdfpageexport.action?pageId=325419009)

## TeamViewer und Zammad

TeamViewer bleibt beim Script-Token ohne Benutzerfeld und ohne TOTP. Vorhandene Tokens bleiben verwendbar. Zammad verwendet weiterhin die bestehende Basic-Anmeldung. Alle Provider-Seiten trennen Beispiele und Live-Proben sichtbar; keine Beispieldaten werden als Arbeitszeit gespeichert.
