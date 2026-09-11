# API v1 für Windows und Smartphone-App

Basisadresse ist APP_PUBLIC_URL, z. B. `https://zeit.firma.de`. JSON über HTTPS. Alle Projekt- und Zeitdaten sind benutzerbezogen. Das Webportal verwendet weiterhin eine HttpOnly-Sitzung plus CSRF; native Clients verwenden einen Bearer-Token. Keine Tokens in URLs übergeben.

## Fähigkeiten abfragen

`GET /api/v1/capabilities` ist ohne Anmeldung erreichbar und liefert API-/Serverversion, unterstützte Funktionen und Token-Laufzeit.

## Anmelden

`POST /api/v1/auth/token`, Content-Type `application/json`:

```json
{"username":"DEIN-BENUTZER","password":"DEIN-PASSWORT","client_name":"ProjektZeit Windows"}
```

Erfolgsantwort:

```json
{"access_token":"OPAQUER-TOKEN","token_type":"Bearer","expires_in":43200}
```

Danach für jeden Aufruf `Authorization: Bearer OPAQUER-TOKEN` setzen. Der Token gilt zwölf Stunden; bei 401 erneut anmelden. Refresh-Tokens für native Clients sind noch nicht implementiert. Das Passwort nicht dauerhaft speichern. Windows Credential Manager/DPAPI bzw. iOS Keychain/Android Keystore für den Token nutzen. Jeder Login erzeugt eine eigene widerrufbare Sitzung. Der Server speichert nur den Token-Hash.

## Endpunkte

| Methode / Pfad | Inhalt |
| --- | --- |
| GET /api/v1/me | Aktueller Benutzer und Rolle |
| GET /api/v1/dashboard | Kunden, Projekte, Kategorien, Stempelungen und laufender Arbeitstag |
| POST /api/v1/work/begin | `{}`: Arbeitsbeginn und automatische unproduktive Zeit |
| POST /api/v1/work/end | `{}`: Arbeitsende und laufenden Timer beenden |
| POST /api/v1/timer/start | `project_id`, `category_id`, optional `note`; atomarer Wechsel |
| POST /api/v1/timer/stop | `{}`: Projekt beenden, unproduktive Zeit fortsetzen |
| POST /api/v1/projects/active | `id`, `active` für Schnellwahl |
| POST /api/v1/entries/edit | Siehe unten |
| GET /api/v1/export.csv | CSV der eigenen Zeiten |
| POST /api/v1/import.csv | `csv`: CSV-Inhalt |
| POST /api/v1/auth/revoke | `{}`: den aktuellen Bearer-Token widerrufen |

Stempelung bearbeiten: `id`, `original_start`, `original_end`, `original_note` aus der zuletzt gelesenen Antwort mitsenden, dazu `started_at`, `ended_at`, `project_id`, `category_id`, `note`. Die Originalwerte verhindern unbemerktes Überschreiben zwischen Web, Windows und App. Laufende Einträge erlauben nur Bemerkungsänderungen. ISO-Zeitstempel immer mit Zeitzone senden, etwa `2026-09-11T08:15:00+02:00`.

Fehler sind JSON mit `error`: 400 ungültige Eingabe, 401 Sitzung abgelaufen/ungültig, 403 fehlende Berechtigung, 409 Konflikt, 429 zu viele Anmeldeversuche. Nach Netzwerkausfall zunächst Dashboard neu lesen; Schreibzugriffe nicht blind wiederholen. Offline-Synchronisierung und Idempotency-Keys sind noch nicht implementiert.

## C#-Beispiel (.NET)

```csharp
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

using var http = new HttpClient { BaseAddress = new Uri("https://zeit.firma.de") };
var login = await http.PostAsJsonAsync("/api/v1/auth/token",
    new { username, password, client_name = "ProjektZeit Windows" });
login.EnsureSuccessStatusCode();
var auth = await login.Content.ReadFromJsonAsync<JsonElement>();
http.DefaultRequestHeaders.Authorization =
    new AuthenticationHeaderValue("Bearer", auth.GetProperty("access_token").GetString());
var dashboard = await http.GetFromJsonAsync<JsonElement>("/api/v1/dashboard");
// Bei Abmelden:
var logout = await http.PostAsJsonAsync("/api/v1/auth/revoke", new { });
logout.EnsureSuccessStatusCode();
```

STARFACE wird zentral im Webportal verknüpft. Anbieter-Tokens werden niemals an Windows-Client oder App zurückgegeben. Die neuen Endpunkte sind die Grundlage; ein fertig entwickelter nativer Client ist nicht enthalten.
