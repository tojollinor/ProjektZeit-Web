# API v1 für Windows und Smartphone-App

Basisadresse ist APP_PUBLIC_URL, z. B. `https://zeit.firma.de`. JSON über HTTPS. Alle Projekt- und Zeitdaten sind benutzerbezogen. Das Webportal verwendet weiterhin eine HttpOnly-Sitzung plus CSRF; native Clients verwenden einen Bearer-Token. Keine Tokens in URLs übergeben.

## Fähigkeiten abfragen

`GET /api/v1/capabilities` ist ohne Anmeldung erreichbar und liefert API-/Serverversion, unterstützte Funktionen und Token-Laufzeit.

## Native Anmeldung im Browser (Authorization Code + PKCE)

Der Windows-Client fragt kein Kennwort ab. Er erzeugt für jede Anmeldung einen
PKCE-Verifier, einen S256-Challenge-Wert und einen kryptografisch zufälligen
`state`. Anschließend öffnet er im Standardbrowser:

```text
GET /client/authorize
  ?response_type=code
  &client_id=projektzeit-windows
  &redirect_uri=http%3A%2F%2F127.0.0.1%3A49152%2Fcallback
  &code_challenge=...
  &code_challenge_method=S256
  &state=...
  &client_name=ProjektZeit%20f%C3%BCr%20Windows
```

Anmeldung, Auswahl einer von mehreren 2FA-Methoden und Freigabe finden im
Webportal statt. Als `redirect_uri` ist ausschließlich ein zufälliger lokaler
Port auf `127.0.0.1` oder `::1` mit dem Pfad `/callback` zulässig. Der Client
prüft bei der Rückleitung den unveränderten `state` und tauscht den einmalig
verwendbaren, drei Minuten gültigen Code aus:

```json
POST /api/v1/client-auth/token
{
  "grant_type": "authorization_code",
  "client_id": "projektzeit-windows",
  "redirect_uri": "http://127.0.0.1:49152/callback",
  "code": "CODE_AUS_DER_RUECKLEITUNG",
  "code_verifier": "URSPRUENGLICHER_PKCE_VERIFIER"
}
```

Erfolgsantwort:

```json
{"access_token":"OPAQUER-TOKEN","token_type":"Bearer","expires_in":43200}
```

Danach für jeden Aufruf `Authorization: Bearer OPAQUER-TOKEN` setzen. Bei 401
ist die lokale Sitzung zu verwerfen und die Browseranmeldung erneut zu starten.
Refresh-Tokens für native Clients gibt es nicht. Der Windows-Client schützt den
Token benutzergebunden mit DPAPI; der Server speichert nur dessen Hash. Jeder
Login erzeugt eine eigene, widerrufbare Sitzung.

`POST /api/v1/auth/token` mit Benutzername und Kennwort bleibt vorerst als
Kompatibilitätsschnittstelle für bestehende Clients erhalten, soll aber nicht
mehr für neue Clients verwendet werden.

## Endpunkte

| Methode / Pfad | Inhalt |
| --- | --- |
| GET /api/v1/me | Aktueller Benutzer und Rolle |
| GET /api/v1/dashboard | Kunden, Projekte, Kategorien, Stempelungen und laufender Arbeitstag |
| POST /api/v1/worktime/state | `{}`: Arbeits- und Pausenstatus lesen |
| POST /api/v1/worktime/action | `action`: `begin`, `end`, `pause` oder `resume` |
| POST /api/v1/timer/start | `project_id`, `category_id`, optional `note`; atomarer Wechsel |
| POST /api/v1/timer/stop | `{}`: Projekt beenden, unproduktive Zeit fortsetzen |
| POST /api/v1/projects/active | `id`, `active` für Schnellwahl |
| POST /api/v1/entries/edit | Siehe unten |
| GET /api/v1/export.csv | CSV der eigenen Zeiten |
| POST /api/v1/import.csv | `csv`: CSV-Inhalt |
| POST /api/v1/auth/revoke | `{}`: den aktuellen Bearer-Token widerrufen |

Stempelung bearbeiten: `id`, `original_start`, `original_end`, `original_note` aus der zuletzt gelesenen Antwort mitsenden, dazu `started_at`, `ended_at`, `project_id`, `category_id`, `note`. Die Originalwerte verhindern unbemerktes Überschreiben zwischen Web, Windows und App. Laufende Einträge erlauben nur Bemerkungsänderungen. ISO-Zeitstempel immer mit Zeitzone senden, etwa `2026-09-11T08:15:00+02:00`.

Fehler sind JSON mit `error`: 400 ungültige Eingabe, 401 Sitzung abgelaufen/ungültig, 403 fehlende Berechtigung, 409 Konflikt, 429 zu viele Anmeldeversuche. Nach Netzwerkausfall zunächst Dashboard neu lesen; Schreibzugriffe nicht blind wiederholen. Offline-Synchronisierung und Idempotency-Keys sind noch nicht implementiert.

## C#-Beispiel für den Token-Austausch (.NET)

```csharp
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

using var http = new HttpClient { BaseAddress = new Uri("https://zeit.firma.de") };
// code, verifier und redirectUri stammen aus dem zuvor gestarteten
// Browser-/Loopback-PKCE-Ablauf.
var login = await http.PostAsJsonAsync("/api/v1/client-auth/token", new {
    grant_type = "authorization_code",
    client_id = "projektzeit-windows",
    redirect_uri = redirectUri,
    code,
    code_verifier = verifier
});
login.EnsureSuccessStatusCode();
var auth = await login.Content.ReadFromJsonAsync<JsonElement>();
http.DefaultRequestHeaders.Authorization =
    new AuthenticationHeaderValue("Bearer", auth.GetProperty("access_token").GetString());
var dashboard = await http.GetFromJsonAsync<JsonElement>("/api/v1/dashboard");
// Bei Abmelden:
var logout = await http.PostAsJsonAsync("/api/v1/auth/revoke", new { });
logout.EnsureSuccessStatusCode();
```

STARFACE wird über den Browser verknüpft. Anbieter-Tokens und Client-Secret
bleiben dabei auf dem ProjektZeit-Server und werden niemals an den nativen
Client zurückgegeben. Die Referenzimplementierung steht unter
`windows-client/`; der Windows-Build wird zusätzlich als CI-Artefakt erzeugt.
