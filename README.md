# kulturbytes-social

kulturbytes-social ist ein konfigurierbarer Python-Publisher, der strukturierte
JSON-Quellen auf ein kanonisches Inhaltsmodell abbildet und auf Facebook,
Instagram, Mastodon und Bluesky veröffentlicht. JMESPath bestimmt die Datenextraktion,
Jinja2 die Darstellung. Kulturbytes ist die mitgelieferte Standardquelle.

Du wählst Inhalte im Terminal aus, siehst eine Vorschau und bestätigst jeden
Beitrag vor der Veröffentlichung. Veranstaltungen, Orte und Artikel verwenden
denselben Ablauf mit eigener Quellenkonfiguration.

Wähle die Anleitung für deine Plattform:

| Plattform | Wofür du sie verwendest |
|---|---|
| [Facebook](facebook/README.md) | Inhalte auf einer Facebook-Seite veröffentlichen |
| [Mastodon](mastodon/README.md) | Inhalte auf einem Mastodon-Konto veröffentlichen |
| [Instagram](instagram/README.md) | Bildbeiträge auf einem Instagram-Professional-Konto veröffentlichen |
| [Bluesky](#bluesky) | Text und ein Bild über das Konto-PDS veröffentlichen |

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv` und eine Internetverbindung.
Für Veröffentlichungen und den Zugangstest benötigst du außerdem die in der
jeweiligen Anleitung beschriebenen Zugangsdaten. Vorschau und Hilfe funktionieren ohne Tokens. Behalte den gesamten Repository-Ordner, da alle
Publisher das Paket in `common/` verwenden.

## Schnellstart

Es gibt genau einen öffentlichen CLI-Befehl: `kulturbytes-social`.
Die Plattformen werden als Click-Unterbefehle registriert:

```bash
uv run kulturbytes-social --help
uv run kulturbytes-social publish --help
uv run kulturbytes-social facebook --help
uv run kulturbytes-social mastodon --help
uv run kulturbytes-social instagram --help
uv run kulturbytes-social bluesky --help
```


Öffne ein Terminal im Repository-Hauptordner und installiere die Abhängigkeiten:

```bash
uv sync --all-packages
```

Öffne danach die [Facebook-Anleitung](facebook/README.md#schnellstart),
[Mastodon-Anleitung](mastodon/README.md#schnellstart) oder
[Instagram-Anleitung](instagram/README.md#schnellstart). Dort findest du die
Befehle zum Setzen deiner Zugangsdaten und für deine erste Vorschau.
Die Installation ist für alle Plattformen gemeinsam und muss nur einmal
ausgeführt werden.

Bei der ersten Auswahl gibst du beispielsweise `1` oder `1,3-5` ein.
`all` wählt alle angezeigten Inhalte; eine leere Eingabe beendet die Auswahl.
Der Standardmodus zeigt nur eine Vorschau.

## Konfiguration

Alle Publisher lesen ihre Zugangsdaten primär aus der lokalen `.env`, danach aus
Umgebungsvariablen und dem OS-Keyring. Mastodon nutzt denselben Resolver. Die
plattformabhängigen Variablen und ihre Standardwerte stehen in den Anleitungen:

- [Facebook konfigurieren](facebook/README.md#konfiguration)
- [Mastodon konfigurieren](mastodon/README.md#konfiguration)
- [Instagram konfigurieren](instagram/README.md#zugangsdaten-und-veröffentlichung)

Alle drei Publisher benötigen Zugangsdaten nur für `--publish` und `--check-auth`.
Import, Vorschau (`--dry-run`) und Befehlshilfe (`--help`) funktionieren ohne Tokens. Zugangsdaten, Meta-Konto-IDs und Mastodon-Instanzadresse werden zentral aus der deterministischen `.env` gelesen.
Echte Tokens gehören außerhalb der versionierten Dateien aufbewahrt.

## Gemeinsamer Meta-Zugang

```text
META_SYSTEM_USER_ACCESS_TOKEN ─┬─ Facebook  (FACEBOOK_PAGE_ID)
                              └─ Instagram (INSTAGRAM_USER_ID)
MASTODON_ACCESS_TOKEN ─────────── Mastodon
```

Für Facebook und Instagram verwaltest du einen Meta System User Access Token.
Der System User muss in deinem Meta Business Portfolio bereits Zugriff auf die
Facebook-Seite, das verknüpfte Instagram-Professional-Konto und die verwendete App
haben. Die erforderlichen Veröffentlichungsrechte müssen dem Token gewährt sein.
IDs bleiben separate, nicht geheime Konfiguration in `.env` oder Environment. Der Publisher
richtet keine System User oder Assets ein und implementiert keinen Browser-OAuth-Login.

Facebook ermittelt intern den Page Token der exakten Seiten-ID, validiert ihn und
verwendet ihn ausschließlich im Speicher des aktuellen Aufrufs. Instagram verwendet
den gemeinsamen Token direkt über die API mit Facebook Login (`graph.facebook.com`).
Bei gemeinsamem Token ist dies der Standard; ein explizites
`INSTAGRAM_LOGIN_TYPE=instagram` wird mit einer Migrationsmeldung abgewiesen.
Beide Publisher validieren ihr Ziel vor Events, Bildern, Datenbankzugriffen und
Veröffentlichung. `--check-auth` erstellt keine Inhalte. Ein erfolgreicher Lesetest
beweist nicht sämtliche Veröffentlichungsrechte.

## Lokale `.env` als primäre Meta-Konfiguration

```text
.env > Prozess-Environment > OS-Keyring > verdeckte TTY-Eingabe
```

Im Source-Checkout liegt die Datei immer im Repository-Hauptordner: `<repo>/.env`.
Der Pfad hängt vom installierten `common`-Paket ab, niemals vom Arbeitsverzeichnis.
Ein Aufruf aus `/tmp` verwendet also dieselbe Datei. Bei einer Installation ohne
Checkout gilt `$XDG_CONFIG_HOME/kulturbytes-social/.env`, andernfalls
`~/.config/kulturbytes-social/.env`; ein relativer XDG-Pfad wird ignoriert.

Beispiel (leere Platzhalter auch in [`.env.example`](.env.example)):

```dotenv
META_SYSTEM_USER_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=
INSTAGRAM_USER_ID=
FACEBOOK_GRAPH_API_VERSION=v26.0
INSTAGRAM_LOGIN_TYPE=facebook
MASTODON_BASE_URL=https://norden.social
MASTODON_ACCESS_TOKEN=
```

Trage die tatsächlichen Konto-IDs ein. Ist noch kein primärer Token vorhanden,
fragen `facebook --check-auth` und `instagram --check-auth` im TTY verdeckt nach
`Meta System User Access Token`. Vorhandene Environment-/Keyring-Tokens werden zuerst
verwendet. **Erst nach erfolgreicher Zielprüfung** wird der primäre Token automatisch
in `.env` gespeichert. Das gilt auch für `--publish`. Der aktuelle Aufruf verwendet
den validierten Wert weiter im Speicher. Fehler bei Validierung oder Speicherung
verhindern Veröffentlichung und Veröffentlichungseinträge. Ungültige Tokens verändern
die Datei nicht. Ein ungültiger vorhandener `.env`-Token führt zum Fehler, nicht zu
stillem Fallback; entferne oder korrigiere den Eintrag vor einem erneuten Bootstrap.

Leere `.env`-Tokenwerte zählen als fehlend und erlauben Fallback. Eine explizit leere
Prozess-Tokenvariable unterdrückt weiterhin den zugehörigen Keyring-Wert. Nicht geheime
Meta-Einstellungen (IDs, Graph-Versionen, Instagram-Login) folgen `.env > Environment >
Standard`, auch bei explizit leerem Wert. Werte werden wörtlich gelesen, ohne Shell-
Ausführung oder `${...}`-Expansion; `os.environ` wird nicht verändert.

Schreibvorgänge erhalten fremde Variablen, Kommentare und Leerzeilen, ersetzen denselben
Schlüssel ohne Duplikate und verwenden eine temporäre Datei im Zielverzeichnis mit
atomarem Austausch und Aufräumen bei Fehlern. POSIX-Dateirechte sind `0600`; auch eine
bereits vorhandene validierte Datei wird auf `0600` beschränkt. Symlinks und ungültige
Dateien werden abgewiesen. **Never commit .env.** `.env` und temporäre `.env.*`-Dateien
sind ignoriert; die Beispieldatei enthält keine Secrets.

CI/systemd können Tokens weiter extern bereitstellen. Nach erfolgreicher Validierung
benötigt der Prozess Schreibzugriff auf den deterministischen Konfigurationspfad.
Ohne TTY gibt es keine Token-Rückfrage. Hilfe und Dry Runs starten keinen Bootstrap.
Nur der primäre Meta-Token wird automatisch persistiert; abgeleitete Facebook-Page-Tokens
bleiben im Speicher. Legacy-Tokens werden niemals zum System-User-Token umbenannt.
Auch `MASTODON_ACCESS_TOKEN` folgt `.env > Environment > Keyring`;
`MASTODON_BASE_URL` folgt `.env > Environment > https://norden.social`. Ein separates
`export MASTODON_ACCESS_TOKEN=...` ist bei einem Token in `.env` nicht erforderlich.
Mastodon startet keine Auth-Einrichtung und persistiert Fallback-Tokens nicht automatisch.
Die Datenbankkonfiguration bleibt unverändert.

## Tokens optional im OS-Keyring speichern

Beide Meta-Unterbefehle verwalten standardmäßig **denselben** Eintrag:

```bash
uv run kulturbytes-social facebook --credentials set
uv run kulturbytes-social instagram --credentials status
uv run kulturbytes-social facebook --credentials delete
```

`set` fragt den Token verdeckt ab. `status` zeigt nur vorhanden/nicht vorhanden;
`delete` verlangt Bestätigung. Löschen wirkt für Facebook und Instagram gemeinsam,
ändert aber keine Environment-Variable und keinen bereits übernommenen `.env`-Eintrag. `--credential meta` wählt diesen Eintrag
explizit. Tokenwerte können nicht als CLI-Argument übergeben werden.

| Verwendung | Environment | Keyring-Service | Benutzername |
|---|---|---|---|
| Facebook und Instagram | `META_SYSTEM_USER_ACCESS_TOKEN` | `kulturbytes-social/meta` | `system-user-access-token` |
| Mastodon | `MASTODON_ACCESS_TOKEN` | `kulturbytes-social/mastodon` | `access-token` |

Für alle Plattformen gilt `.env > Environment > Keyring`. Status zeigt zusätzlich die Quelle
(`.env`, `Environment` oder `OS-Keyring`).
Eine explizit leere Environment-Variable unterdrückt den zugehörigen Keyring-Lookup. Zum Verwenden des Keyrings
die Variable mit `unset` entfernen. Hilfe und Dry Runs greifen nicht auf Tokens zu.
Die Credential-Verwaltung lädt keine Events und öffnet keine Datenbank; sie darf
nicht mit `--publish`, `--check-auth` oder `--resolve-page-token` kombiniert werden.

Keyring ist optional; Environment-Zugang funktioniert ohne Desktop-Sitzung.
Unter Ubuntu kann eine entsperrte Secret-Service-Sitzung nötig sein, beispielsweise
mit `gnome-keyring` und `libsecret-tools`. Unterstützt werden Secret Service,
KWallet, macOS Keychain und Windows Credential Manager; Klartext-Dateibackends werden
abgewiesen. `uv sync --all-packages` installiert die Python-Abhängigkeit. Tokens
werden nie ausgegeben oder in SQLite/Logs gespeichert. Nur erfolgreich validierte
primäre Meta-Zugänge werden automatisch in der geschützten `.env` persistiert.

### Migration bestehender Meta-Zugänge

Die Reihenfolge ist eindeutig: gemeinsamer Meta-Token aus `.env`, Environment, dann
Keyring; nur wenn keiner verfügbar ist, folgen die bisherigen Plattform-Credentials.
Ein ungültiger gemeinsamer Token führt zum Fehler und niemals zum Wechsel auf einen
Legacy-Token. Ein nicht verfügbarer optionaler Meta-Keyring verhindert vorhandene
Legacy-Environment-Zugänge nicht. Eine leere Meta-Environment-Variable erlaubt den
Legacy-Fallback, unterdrückt aber den gemeinsamen Keyring-Eintrag.

Facebook unterstützt vorübergehend `FACEBOOK_PAGE_ACCESS_TOKEN` / `FACEBOOK_USER_ACCESS_TOKEN`
und deren alte Keyring-Einträge samt Recovery. Instagram unterstützt vorübergehend
`INSTAGRAM_ACCESS_TOKEN` und seinen bisherigen Keyring-Eintrag. Ohne gemeinsamen
Token bleibt Instagram Login der bisherige Standard; `INSTAGRAM_LOGIN_TYPE=facebook`
funktioniert weiterhin mit dem passenden Legacy-Token. Diese Pfade geben einen
Deprecation-Hinweis aus. Bestehende Tokens werden weder automatisch migriert noch gelöscht.

Zum Umstellen den System User mit Asset-Zugriff konfigurieren, den gemeinsamen
Token einmal verdeckt speichern (oder `META_SYSTEM_USER_ACCESS_TOKEN` extern bereitstellen),
bei Instagram `INSTAGRAM_LOGIN_TYPE=facebook` setzen bzw. die alte Login-Variable entfernen
und beide `--check-auth`-Befehle ausführen. Veraltete Einträge können danach gezielt
mit `facebook --credentials delete --credential page` bzw. `user` und
`instagram --credentials delete --credential access` gelöscht werden.
Die Legacy-Optionen bleiben in dieser Übergangsversion verfügbar; ihre Entfernung
wird separat angekündigt und erfolgt frühestens in einer kommenden inkompatiblen Version.

## Zugang prüfen

Im Repository-Hauptordner:

```bash
uv run kulturbytes-social facebook --check-auth
uv run kulturbytes-social mastodon --check-auth
uv run kulturbytes-social instagram --check-auth
```

Der Check liest das konfigurierte Plattformkonto bzw. die Facebook-Seite und bei
Facebook-Wiederherstellung zusätzlich die verwalteten Seiten des Nutzers.
Er zeigt bei Erfolg den Namen und beendet sich mit Exitcode 0; bei fehlenden oder
ungültigen Zugangsdaten erscheint eine Fehlermeldung mit Exitcode 1, beispielsweise
`Error: Facebook Access Token ist abgelaufen.` Tokens werden niemals angezeigt;
auch von der API zurückgegebene Tokenwerte werden entfernt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und allen Auswahloptionen.
Es gibt keine Event-Abfrage, Auswahl, Bildverarbeitung, Veröffentlichung oder
Datenbankänderung. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff;
er garantiert keine Veröffentlichungsrechte. Zum Veröffentlichen bleiben
passende Zugangsdaten und die Bestätigung pro Termin erforderlich.

## Termine auswählen und veröffentlichen

Alle Publisher sind Unterbefehle von `kulturbytes-social`.
Für Facebook, ausgehend vom Repository-Hauptordner:

```bash
uv run kulturbytes-social facebook --dry-run --limit 10
```

Für Mastodon, ebenfalls ausgehend vom Repository-Hauptordner:

```bash
uv run kulturbytes-social mastodon --dry-run --limit 10
```

Für Instagram, ebenfalls ausgehend vom Repository-Hauptordner:

```bash
uv run kulturbytes-social instagram --dry-run --limit 10
```

Die Liste enthält freigegebene Termine ab dem heutigen Datum, chronologisch
sortiert. Bereits gespeicherte Veröffentlichungen werden ausgeblendet.
Wähle die gewünschten Nummern aus, um ihre Vorschau zu sehen.

Wenn du veröffentlichen möchtest, starte beispielsweise für Facebook:

```bash
uv run kulturbytes-social facebook --publish --limit 10
```

Vor jedem Beitrag fragt das Programm nach einer Bestätigung. `--limit` begrenzt
die angebotene Liste; du entscheidest, wie viele Termine du daraus veröffentlichst.
Der Ablauf ist interaktiv und eignet sich derzeit nicht für unbeaufsichtigte
Timer-Läufe.

| Option | Wirkung | Standard |
|---|---|---|
| `--dry-run` | Vorschau der ausgewählten Beiträge anzeigen | aktiv |
| `--check-auth` | Nur Zugang prüfen, ohne Veröffentlichung oder Datenbankzugriff | aus |
| `--publish` | Beiträge nach einzelner Bestätigung veröffentlichen | aus |
| `--limit 10` | Höchstens zehn Termine zur Auswahl anbieten | `50` |
| `--limit 0` | Alle passenden Termine zur Auswahl anbieten | — |
| `--city Flensburg` | Nach Stadt filtern, unabhängig von Groß- und Kleinschreibung | alle Städte |
| `--include-published` | Bereits veröffentlichte Termine mit zusätzlicher Rückfrage anbieten | aus |
| `--help` | Hilfe zu den Befehlen anzeigen | — |

Nach Installation funktioniert `kulturbytes-social` auch außerhalb des Repositorys
ohne `uv run`. Die Plattformpakete sind interne Backends und haben keine eigenen
öffentlichen Executables.

## Einzelnen Termin direkt auswählen

Im Repository-Hauptordner kannst du die nummerierte Auswahl überspringen:

```bash
uv run kulturbytes-social facebook --publish --event-uuid "EVENT_UUID" --date-identifier "202609101830"
```

Ersetze `EVENT_UUID` durch die Veranstaltungs-UUID. `--date-identifier` akzeptiert
entweder den `date_slug` (wie im Beispiel) oder die `date_uuid`. Beide Optionen
müssen zusammen angegeben werden. Ohne `--publish` erscheint nur die Vorschau.
Vor dem Veröffentlichen bleibt die Bestätigungsfrage bestehen.

Der Termin wird über `/api/events` aufgelöst; die Liste liefert auch die bevorzugte
`summary`. Die Detailantwort liefert die übrigen Daten und bei leerer Zusammenfassung
die `description`. Freigabe-, Datums-, Stadt- und Duplikatfilter gelten weiterhin.
`--limit` schließt den direkt gewählten Termin nicht aus. Nicht eindeutig gefundene
oder ausgefilterte Termine führen zu einer Fehlermeldung und einem Fehler-Exitcode.

## Inhalt der Beiträge

Standardmäßig übernehmen alle Publisher Veranstaltungsinformationen aus der Kulturbytes-API
und verlinken auf den Termin bei Kulturbytes. Mit `--source` lassen sich weitere
konfigurierte JSON-Quellen auswählen. Vorhandene Veranstaltungsbilder
und Hashtags ergänzen die Beiträge.

Facebook verwendet einen ausführlichen Beitrag und veröffentlicht vorhandene
Bilder als Fotopost. Mastodon verwendet einen auf das Instanzlimit (Fallback: 500 Zeichen)
gekürzten Text und öffentliche Beiträge mit Alt-Text für Bilder. Die Details
stehen unter [Facebook](facebook/README.md#inhalt-der-beiträge) und
[Mastodon](mastodon/README.md#inhalt-der-beiträge). Instagram benötigt ein JPEG-Hauptbild
und verwendet bis zu 2.200 Zeichen sowie höchstens fünf erzeugte Hashtags; siehe
[Instagram](instagram/README.md#bild-und-beitragstext).

## Data Sources

Der Ablauf im Kern ist quellenunabhängig:

```text
SourceDefinition → Fetcher → JMESPath-Mapper → ContentItem
    → Jinja2 TemplateRenderer → RenderedPost → Publisher
```

Kulturbytes hat keinen eigenen Python-Adapter mehr. Es verwendet denselben
`JsonSourceAdapter` wie jede andere JSON-Quelle. Listen-/Detailabfragen, Release-
und Identitätsprüfungen stehen vollständig in `sources/kulturbytes.yaml`. Der Kern fragt Adapter-Fähigkeiten und Quellenverhalten
ab; er verzweigt nicht anhand eines Quellennamens. Neue Veranstaltungen, Orte,
Artikel oder einfache Mitteilungen brauchen keine neuen Python-Klassen.

```bash
uv run kulturbytes-social publish --platform facebook --source example-articles
uv run kulturbytes-social publish --platform mastodon --source example-places --item-id p1
uv run kulturbytes-social publish --platform instagram --source kulturbytes
```

Alle Befehle starten als Dry Run. `--publish` aktiviert die Veröffentlichung mit
Bestätigung für jeden Inhalt. `--include-published` verlangt weiterhin eine zusätzliche
Rückfrage. Die bisherigen Befehle `facebook`, `instagram` und `mastodon` bleiben
verfügbar und verwenden denselben Ablauf. Authentifizierungs- und Credential-Befehle
bleiben unter den Plattformbefehlen, etwa `facebook --check-auth`.

`kulturbytes` ist ausschließlich am CLI-Rand als Standardquelle gesetzt.
Die alten Optionen `--event-uuid` und `--date-identifier` sind Kulturbytes-
Kompatibilitätsselektoren der Plattformbefehle. Die generische Engine löst sie anhand von `legacy_selectors` in YAML auf;
`publish` verwendet den neutralen Selektor `--item-id`.

## SourceDefinition und JSON Source Mapping

Quellen werden durch vertrauenswürdige lokale YAML-Dateien konfiguriert. Beispiel:

```yaml
name: museum
adapter: json
list:
  url: https://museum.example/api/items
  method: GET
  headers:
    Accept: application/json
    X-API-Version: "2"
  query:
    limit: "100"
  root: data.items
  mode: collection
detail:
  url: https://museum.example/api/items/{id}
  root: data
  mode: object
fields:
  id: id
  title: name
  text: description
  location: building.name
  city: building.city
  image_url: image.url
media:
  allowed_hosts:
    - images.museum.example
    - cdn.museum.example
behavior:
  skip_past: false
```

| Einstellung | Bedeutung |
| --- | --- |
| `name` | Eindeutiger Name, 1–64 Kleinbuchstaben/Ziffern/`_`/`-`; erstes Zeichen alphanumerisch |
| `adapter` | `json` |
| `list` / `request` | Gleichwertige Formen für den ersten Abruf; genau eine verwenden |
| `endpoint` | Kompatibilitätsform für die URL; `root`, `mode`, `method`, `headers`, `query` stehen dann oben |
| `detail` | Optionaler Detail-Request mit `{id}` oder deklarierten Pfad-Platzhaltern |
| `fields` | Kanonisches Feld → JMESPath-Ausdruck; `title` ist erforderlich |
| `media.allowed_hosts` | Erlaubte Bildhosts dieser Quelle, standardmäßig `[]` |
| `behavior.skip_past` | Vergangene Datumsangaben ausschließen; generischer Standard `false` |

`request`/`list` können `root` und `mode` auch auf oberster Ebene verwenden;
dieselbe Einstellung darf nur an einer Stelle stehen. Request-spezifische
`fields` überschreiben das vollständige globale Mapping für diesen Request,
beispielsweise wenn die Detailantwort `headline` statt `name` liefert.

Unbekannte Einstellungen, doppelte YAML-Schlüssel oder Quellennamen, ungültige
Typen und ungültige JMESPath-Ausdrücke werden lokal abgelehnt. Fehlende optionale
Mapping-Ergebnisse werden `None`, fehlende Tags `[]`. Titel sind verpflichtend;
fehlerhafte Datensätze und doppelte IDs werden nicht stillschweigend ausgewählt.

## Listen- und Detailabrufe

Alle Requests verwenden ausschließlich **HTTPS auf Port 443 und GET**. Auch lokales
HTTP, POST-basierte Quellen und authentifizierte Quellen-APIs werden hier nicht
unterstützt. Header sind statische Betreiberkonfiguration; erlaubt sind nur
`Accept`, `User-Agent` und `X-API-Version`. Insbesondere `Authorization`,
`Proxy-Authorization`, `Cookie`, `Set-Cookie` und API-Key-Header werden abgelehnt.
Query-Schlüssel und -Werte müssen Strings ohne Steuerzeichen sein. Zugangsdaten
gehören weder in URLs, Header noch Query-Konfiguration; es gibt keine Variablen-
oder Credential-Interpolation.

`mode: collection` erwartet eine Liste von Objekten; `mode: object` genau ein
Objekt. Die Antwortform wird niemals aus dem JSON geraten. Der Standard für den
ersten Request ist `collection`, für `detail` ist er `object`. `root` ist stets
erforderlich; `@` bezeichnet die vollständige Antwort.

Ohne `detail` ist der erste Abruf bereits der vollständige Inhalt. Eine direkte
Auswahl mit `--item-id` sucht dann genau einen Eintrag vor Anwendung des Limits.
Mit `detail` arbeitet die interaktive Auswahl zunächst mit dem Listen-Mapping und
lädt nur ausgewählte Details. Beim einfachen `{id}`-Modus überspringt ein direktes
`--item-id 123` den Listenabruf und lädt unmittelbar `/items/123`. Deklarierte
`detail.placeholders` benötigen dagegen den ausgewählten Listeneintrag; dann
findet auch bei `--item-id` zuerst ein Listenabruf statt. Das Detail muss eindeutig dieselbe ID
liefern; abweichende oder fehlende IDs führen zum Abbruch. Listen-/Detail-Mappings
brauchen deshalb eine stabile `id`.

Ohne `detail.placeholders` bleibt `{id}` die einzige URL-Variable. Mit diesem
Block werden mehrere benannte Variablen aus kompilierten JMESPath-Ausdrücken
unterstützt. Jeder Name muss `[A-Za-z_][A-Za-z0-9_]*` entsprechen und genau einmal
im URL-Pfad vorkommen; unbenutzte oder nicht deklarierte Namen werden abgelehnt.
Jeder Wert muss ein nicht leerer String sein und wird als undurchsichtiges
URL-Pfadsegment kodiert; `.` und `..` werden abgelehnt. Platzhalter dürfen weder
Schema, Host, Port, Query noch Fragment verändern. Es gibt kein Python-Formatting
und keine Jinja-Ausführung in URLs.

Generische Abrufe verwenden frische Clients ohne Social-Auth, Cookies, `.netrc`
oder Umgebungs-Proxies, explizite Timeouts und begrenzte GET-Retries. Redirects
werden abgelehnt. Der Transport prüft sämtliche DNS-Antworten auf öffentliche
Adressen und verbindet direkt mit der geprüften IP unter ursprünglichem Host und
TLS-SNI. Interne Netze sind keine implizit unterstützten Quellendestinationen.
Fehlermeldungen enthalten keine vollständigen JSON-Antworten oder Request-URLs.

## Mehrstufige Quellen vollständig in YAML

Bei `detail.placeholders` verwendet die Engine privat den Kontext
`{"list": <ausgewähltes JSON-Objekt>, "detail": <Detail-JSON-Objekt>}`.
`list.fields` erstellt die Vorschau aus dem **rohen Listeneintrag**. Das globale
`fields`-Mapping erstellt den endgültigen Inhalt aus dem kombinierten Kontext;
`detail.fields` kann dieses vollständige Mapping ersetzen. Raw-JSON bleibt in
privaten `SourceRecord`-Objekten des Adapters und gelangt nie in `ContentItem`,
Jinja, SQLite oder Publisher. Ohne deklarierte Platzhalter bleibt das bisherige
Mapping auf das einzelne JSON-Objekt erhalten.

```yaml
detail:
  url: https://example.org/records/{record}/{slug}
  root: item
  placeholders:
    record: list.record_id
    slug: list.slug
  identity_checks:
    - left: list.record_id
      right: detail.identifier
fields:
  id: list.record_id
  title: detail.headline
  text: list.summary || detail.body
```

Identitätsprüfungen werden beim Laden kompiliert. Beide Seiten müssen vorhandene,
begrenzte skalare Werte ergeben und nach Wert **und Typ** übereinstimmen. Fehler
nennen Quelle, Prüfnummer und Ausdrücke, niemals vollständige Antwortdaten.
Die kanonische ID muss ebenfalls der Auswahl entsprechen.

`identity` enthält genau `publication_key`, `content_key` und `revision`, jeweils
als kompilierten Ausdruck. Die Werte werden schon für die Vorschau benötigt,
weil dort Dubletten und aktive Versuche gefiltert werden. Nach dem Detailabruf
werden sie erneut geprüft und dürfen sich nicht verändern. Explizite Identitäten
sind 1–200 Zeichen lange sichere Kennungen (`[A-Za-z0-9_][A-Za-z0-9_.:-]*`).
Ohne diesen Block gilt weiterhin `<source>:<id>`. `ContentItem.id` bleibt davon
getrennt. Es gibt keine automatische Änderung oder Migration historischer Schlüssel.

Request-lokale `assertions` ordnen JMESPath-Ausdrücken `type` und optional
`required: true` zu. Unterstützte Typen: `identifier`, `string`, `object`,
`strings` (Stringliste), `number` (endlich und nicht negativ), `date` (ISO-Tag),
`time` (lokale ISO-Uhrzeit) und `url` (HTTP(S) ohne Zugangsdaten).
Fehlende optionale Werte und `null` sind erlaubt. Kulturbytes aktiviert
`skip_invalid: true`: fehlerhafte Listeneinträge werden gemeldet/übersprungen,
ein ungültiger direkter Treffer führt auch neben einem gültigen Treffer zum Fehler.
Fehlerhafte Hüllen und Detailantworten führen immer zum Abbruch. Doppelte IDs
werden grundsätzlich abgelehnt; `list.allow_duplicate_ids: true` erhält ausdrücklich
das bisherige Kulturbytes-Listenverhalten. Direkte Auswahl erfordert trotzdem
genau einen Treffer, und die Publikationsreservierung verhindert doppelte Posts.

`filters` werden auf validierte Listeneinträge angewandt. Jeder Filter hat
`expression` und genau einen Operator: `equals`, `not_equals`, `truthy: true`
oder `falsy: true`. Vergleiche sind typgenau. `legacy_selectors` enthält die
beiden bestehenden CLI-Argumente `event_uuid` und `date_identifier`, jeweils mit
einer Liste alternativer Ausdrücke. Alle Argumente müssen treffen. Die Engine
kennt weder Kulturbytes-Feldnamen noch einen speziellen Kulturbytes-Selektor.

`derived.<canonical_field>.concat` verbindet ausschließlich Literale und
`{expr: <JMESPath>}`-Teile zu einem String. Es gibt keine beliebigen Funktionen,
Python-Ausdrücke oder URL-Templates. Die fünf zusätzlichen JMESPath-Funktionen
sind `trim(string|null)`, `join_text(separator, strings_or_nulls)`,
`number_text(number|null)` (kompakte Zahlendarstellung), `time_hm(string)`
(lokale ISO-Uhrzeit auf Minuten normalisieren) und `path_segment(string)`
(opaque URL-Kodierung). Alle Ergebnisse durchlaufen die kanonische Validierung.
Die Kulturbytes-YAML verwendet sie für URL, Adresse und bestehende Preisangaben;
Marke, Hashtags und deren Priorität stehen nur in den Quelltemplates.

Die vollständige mitgelieferte Kulturbytes-Definition lautet:

```yaml
name: kulturbytes
adapter: json
behavior:
  skip_past: true
media:
  allowed_hosts:
  - api.kulturbytes.de
skip_invalid: true
list:
  allow_duplicate_ids: true
  url: https://api.kulturbytes.de/api/events
  method: GET
  root: data.events
  mode: collection
  fields:
    id: date_uuid
    title: title
    city: venue_city
    location: venue_name
    date: start_date
    time: start_time || `null`
  assertions:
    uuid:
      type: identifier
      required: true
    date_uuid:
      type: identifier
      required: true
    date_slug:
      type: identifier
      required: true
    release_status:
      type: string
      required: true
    title:
      type: string
      required: true
    start_date:
      type: date
      required: true
    venue_name:
      type: string
    venue_city:
      type: string
    summary:
      type: string
    start_time:
      type: time
detail:
  url: https://api.kulturbytes.de/api/event/{event_uuid}/date/{date_slug}
  method: GET
  root: data
  mode: object
  placeholders:
    event_uuid: list.uuid
    date_slug: list.date_slug
  identity_checks:
  - left: list.uuid
    right: detail.uuid
  - left: list.date_uuid
    right: detail.date.uuid
  - left: list.date_slug
    right: detail.date.slug
  assertions:
    uuid:
      type: identifier
      required: true
    title:
      type: string
      required: true
    date:
      type: object
      required: true
    date.uuid:
      type: identifier
      required: true
    date.slug:
      type: identifier
      required: true
    date.start_date:
      type: date
      required: true
    subtitle:
      type: string
    description:
      type: string
    summary:
      type: string
    org_name:
      type: string
    date.venue_name:
      type: string
    date.venue_street:
      type: string
    date.venue_house_number:
      type: string
    date.venue_postal_code:
      type: string
    date.venue_city:
      type: string
    date.price_type:
      type: string
    date.currency:
      type: string
    images.main.alt:
      type: string
    tags:
      type: strings
    images:
      type: object
    images.main:
      type: object
    images.main.uuid:
      type: identifier
    images.main.url:
      type: url
    date.ticket_link:
      type: url
    date.min_price:
      type: number
    date.max_price:
      type: number
    date.end_date:
      type: date
    date.start_time:
      type: time
legacy_selectors:
  event_uuid:
  - uuid
  date_identifier:
  - date_uuid
  - date_slug
filters:
- expression: release_status
  equals: released
identity:
  publication_key: list.date_uuid
  content_key: list.uuid
  revision: list.date_slug
fields:
  id: list.date_uuid
  title: detail.title
  subtitle: detail.subtitle
  text: trim(trim(list.summary) || detail.description)
  city: detail.date.venue_city
  location: detail.date.venue_name
  address: >-
    join_text(', ', [(detail.date.venue_street && join_text(' ', [detail.date.venue_street, detail.date.venue_house_number]))
    || '', join_text(' ', [detail.date.venue_postal_code, detail.date.venue_city])])
  date: detail.date.start_date
  time: time_hm(detail.date.start_time || '00:00')
  end_date: detail.date.end_date
  image_url: detail.images.main.url || `null`
  image_alt: trim(detail.images.main.alt || join('', ['Veranstaltungsbild zu ', detail.title]))
  image_name: detail.images.main.uuid || list.date_uuid
  organizer: detail.org_name
  ticket_link: detail.date.ticket_link || `null`
  tags: detail.tags
  price: >-
    (detail.date.price_type == 'free' && 'Eintritt frei') || (detail.date.min_price != `null` && join('',
    ['Eintritt: ', number_text(detail.date.min_price), (detail.date.max_price != `null` && detail.date.max_price
    != detail.date.min_price && join('', ['–', number_text(detail.date.max_price)])) || '', ' ', ((contains(keys(detail.date),
    'currency') && [(detail.date.currency == `null` && 'None') || to_string(detail.date.currency)]) ||
    ['EUR'])[0]])) || `null`
derived:
  link:
    concat:
    - https://kulturbytes.de/de/veranstaltung/
    - expr: path_segment(list.uuid)
    - /
    - expr: path_segment(list.date_slug)
```

`trim(list.summary)` behandelt auch reine Leerzeichen als leer. Nur dann wird
`detail.description` verwendet; `detail.summary` ist niemals die Textquelle.
Tags stammen aus `detail.tags`; `#Kulturbytes`, Stadt und Instagram-Priorität
werden in `templates/kulturbytes/*.j2` ergänzt. Plattformlimits bleiben im Renderer.

## JMESPath

`root` und alle Werte unter `fields` sind beim Laden kompilierte JMESPath-Ausdrücke:
`events`, `places`, `data.items`, `event.headline` oder `media[0].url`. Unterschiede
zwischen fremden JSON-Strukturen bleiben in YAML-Mappings und Assertions.

**Mapping bestimmt, woher Daten kommen. Templates bestimmen, wie sie erscheinen.**

## Canonical ContentItem

`ContentItem` ist ein striktes Pydantic-Modell ohne quellenspezifische Dictionaries.
Es erlaubt keine unbekannten Felder oder impliziten Typumwandlungen.

| Felder | Typ und Bedeutung |
| --- | --- |
| `title` | Nichtleerer String; einziges Pflichtfeld für Inhalte |
| `id` | Optionaler stabiler String, 1–200 Zeichen; für Veröffentlichung erforderlich |
| `subtitle`, `text` | Optionale Strings |
| `city`, `location`, `address` | Optionale Ortsangaben als Strings |
| `date`, `end_date` | Optionales ISO-Datum `YYYY-MM-DD` |
| `time` | Optionale lokale Zeit `HH:MM` oder `HH:MM:SS` |
| `image_url`, `link`, `ticket_link` | Optionale HTTP(S)-URLs ohne eingebettete Zugangsdaten |
| `image_alt`, `image_name` | Optionaler Alternativtext und sicherer Upload-Dateiname |
| `tags` | Liste von Strings, Standard `[]`; getrimmt, leere/identische Werte entfernt |
| `organizer`, `price` | Optionale bereits lesbare Angaben |

Das bisherige interne Modell `SocialItem` heißt jetzt `ContentItem`; in eigenen
Mappings und Templates wird `venue` durch `location` ersetzt. Die übrigen Felder
bleiben erhalten. Sie eignen sich auch für Ausstellungen, Orte, Ankündigungen oder
Artikel; eine unstrukturierte Metadata-Hintertür gibt es nicht.

`behavior.skip_past: true` filtert Datumswerte vor dem heutigen Tag in Europe/Berlin.
Kulturbytes und das Event-Beispiel aktivieren dieses Verhalten. Der generische
Standard `false` lässt auch ältere Artikel zu. Fehlende Datumswerte sind gültig;
der Inhaltstyp wird nicht anhand vorhandener Felder erraten. `--city` ist ein
exakter Vergleich ohne Beachtung der Groß-/Kleinschreibung. Einträge ohne Stadt
passen bei aktivem Stadtfilter nicht. Detailwerte werden erneut gegen diese Filter
geprüft.

## SourceContext und Veröffentlichungsschlüssel

Ein privater `SourceContext` begleitet `ContentItem` und `RenderedPost`. Er enthält
`source_name`, eine `PublicationIdentity(publication_key, content_key, revision)`
und eine unveränderliche `MediaPolicy`. Diese Daten sind weder Mapping-Felder noch
Template-Variablen.

Generische Quellen verwenden `<source>:<id>` als Veröffentlichungsschlüssel;
dieselbe ID in zwei Quellen kollidiert dadurch nicht. Der mitgelieferte
Kulturbytes-Eintrag konfiguriert seine bisherigen Termin-IDs und Fingerprints
explizit über `identity`; seine Schlüssel erhalten keinen `kulturbytes:`-Präfix.
`storage.py` bietet die neutrale Schnittstelle; `legacy_storage.py`, `database.py`
und `publications.py` kapseln bestehende Tabellen, Snapshots und Journaltransaktionen.
Historische Spaltennamen werden ohne Datenmigration beibehalten. Reservierung,
Dublettenvermeidung, Behandlung unklarer Remote-Ergebnisse und Recovery bleiben
unverändert. Quellenname und ID müssen nach Veröffentlichung stabil bleiben.
Journalabfragen mit dem bisherigen `--date-uuid` verwenden bei generischen Quellen
den vollständigen zusammengesetzten Schlüssel.

## Quellenspezifische Medienrichtlinien

### Pluto-Bildverarbeitung

Für Quellen mit [Pluto-Bildserver](https://github.com/sndcds/pluto) aktiviert
`media.image` die serverseitige Verarbeitung über URL-Parameter:

```yaml
media:
  allowed_hosts: [api.kulturbytes.de]
  image:
    ratio: {instagram: "4/5", facebook: "1200/630", mastodon: free}
    type: {instagram: jpg, facebook: webp, mastodon: jpg}
    max_width: 1920
    max_height: 1920
```

`ratio` akzeptiert positive ganzzahlige Verhältnisse (`4/5` oder `4:5`) und
`free`; `type` akzeptiert `jpg`, `png`, `webp`. Größenlimits sind ganze Zahlen
zwischen 1 und 65535. Fehlende Plattformwerte bedeuten freies Verhältnis bzw.
keine Formatvorgabe. Ohne `media.image` bleibt die Bild-URL unverändert.
Die Quelle muss die Pluto-Parameter unterstützen; dies wird nicht am Hostnamen erkannt.

Der Publisher übersetzt etwa Instagram zu `?ratio=4%3A5&height=1920&type=jpg`
und Facebook zu `?ratio=1200%3A630&width=1920&type=webp`. Pluto übernimmt den
Zuschnitt am gespeicherten Fokuspunkt, Verkleinerung und Konvertierung.
Für `free` wird kein Ratio-Parameter gesendet. Bei zwei Größenlimits benötigt
dieser Modus die positiven kanonischen Felder `image_width` und `image_height`,
um die begrenzende Kante zu wählen; fehlende Metadaten führen zu einem klaren Fehler.
Kulturbytes mappt diese aus `detail.images.main.width` und `.height`.
Andere Quellen können ihre entsprechenden Metadaten auf dieselben Felder abbilden.

Vorhandene `ratio`, `fit`, `width` und `height` werden ersetzt; eine konfigurierte
Formatvorgabe ersetzt `type`. Andere Query-Parameter bleiben erhalten.
Vorschau und Veröffentlichung verwenden dieselbe verarbeitete URL; Instagram
prüft weiterhin JPEG und übergibt diese öffentliche URL an Meta. Die gebündelte
Instagram-Konfiguration verwendet deshalb `jpg`. Es gibt keine lokale Bildkonvertierung,
neues Hosting oder zusätzliche Abhängigkeiten. Alle lokalen Bildabrufe behalten
Hostfreigabe, DNS-Pinning und getrennten Transport ohne Social-Zugangsdaten.

`media.allowed_hosts` ist eine explizite Freigabe durch den Betreiber, keine
Information aus der API-Antwort. Der Standard ist eine leere Liste: Bilder werden
abgelehnt. Der mitgelieferte Kulturbytes-Eintrag erlaubt `api.kulturbytes.de`;
andere Quellen können eigene konkrete Hosts freigeben. Wildcards, Schemes, Ports,
Pfade und Zugangsdaten sind in Hosteinträgen unzulässig.

Für alle Hosts bleiben HTTPS/443, vollständige DNS-Prüfung, Ablehnung privater,
Loopback-, Link-Local-, Multicast-, reservierter und unspezifizierter Adressen,
DNS-Pinning, ursprünglicher Host-Header, TLS-SNI und Zertifikatsprüfung aktiv.
Unterschiedliche logische HTTPS-Hosts verwenden getrennte Verbindungspools, auch
bei identischer IP. Es gibt keine globale Host-Allowlist und keine Proxy-/Social-
Credential-Übernahme. Jeder Retry und jeder der maximal fünf Redirects wird erneut
geprüft; auch der Redirect-Zielhost muss in derselben Quellenrichtlinie stehen.

Facebook und Mastodon unterstützen bildlose Beiträge. Instagram braucht weiterhin
ein öffentliches JPEG; seine lokale Prüfung verwendet dieselbe Medienrichtlinie.
Ein ungültiges vorhandenes Bild führt nicht zu einem stillen Text-Fallback. Metas
späterer eigener Instagram-Bildabruf liegt außerhalb unseres Transports.

## Jinja2 Templates

Ein zentraler Sandbox-Renderer liefert `RenderedPost(text, image_url, image_alt,
image_name)`. Default-Templates sind neutral, beginnen mit dem Titel und enthalten
keine Kulturbytes-Marke oder Veranstaltungsannahme. Kulturbytes verwendet eigene
Templates unter `templates/kulturbytes/`; zwölf gesicherte Beispielausgaben bleiben
bytegenau unverändert, einschließlich Marken-Hashtags und Instagram-Priorität.

Auflösung: `templates/<quelle>/<plattform>.j2`, danach
`templates/default/<plattform>.j2`. Innerhalb jedes Schritts werden bei installierter
Nutzung XDG-Dateien vor Paketdateien gesucht. Templates sind vertrauenswürdige
Projekt-/Administratorkonfiguration und sehen ausschließlich kanonische Felder.
Die sicheren Filter sind `default`, `join`, `trim`, `lower`, `upper`, `plain`,
`dateformat` und `hashtags`. Python-Attribute, beliebige Aufrufe, Globals, Imports,
Includes und frei wählbare Dateipfade sind gesperrt. Inhalt wird nicht erneut als
Template ausgeführt.

Instagram bleibt bei 2.200 Zeichen und maximal fünf Hashtags. Templates bestimmen
deren Priorität; bei mindestens fünf kanonischen Tags müssen fünf vollständige
Tags erhalten bleiben. Mastodon bewahrt alle generierten Tags und den vollständigen
Pflicht-Link, kürzt `text` an Wortgrenzen und verwendet das Instanzlimit (Fallback
500). Der Renderer kürzt Inhaltsfelder und rendert erneut, statt den fertigen Post
abzuschneiden. Zu lange feste Inhalte oder verlorene Pflicht-Links/Hashtags führen
zu einem Fehler. Optionale Metadaten können bei Mastodon entfallen. Facebook behält
die bisherige Markdown-Darstellung; Instagram und Mastodon bereinigen sie.

## Quellen verwalten und konfigurieren

```bash
uv run kulturbytes-social sources list
uv run kulturbytes-social sources validate museum
uv run kulturbytes-social sources show museum
```

Alle drei Befehle arbeiten lokal ohne HTTP, Credentials oder Datenbankzugriff.
`validate` prüft Schema, Requests, GET/HTTPS, Header/Query, Platzhalter, Modi,
JMESPath, kanonische Felder, Medienrichtlinie, Verhalten und Template-Auflösung.
`show` zeigt Name, Adapter, Listen-Host/-Pfad, Detail-Verfügbarkeit, Modus, gemappte
Felder, Medienhosts und Template-Overrides; Headerwerte und URL-Queries fehlen.
Remote-Validierung wird nicht angeboten.

Im Checkout liegen Dateien unter `sources/` und `templates/`, unabhängig vom
Arbeitsverzeichnis. Beide Verzeichnisse verlinken auf
`common/src/kulturbytes_common/data/`, damit dieselben Assets in Wheel und sdist
enthalten sind. Installierte Anwendungen lesen zusätzlich
`$XDG_CONFIG_HOME/kulturbytes-social/{sources,templates}` (Standard:
`~/.config/kulturbytes-social/`). Ein relatives `XDG_CONFIG_HOME` wird ignoriert.
Quellendefinitionen werden ergänzt; doppelte Namen sind ein Fehler. Templates
dürfen die oben beschriebene lokale Priorität verwenden. Symlinks außerhalb des
jeweiligen Konfigurationsverzeichnisses werden abgelehnt.

## Adding a Source: Veranstaltungen, Orte und Artikel

Die mitgelieferten Beispiele sind ohne Python-Erweiterung nutzbar. Ihre
`example.org`-URLs sind Platzhalter, die vor einem Abruf durch echte Endpunkte
ersetzt werden müssen. Die Beispielantworten sehen so aus:

```json
{"events":[{"id":"e1","name":"Jazzabend","town":"Flensburg","start":"2099-10-01"}]}
```

```json
{"places":[{"id":"p1","name":"Stadtmuseum","city":"Flensburg","image":"https://images.example.org/p1.jpg"}]}
```

Der optionale Orts-Detailabruf für `p1` liefert:

```json
{"data":{"id":"p1","name":"Stadtmuseum","city":"Flensburg","image":"https://images.example.org/p1.jpg"}}
```

```json
{"items":[{"slug":"open-data-day","headline":"Open Data Day","body":"Offene Daten entdecken.","url":"https://example.org/article"}]}
```

Im Repository-Hauptverzeichnis lassen sich die drei Quellen kopieren:

```bash
cp sources/example-events.yaml sources/city-events.yaml
sed -i 's/^name: example-events$/name: city-events/' sources/city-events.yaml
cp sources/example-places.yaml sources/city-places.yaml
sed -i 's/^name: example-places$/name: city-places/' sources/city-places.yaml
cp sources/example-articles.yaml sources/city-articles.yaml
sed -i 's/^name: example-articles$/name: city-articles/' sources/city-articles.yaml
# In diesen drei YAML-Dateien die URL-Platzhalter und gegebenenfalls Medienhosts ersetzen.
uv run kulturbytes-social sources validate city-events
uv run kulturbytes-social sources validate city-places
uv run kulturbytes-social sources validate city-articles
uv run kulturbytes-social publish --platform facebook --source city-events --item-id e1
uv run kulturbytes-social publish --platform instagram --source city-places --item-id p1
uv run kulturbytes-social publish --platform mastodon --source city-articles --item-id open-data-day
```

Alternativ ist diese vollständige Artikelquelle direkt kopierbar:

```yaml
name: notices
adapter: json
endpoint: https://example.org/api/notices
root: items
mode: collection
fields:
  id: slug
  title: headline
  text: body
  link: url
```

Als `sources/notices.yaml` speichern, den Endpunkt ersetzen, lokal mit
`sources validate notices` prüfen und mit
`publish --platform facebook --source notices --item-id open-data-day` ansehen.
Ein eigenes Template ist optional; beispielsweise
`templates/notices/facebook.j2`:

```jinja2
{{ title }}
{% if text %}{{ text }}{% endif %}
{% if link %}{{ link }}{% endif %}
{{ tags | hashtags(city=city) }}
```

Bei einer installierten Anwendung werden eigene YAML-Dateien im oben beschriebenen
XDG-Quellenverzeichnis und Templates im XDG-Templateverzeichnis abgelegt. Den Befehl
dann als `kulturbytes-social` ohne `uv run` aufrufen. Die älteren Beispiele
`example-simple` und `example-nested` bleiben als Mapping-Kompatibilitätsbeispiele
enthalten.

## Lokale Daten

Jede Plattform behält ihre eigene SQLite-Datenbank und die bisherigen Veröffentlichungseinträge.
Im Checkout sind die Standardpfade fest am Repository verankert:

- `facebook/facebook_posts.sqlite3`
- `mastodon/mastodon_posts.sqlite3`
- `instagram/instagram_posts.sqlite3`

Bestehende Dateien an diesen Orten werden weiterverwendet. Bei einer separaten
Installation außerhalb eines Checkouts liegen die Dateien unter
`$XDG_DATA_HOME/kulturbytes-social/`, standardmäßig `~/.local/share/kulturbytes-social/`.
Ein Arbeitsverzeichniswechsel ändert diese Pfade nicht. Verzeichnisse werden erst
beim Initialisieren der Datenbank angelegt, nicht bei Hilfe oder Auth-Checks.

Verwende `FACEBOOK_DATABASE_PATH`, `INSTAGRAM_DATABASE_PATH` und
`MASTODON_DATABASE_PATH` für eigene Pfade. Pro Einstellung gilt `.env` vor
Prozessumgebung. Der plattformspezifische Schlüssel hat Vorrang vor `DATABASE_PATH`;
dieser alte Fallback funktioniert noch, meldet aber einmal pro Prozess eine
Veraltungswarnung. Ohne Override bleibt der Standardpfad erhalten. Absolute Werte
werden direkt verwendet, relative Werte beziehen sich auf das Standarddatenbankverzeichnis
der Plattform. Eine bereits einer anderen Plattform zugeordnete Datei oder ein
fremdes Veröffentlichungsschema wird beim Öffnen abgelehnt.
Dry-Runs können Tabellen anlegen, reservieren aber keinen Termin und schreiben
keine Veröffentlichung. `published_events` enthält weiterhin den jeweils letzten
bestätigten Post pro Termin; die Versuchshistorie steht im zusätzlichen Journal.

## Schutz bei API-, Medien- und Veröffentlichungsfehlern

Kulturbytes-Antworten werden am API-Eingang durch generische, in YAML definierte
Assertions und anschließend durch das strikte Pydantic-`ContentItem` geprüft.
Ein ungültiger Listeneintrag wird gemeldet und übersprungen; gültige Nachbarn bleiben
verwendbar. Eine ungültige Gesamtantwort oder direkt gewählte Veranstaltung führt
zum Fehler. Event-UUID, Termin-UUID und Slug müssen zwischen Liste und Details
übereinstimmen. IDs sind bewusst begrenzte, nicht leere Pfadsegmente statt strikt
geparster UUIDs, damit auch bestehende vereinfachte IDs gültig bleiben. Fehlende
optionale Felder und `null` werden berücksichtigt. Die Listenzusammenfassung hat
weiter Vorrang vor der Detailbeschreibung. „Heute“ richtet sich für alle Plattformen
nach `Europe/Berlin`, unabhängig von der Zeitzone des Rechners.

Bildabrufe richten sich nach `media.allowed_hosts` der jeweiligen Quelle,
immer über HTTPS/443. Kulturbytes erlaubt `api.kulturbytes.de`; generische Quellen
haben ohne Konfiguration keine Bildfreigabe. Alle DNS-Antworten müssen öffentlich
und nicht reserviert sein. Der Transport verbindet direkt zur geprüften IP mit
ursprünglichem Host-Header, TLS-SNI und Zertifikatsprüfung. Jede logische HTTPS-
Origin hat einen eigenen Verbindungspool, auch bei gemeinsam genutzter IP.

Jeder Retry und jeder der höchstens fünf expliziten Redirects durchläuft diese
Prüfung erneut. Ein eigener Medien-Client mit `trust_env=False` und direktem
HTTPX-Transport ignoriert `HTTP_PROXY`, `HTTPS_PROXY` und `ALL_PROXY`; API-Tokens,
Cookies und Auth-Konfiguration werden nicht übernommen. Dies gilt für Facebook,
Mastodon und die Instagram-JPEG-Prüfung. Instagram erhält weiterhin die geprüfte
öffentliche Host-URL; Metas eigener späterer Abruf unterliegt Metas Netzwerkschutz,
nicht unserem lokalen Transport. Download-Größenlimits bleiben Gegenstand von Issue #6.

Sichere GETs für Kulturbytes, Auth-Prüfungen, Instanzdaten, Polling und Medien
verwenden pro Retry-Folge denselben Client und höchstens drei Versuche bei 429/502/503/504,
ConnectTimeout, ReadTimeout und ConnectError. Die Wartezeiten betragen normalerweise
0,5 und 1 Sekunde; `Retry-After` (Sekunden oder HTTP-Datum) wird auf fünf Sekunden
pro Pause begrenzt. Ohne ausdrückliches `timeout=` übernimmt `safe_get` die
Timeouts des verwendeten Clients (im Publisher: Connect/Pool 10, Read/Write 60 Sekunden).
Ein ausdrückliches Override bleibt erhalten; es gibt keinen versteckten Fünf-Sekunden-Timeout
und keine zusätzliche globale Frist für DNS oder einen fortlaufenden Download. Bei gestreamten Medien
gelten die Retries bis zum Empfang der Header; ein abgebrochener Body wird nicht
fortgesetzt. **POSTs werden nie automatisch wiederholt**, auch Medienuploads und
Instagram-Container nicht. Die bestehenden fachlichen Polling-Intervalle bleiben.

## Veröffentlichungsjournal und Wiederherstellung

Jede Datenbank erhält zusätzlich `publisher_metadata` und `publication_attempts`.
Die erste Tabelle schützt vor einer versehentlichen Nutzung durch eine andere
Plattform. Das Journal speichert pro Versuch eine eigene UUID, Plattform, Termin,
Veranstaltungsmetadaten einschließlich `date_slug`, Zeitstempel, Zustand und
gegebenenfalls Remote-ID und -URL. `target_ref` enthält die numerische Facebook-Page-ID,
Instagram-User-ID oder die Mastodon-Instanzadresse ohne Zugangsdaten. `content_sha256`
ist ein deterministischer SHA-256 über Plattform, Event-/Termin-UUID, Slug und den
exakten bereits erzeugten Nachrichtentext. Der vollständige Text wird nicht gespeichert.
Tokens, Header und rohe API-Fehlerantworten gehören nicht ins Journal. Bestehende
Journal-Dateien erhalten die zusätzlichen Spalten automatisch; ältere Versuche
behalten unbekannte Werte, ohne erfundene Phasen oder Hashes. Bestehende `published_events`
bleiben erhalten; die Tabellen und der Index werden automatisch ergänzt.

Nach deiner Veröffentlichungsbestätigung wird der Termin atomar reserviert:
`reserved → publishing → remote_succeeded → published`. Ein partieller eindeutiger
Index sperrt aktive Versuche je Plattform und `date_uuid`. Kurze SQLite-Transaktionen
mit `BEGIN IMMEDIATE` und fünf Sekunden `busy_timeout` schützen auch zwischen
getrennten Prozessen. Andere Termine und Plattformen bleiben unabhängig. Das
bestehende SQLite-Journalformat wird beibehalten; WAL wird nicht erzwungen.

Vor jedem POST wird außerdem `mutation_stage` dauerhaft gesetzt:
`facebook_photo`, `facebook_feed`, `mastodon_media`, `mastodon_status`,
`instagram_container` oder `instagram_publish`. Die letzte Phase bleibt bei unklarem
Ergebnis sichtbar; die Fehlerklasse wird ohne rohe Fehlermeldung gespeichert.

Ein Fehler vor dem Remote-Aufruf oder eine eindeutige Ablehnung des POSTs kann den Versuch
als `failed` freigeben. Bei 408, unklarem Verbindungsabbruch oder 5xx bleibt
`publishing` gesperrt. Ein Fehler beim nachfolgenden Polling-GET bestätigt ebenfalls
nicht das Ergebnis des vorherigen POSTs und gibt den Versuch nicht frei. Sobald eine
Post-ID zurückkommt, wird sie als `remote_succeeded` gespeichert,
bevor `published_events` aktualisiert wird. Scheitert dieser zweite Schritt, ist die
ID aus dem Journal wiederherstellbar. Die abschließende Aktualisierung von
`published_events` und `published` erfolgt in einer gemeinsamen Transaktion. Auch
ein `resolve`-Aufruf übernimmt alle lokalen Änderungen atomar oder rollt sie zurück;
ein bereits zuvor gespeicherter Remote-Erfolg bleibt dabei erhalten. Ist bereits
die Speicherung der Remote-ID
unmöglich, bleibt die vorher gespeicherte Reservierung gesperrt; die Fehlermeldung
nennt die zurückgegebene ID. Ein Prozessabsturz zwischen Remote-Erfolg und Speicherung
kann ebenfalls einen unklaren Zustand hinterlassen. Das ist keine verteilte Transaktion.

Ungeklärte Versuche werden bei der Auswahl gemeldet und blockieren auch
`--include-published`. Sie laufen nicht automatisch ab. Zuerst den betroffenen
Publisher-Prozess stoppen und den tatsächlichen Beitrag auf der Plattform prüfen.
Anschließend das lokale Journal anzeigen:

```bash
uv run kulturbytes-social attempts list --platform facebook --active
uv run kulturbytes-social attempts list --platform mastodon --state remote_succeeded
uv run kulturbytes-social attempts list --platform instagram --date-uuid "$DATE_UUID"
uv run kulturbytes-social attempts list --platform facebook --limit 50
```

Die Liste zeigt standardmäßig die neuesten 50 Versuche zuerst; `--limit 0` zeigt alle.
`--active` umfasst `reserved`, `publishing` und `remote_succeeded`; mit einem
abgeschlossenen `--state` ist diese Option nicht kombinierbar. Filter und Limit
werden direkt in SQLite angewendet. Die Anzeige benötigt keine Zugangsdaten,
verändert keine Veröffentlichung und ruft kein Netzwerk auf.

Setze `ATTEMPT_UUID` auf die angezeigte Versuch-ID. Für einen bereits im Journal
bestätigten Remote-Erfolg repariert dieser Befehl ausschließlich die lokalen Daten:

```bash
uv run kulturbytes-social attempts resolve --platform facebook "$ATTEMPT_UUID" --outcome published
```

Bei einem unklaren Versuch mit manuell gefundenem Beitrag zusätzlich
`--remote-id "$REMOTE_POST_ID"` mit einer numerischen Post-ID angeben (Facebook
auch `page_post`; Mastodon optional `--remote-url` ohne Zugangsdaten, Query oder Fragment). Nur wenn
**sicher kein Beitrag entstanden ist**, darf eine Reservierung freigegeben werden:

```bash
uv run kulturbytes-social attempts resolve --platform facebook "$ATTEMPT_UUID" --outcome failed
```

Beide Befehle verlangen eine Bestätigung der manuellen Prüfung; ein gespeicherter
`remote_succeeded`-Zustand lässt sich nicht zu `failed` herabstufen. Ersetze `facebook`
bei Bedarf durch `mastodon` oder `instagram`. Diese Befehle benötigen keine Tokens
und machen keine Remote-Anfragen. Nach vollständigem Abschluss bleibt eine ausdrücklich
bestätigte Wiederveröffentlichung möglich; sie erhält eine neue Versuch-ID.

## Migration

Die alten Plattform-Executables und `main.py`-Wrapper sind entfernt:

| Alter Aufruf im Plattformordner | Neuer Aufruf im Repository-Hauptordner |
|---|---|
| `cd facebook` und `uv run main.py --publish` | `uv run kulturbytes-social facebook --publish` |
| `cd mastodon` und `uv run main.py --publish` | `uv run kulturbytes-social mastodon --publish` |
| `cd instagram` und `uv run main.py --publish` | `uv run kulturbytes-social instagram --publish` |

Auch die bisherigen Executables `kulturbytes-facebook`, `kulturbytes-mastodon`
und `kulturbytes-instagram` werden durch `kulturbytes-social PLATFORM` ersetzt.
Führe nach dem Update `uv sync --all-packages` aus.

Die bisherigen Standarddatenbanken in den Plattformordnern werden weiterbenutzt.
Falls du bisher einen anderen Pfad oder ein anderes Arbeitsverzeichnis genutzt hast,
setze **vor der nächsten Veröffentlichung** den passenden `<PLATFORM>_DATABASE_PATH` auf den absoluten Pfad
deiner bestehenden plattformspezifischen Datei. Dasselbe gilt beim Wechsel vom
Checkout zu einer separaten Installation: Es gibt keine automatische Kopie oder
Zusammenführung von Veröffentlichungshistorien. So bleibt die Duplikaterkennung erhalten.


## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Beim Start fehlt eine Umgebungsvariable | Setze die Zugangsdaten im selben Terminal, in dem du den Publisher startest. |
| Ein lokales Python-Paket wird nicht gefunden | Führe `uv sync --all-packages` im Repository-Hauptordner aus und behalte das Root-Paket unter `src/` und alle vier internen Paketordner. |
| Es stehen keine Termine zur Auswahl | Prüfe Stadtfilter und bereits veröffentlichte Termine. |
| Die Veröffentlichung schlägt fehl | Lies die API-Fehlermeldung und die Hinweise für deine Plattform. |

Weitere Hilfe findest du bei [Facebook](facebook/README.md#hilfe-bei-problemen)
und [Mastodon](mastodon/README.md#hilfe-bei-problemen).

## Bluesky

Bluesky ist über denselben Quellen-, Template- und Veröffentlichungsablauf verfügbar:

```bash
uv run kulturbytes-social bluesky --dry-run
uv run kulturbytes-social bluesky --publish
uv run kulturbytes-social publish --platform bluesky --source example-articles --item-id article-1 --publish
uv run kulturbytes-social bluesky --check-auth
```

Die Vorschau benötigt keine Bluesky-Zugangsdaten und erstellt weder eine Session
noch einen Blob oder Post. `--publish` prüft den Zugang vor Quellabruf und
Datenbankinitialisierung und verlangt die übliche Einzelbestätigung.
`--source`, `--item-id`, Stadt-/Limitfilter, interaktive Auswahl, die bestehenden
Legacy-Selektoren und `--include-published` funktionieren wie bei den anderen Plattformen.

In der lokalen `.env` konfigurieren:

```dotenv
BLUESKY_HANDLE=your-handle.bsky.social
BLUESKY_APP_PASSWORD=
BLUESKY_SERVICE_URL=https://bsky.social
BLUESKY_DATABASE_PATH=
```

Ein **Bluesky App Password** in `BLUESKY_APP_PASSWORD` eintragen, niemals das
primäre Kontopasswort. Die Service-URL muss das HTTPS-PDS des Kontos bezeichnen;
eigene PDS werden unterstützt. Handle und Service folgen `.env > Environment`.
Das App Password folgt `.env > Environment > OS-Keyring`; die bekannten Leerwertregeln
gelten weiterhin. Explizite Keyring-Verwaltung (keine Passwortwerte als CLI-Argumente):

```bash
uv run kulturbytes-social bluesky --credentials set
uv run kulturbytes-social bluesky --credentials status
uv run kulturbytes-social bluesky --credentials delete
```

Der Eintrag ist `kulturbytes-social/bluesky` / `app-password`.
`createSession` liefert einen nur im Arbeitsspeicher gehaltenen JWT und die DID;
die DID ist das Ziel von `createRecord`. Es gibt keine automatischen POST-Wiederholungen
oder Session-Erneuerungen. `--check-auth` erstellt nur eine Session, keinen Inhalt.

Die [Post-Lexicon](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/post.json)
erlaubt **300 Grapheme und 3000 UTF-8-Bytes**. Der Renderer kürzt nur ganze Wörter
des Beschreibungstexts; Titel, Links und erforderliche Hashtags bleiben erhalten.
Zu große feste Metadaten führen zu einem Fehler. URL-Facets verwenden UTF-8-Bytepositionen;
Mentions werden noch nicht aufgelöst. Kulturbytes-Branding bleibt im eigenen Jinja-Template.

Ein Bild wird über die bestehende HTTPS-/Host-/DNS-Sicherheitskette geladen und
anschließend per `uploadBlob` zum PDS gesendet. Das offizielle
[Image-Lexicon](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/embed/images.json)
erlaubt **2.000.000 Bytes pro Bild**. Größere Downloads werden vor dem Upload abgebrochen.
JPEG, PNG und WebP werden anhand von MIME-Typ und Dateisignatur geprüft.
Die Kulturbytes-Pluto-Vorgabe ist `bluesky: 4/3` / `jpg`; eine geringere Auflösung
kann bei zu großen Bildern helfen, garantiert aber keine Byte-Größe.
Alt-Text kommt aus `RenderedPost`; ungewisse transformierte Bildmaße werden nicht behauptet.

Die eigene `bluesky_posts.sqlite3` speichert die AT URI als Post-ID und optional
die öffentliche bsky.app-URL. Das Journal erfasst `bluesky_blob` und `bluesky_post`.
Unklare Ergebnisse sperren erneutes Posten, auch mit `--include-published`.
Nach Stoppen des Workers und manueller Plattformprüfung ist lokale Wiederherstellung möglich:

```bash
uv run kulturbytes-social attempts list --platform bluesky --active
uv run kulturbytes-social attempts resolve --platform bluesky ATTEMPT_UUID --outcome published --remote-id 'at://did:plc:ACCOUNT/app.bsky.feed.post/RECORD_KEY'
```

Die AT URI muss zur gespeicherten DID gehören. Bei sicher fehlendem Post kann nach
Prüfung stattdessen `--outcome failed` verwendet werden. Ein Blob-Upload allein
ist noch kein sichtbarer Post. Wiederherstellung benötigt keine Zugangsdaten und
führt keine Remote-Anfragen aus. App Passwords und JWTs gelangen weder an Quellen/
Bildserver noch in Ausgaben, Templates oder SQLite.

## Continuous Integration

[Tests](.github/workflows/tests.yml) und [CodeQL](.github/workflows/codeql.yml)
laufen bei Pushes auf `main` und Pull Requests gegen `main`. Die Tests verwenden
Python 3.12 und 3.13, den geprüften uv-Lockfile (`--locked`) und den vollständigen
Unittest-Lauf. Ein eigener Ruff-Job prüft Formatierung, Python-Fehler und Importreihenfolge.
Nur uv-Abhängigkeiten werden gecacht; Social-Zugangsdaten sind nicht erforderlich.

Die [offizielle CodeQL Action](https://github.com/github/codeql-action) analysiert
Python im gesamten Repository einschließlich aller Workspace-Pakete und Tests,
ohne Build-Schritt, mit `security-and-quality`-Queries. Ergebnisse erscheinen in
GitHub Code Scanning. Zusätzlich läuft die Analyse montags um 05:23 UTC.
Fork-PRs verwenden den regulären `pull_request`-Trigger ohne privilegierten
`pull_request_target`-Workflow. Die GitHub-Branch-Regeln für `main` verlangen
Pull Requests mit aktuellen, erfolgreichen Test-, Ruff- und CodeQL-Checks,
auch für Administratoren.

Lokale Entsprechung:

```bash
uv sync --all-packages --locked
uv run --all-packages --locked python -m unittest discover -s tests -v
uv run --locked ruff format --check .
uv run --locked ruff check .
git diff --check
```

Optional mit lokal installierter CodeQL CLI und Python-Query-Pack:

```bash
codeql database create .codeql-db --language=python --build-mode=none --source-root=.
codeql database analyze .codeql-db codeql/python-queries:codeql-suites/python-security-and-quality.qls --format=sarif-latest --output=codeql-python-security.sarif
```

Lokale CodeQL-Datenbanken und SARIF-Berichte sind ignorierte Arbeitsartefakte und
werden nicht eingecheckt. Die Workflows verwenden minimale Token-Berechtigungen,
Job-Timeouts und brechen überholte Läufe desselben Branches/PRs ab.

## Entwicklung

Die Root-CLI unter `src/kulturbytes_social/cli.py` registriert nur Befehle.
Plattformlogik bleibt in den drei Backend-Paketen; `common/` enthält die gemeinsamen
Workflows und Helfer. Neue Publisher werden als Unterbefehle ergänzt, beispielsweise
`kulturbytes-social bluesky`, ohne zusätzliche öffentliche Executables.

Das Root-Anwendungspaket und die vier internen Pakete bilden einen `uv`-Workspace mit einer gemeinsamen `uv.lock`.
Das Paket `kulturbytes-common` wird lokal eingebunden. Änderungen an gemeinsamen
Funktionen wirken auf alle Publisher.

```text
src/kulturbytes_social/cli.py   Root-Click-Gruppe
common/src/kulturbytes_common/
  sources/generic.py         Generische JSON-Listen-/Detail-Engine
  sources/rules.py           Kompilierte Assertions und sichere Mapping-Funktionen
  media.py        Richtliniengebundene Bilddownloads
  network.py      Öffentliches HTTPS, DNS-Pinning und getrennte Origin-Pools
  formatting.py   Gemeinsame Markdown-Bereinigung
  selection.py    Terminliste und interaktive Auswahl
  database.py     Prüfung auf bereits veröffentlichte Termine
  sources/        YAML/JMESPath, Adapter und ContentItem
  rendering.py    Zentraler Jinja-Renderer und sichere Textkürzung
  data/           Mitgelieferte YAML- und Jinja-Dateien
  storage.py      Neutrale Veröffentlichungsschlüssel und Zustandsabfragen
  legacy_storage.py  Kompatible Tabellen und Journal-Snapshots
  workflow.py     Quellenunabhängiges Laden, Filtern und Veröffentlichen
facebook/src/kulturbytes_facebook/cli.py
mastodon/src/kulturbytes_mastodon/cli.py
instagram/src/kulturbytes_instagram/cli.py
tests/test_publishers.py
tests/test_instagram.py
```

Die Plattformpakete enthalten Konfiguration, Vorschau, Bestätigung und API-Aufrufe.
Textkomposition, Mapping und gemeinsame Speicherung liegen in `common/`. Führe die gemeinsamen Tests im Repository-Hauptordner aus:

```bash
uv run --all-packages python -m unittest discover -s tests -v
```

Die Tests verwenden simulierte HTTP-Antworten, DNS, Schlafzeiten und temporäre Datenbanken.
Zusätzliche Regressionstests prüfen API-Modelle, Berliner Tagesgrenzen, GET-Retries,
SSRF/Redirects sowie Reservierungen über getrennte SQLite-Verbindungen und die
Wiederherstellung nach Remote-Erfolg mit anschließendem SQLite-Fehler.
Quellen- und Template-Tests prüfen YAML/JMESPath, strikte Typen, Sandbox, generische
CLI-Abläufe und zwölf gesicherte Kulturbytes-Ausgaben. Ein Installationstest baut
das Common-Wheel aus einer Quelldistribution und lädt seine Assets außerhalb des
Checkouts.

## Lizenz

[AGPL-3.0](LICENSE)
