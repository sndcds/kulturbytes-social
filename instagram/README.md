# Kulturbytes Instagram Publisher

Veröffentliche Kulturbytes-Termine als Instagram-Bildbeiträge. Du wählst einen
Termin aus, prüfst Bildadresse und Text und bestätigst die Veröffentlichung.
Die Vorschau funktioniert ohne Instagram-Zugangsdaten.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Mastodon](../mastodon/README.md)

## Schnellstart

Im Repository-Hauptordner:

```bash
uv sync --all-packages
uv run kulturbytes-social instagram --dry-run --limit 10
```

Wähle beispielsweise `1` oder `1,3-5`. `all` wählt alle angebotenen Termine;
eine leere Eingabe beendet die Auswahl. Die Vorschau lädt Kulturbytes-Daten
und prüft, ob die Bildadresse JPEG-Daten liefert. Sie ruft keine Instagram-API auf.

Direkte Auswahl, im Repository-Hauptordner:

```bash
uv run kulturbytes-social instagram --event-uuid "EVENT_UUID" --date-identifier "202609101830"
```

Ersetze `EVENT_UUID` durch die Veranstaltungs-UUID. Die Terminkennung kann
`date_slug` oder `date_uuid` sein. Beide Optionen sind zusammen erforderlich.
Der Termin wird in `/api/events` gesucht und über den gefundenen Slug angereichert.

## Primäre lokale `.env`

Meta-Konfiguration folgt **`.env > Prozess-Environment > OS-Keyring > verdeckte TTY-Eingabe**.
Im Checkout gilt immer `<repo>/.env`, unabhängig vom Arbeitsverzeichnis. Installiert
außerhalb des Checkouts: `$XDG_CONFIG_HOME/kulturbytes-social/.env`, mit Fallback
`~/.config/kulturbytes-social/.env` (relative XDG-Werte werden ignoriert).
Die gemeinsame Datei enthält `META_SYSTEM_USER_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID`
und `INSTAGRAM_USER_ID`; beide Publisher verwenden denselben primären Token.

`--check-auth` und `--publish` validieren zuerst das exakte Ziel. Erst danach werden
primäre Tokens aus Environment, Keyring oder versteckter Eingabe automatisch in `.env`
gespeichert; der aktuelle Aufruf arbeitet mit dem validierten Wert im Speicher weiter.
Validierungsfehler lassen Datei, Keyring und Veröffentlichungsdatenbank unverändert.
Schreibfehler brechen vor Veröffentlichung ab. Die Originalquelle wird nicht verändert.
Fehlende Tokens werden nur im TTY abgefragt; ohne TTY wird klar abgebrochen. Dry Runs
und Hilfe starten keinen Bootstrap. Ein ungültiger `.env`-Token muss korrigiert oder
entfernt werden; es gibt keinen stillen Wechsel zu einem anderen Token.

Leere `.env`-Tokenwerte erlauben Fallback; leere Prozess-Tokenvariablen unterdrücken
weiterhin den Keyring für denselben Token. IDs und Meta-API-Einstellungen werden ebenfalls
aus `.env` vor Environment gelesen. Bestehende Kommentare und fremde Variablen bleiben
beim atomaren Update erhalten. POSIX-Rechte: `0600`, auch für bereits validierte Dateien.
Temporäre Dateien werden aufgeräumt; Symlinks werden abgewiesen. **Never commit .env.**
Abgeleitete Page-Tokens und Legacy-Tokens werden nie als primärer Meta-Token persistiert.
CI/systemd können weiter Environment verwenden, benötigen nach Validierung aber einen
beschreibbaren Konfigurationspfad. Details: [Projektübersicht](../README.md#lokale-env-als-primäre-meta-konfiguration).

## Zugangsdaten und Veröffentlichung

Du benötigst ein Instagram-Professional-Konto (Business oder Creator), eine passend
konfigurierte Meta-App und einen gültigen Token mit Veröffentlichungsrechten.
Das Programm übernimmt bestehende Zugangsdaten; es implementiert keinen OAuth-Login
und keine automatische Token-Erneuerung.

Der bevorzugte Zugang verwendet denselben `META_SYSTEM_USER_ACCESS_TOKEN` wie Facebook
über die **Instagram API mit Facebook Login** (`graph.facebook.com`). Der Meta System
User muss im Business Portfolio Zugriff auf App, Facebook-Seite und das damit
verknüpfte Instagram-Professional-Konto erhalten haben. Die erforderlichen Rechte
umfassen `instagram_basic` und `instagram_content_publish`; für Seitenzugriff können
zusätzlich `pages_show_list`, `pages_read_engagement` und `business_management` nötig sein.
`INSTAGRAM_USER_ID` ist die numerische Instagram-Konto-ID für diesen API-Modus,
nicht die Facebook-Seiten-ID. IDs aus einem anderen Login-Modus müssen geprüft werden.
Siehe [Metas Instagram-API-Dokumentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-8365d531-b49f-4e07-8e76-19f8608947a3)
für User-/System-User-Tokens und die Facebook-Login-API.

```bash
export INSTAGRAM_USER_ID="DEINE_NUMERISCHE_INSTAGRAM_KONTO_ID"
export INSTAGRAM_LOGIN_TYPE="facebook"
# Einmal für Facebook und Instagram gemeinsam, mit verdeckter Eingabe:
uv run kulturbytes-social instagram --credentials set
uv run kulturbytes-social instagram --check-auth
uv run kulturbytes-social instagram --publish --event-uuid "EVENT_UUID" --date-identifier "202609101830"
```

Alternativ kann `META_SYSTEM_USER_ACCESS_TOKEN` extern in der Umgebung bereitgestellt
werden. Der Token wird direkt für Zielprüfung und Container-/Publish-Aufrufe verwendet.
Vor jedem Beitrag erscheint weiterhin eine Bestätigungsfrage. Ohne Zustimmung entstehen
weder Mediencontainer noch Beitrag. Ohne `--publish` bleibt es beim Dry-Run.

| Variable | Bedeutung | Standard |
|---|---|---|
| `INSTAGRAM_USER_ID` | Numerische Instagram-Konto-ID | erforderlich für Auth/Publish |
| `META_SYSTEM_USER_ACCESS_TOKEN` | Gemeinsamer Meta-Zugang | alternativ im OS-Keyring |
| `INSTAGRAM_LOGIN_TYPE` | API-Modus | `facebook` mit Meta-Token; `instagram` mit Legacy-Token |
| `INSTAGRAM_GRAPH_API_VERSION` | Graph-Version | `v26.0` |
| `INSTAGRAM_DATABASE_PATH` | Optionaler SQLite-Pfad | stabiler Plattform-State-Pfad, siehe unten |

### Legacy-Migration

Der gemeinsame Token aus `.env`, Environment bzw. Keyring hat Vorrang vor
`INSTAGRAM_ACCESS_TOKEN` und dem alten Instagram-Keyring. Nur wenn kein gemeinsamer
Token verfügbar ist, wird der Legacy-Zugang mit Deprecation-Hinweis verwendet.
Ein leerer Meta-Environment-Wert unterdrückt den gemeinsamen Keyring und erlaubt
Legacy-Fallback. Ungültige gemeinsame Tokens lösen keinen Legacy-Fallback aus.

Legacy-Zugänge behalten beide bisherigen Modi: `instagram` (bisheriger Standard)
mit `graph.instagram.com` und `instagram_business_basic` / `instagram_business_content_publish`,
oder `facebook` mit passendem Legacy-Token. Ein explizites `INSTAGRAM_LOGIN_TYPE=instagram`
zusammen mit gemeinsamem Meta-Token ist ein Konfigurationsfehler; der Token wird niemals
an `graph.instagram.com` gesendet. Zur Migration den gemeinsamen Token speichern,
`INSTAGRAM_LOGIN_TYPE=facebook` setzen oder die alte Variable entfernen und `--check-auth`
ausführen. Den alten Eintrag optional mit `--credentials delete --credential access` löschen.
Er bleibt bis zu einer separat angekündigten inkompatiblen Version unterstützt.
Keine automatische Token-Migration, OAuth-Anmeldung oder System-User-/Asset-Provisionierung.

## Optionaler OS-Keyring

Meta-Tokens werden zuerst aus der deterministischen `.env`, dann aus der
Umgebung und schließlich aus dem OS-Keyring geladen. Eine vorhandene, aber leere Variable verhindert ebenfalls
den Keyring-Zugriff und zählt als fehlend. Hilfe und Dry-Run lesen keine Tokens.
`--publish` und `--check-auth` verwenden beide dieselbe Auflösung.

Im Repository-Hauptordner:

```bash
uv run kulturbytes-social instagram --credentials status
uv run kulturbytes-social instagram --credentials set
uv run kulturbytes-social instagram --credentials delete
```

Beim Speichern wird der Token verdeckt abgefragt. Status zeigt ausschließlich
vorhanden/nicht vorhanden; weder Werte, Teile, Längen noch Hashes werden ausgegeben.
Löschen verlangt eine Bestätigung und betrifft nur den Keyring, nicht `.env` oder Umgebung.
Die Verwaltung führt keine Netzwerk- oder Datenbankoperationen aus. Kombinationen
mit `--publish` oder `--check-auth` sind nicht zulässig; Auswahloptionen werden ignoriert.
Die Paketbefehle akzeptieren dieselben Optionen.

Standard und `--credential meta`: Service `kulturbytes-social/meta`, Benutzername
`system-user-access-token`, gemeinsam mit Facebook. Löschen betrifft beide Publisher.
`--credential access` verwaltet vorübergehend den veralteten Instagram-Eintrag
unter `kulturbytes-social/instagram` / `access-token`.
Meta-Kontokonfiguration wird aus `.env` vor Umgebungsvariablen gelesen.

Keyring ist optional. Auf Ubuntu können `sudo apt install gnome-keyring libsecret-tools`
und eine entsperrte Secret-Service-Sitzung benötigt werden. Die Python-Abhängigkeit
`keyring` wird über `uv sync --all-packages` installiert; die Anwendung ruft kein
`secret-tool` auf und akzeptiert keine Klartext-Keyring-Backends. Die primäre `.env`
wird separat mit restriktiven Dateirechten verwaltet. Backend-Fehler werden
als bereinigte Click-Fehler angezeigt. Umgebungsvariablen funktionieren auch bei
kaputtem Keyring. Server können extern bereitgestellte Systemd-Credentials bevorzugen;
eine automatische Provisionierung ist nicht enthalten. Details und unterstützte
OS-Backends: [Projektübersicht](../README.md#tokens-optional-im-os-keyring-speichern).

## Zugang ohne Veröffentlichung prüfen

Im Repository-Hauptordner, nach dem Setzen der Zugangsdaten:

```bash
uv run kulturbytes-social instagram --check-auth
```

Beispiel einer erfolgreichen Prüfung (Exitcode 0):

```text
✓ Instagram Token gültig
✓ Konto: @kulturbytes
✓ Login-Typ: facebook
```

Bei Fehlern endet der Check mit Exitcode 1, zum Beispiel `Error: Instagram-Zugriff konnte nicht validiert werden.`
API-Fehler können zusätzlich HTTP-Status und bereinigte Details enthalten.
Tokens werden niemals angezeigt, auch wenn die API sie zurückgibt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und Auswahloptionen.
Es werden keine Kulturbytes-Termine geladen, keine Bilder oder Mediencontainer
erzeugt und keine Beiträge oder Datenbankeinträge geschrieben. Der Check verwendet
nur `GET /{version}/{user_id}?fields=id,username`. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff,
aber nicht sämtliche Veröffentlichungsrechte. Siehe [Meta Instagram API](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api).

Der Graph-Host folgt `INSTAGRAM_LOGIN_TYPE`: `graph.instagram.com` für
`instagram`, `graph.facebook.com` für `facebook`. Die zurückgegebene Konto-ID
muss mit `INSTAGRAM_USER_ID` übereinstimmen. Hilfe und Dry-Run benötigen keine Tokens;
`--publish` validiert dieselbe Konto-ID vor Event-, Bild- und Datenbankzugriffen.

## Auswahloptionen

| Option | Wirkung |
|---|---|
| `--dry-run` | Vorschau und Bildprüfung, Standard |
| `--check-auth` | Nur Zugang prüfen, ohne Veröffentlichung |
| `--publish` | Nach Bestätigung veröffentlichen |
| `--limit N` | Anzahl angebotener Termine; Standard 50, 0 zeigt alle |
| `--city Flensburg` | Stadtfilter ohne Beachtung der Groß-/Kleinschreibung |
| `--include-published` | Bekannte Termine mit zusätzlicher Bestätigung anbieten |
| `--event-uuid UUID --date-identifier ID` | Einzeltermin direkt auswählen; Slug oder Termin-UUID |
| `--help` | Befehlshilfe, ohne Zugangsdaten |

Freigabe-, Datums-, Stadt- und Duplikatfilter gelten auch für die direkte Auswahl.
`--limit` schließt einen direkt gewählten Termin nicht aus. Nicht gefundene oder
gefilterte direkte Termine liefern einen Fehler-Exitcode.

Der einzige öffentliche CLI-Befehl ist `kulturbytes-social` mit dem Unterbefehl `instagram`.

## Bild und Beitragstext

Verwendet wird das Hauptbild aus `images.main.url` der Detailantwort.
Instagram benötigt für diesen Ablauf ein öffentlich erreichbares JPEG. Ohne Bild
oder bei einem anderen Format wird der Termin mit einer Fehlermeldung abgebrochen.
Eine lokale Konvertierung allein genügt nicht: Meta lädt das Bild selbst über die
öffentliche URL. Das Tool verändert und hostet keine Bilder. Die lokale Prüfung
erkennt die JPEG-Signatur; weitere Bildvorgaben und die Erreichbarkeit von Metas
Servern prüft die Instagram-API. Unterstützt werden einzelne Feed-Bildbeiträge.
Reels, Stories, Carousels und Alt-Text-Übertragung sind nicht implementiert.

Der Text verwendet bevorzugt `summary` aus `/api/events`, sonst `description`
aus der Detailantwort. Titel, Datum, Ort, optionale Eintritts-/Ticketinformationen,
Veranstalter und der Kulturbytes-Link ergänzen ihn. Der gemeinsame Helfer bereinigt
einfache Markdown-Auszeichnungen und Markdown-Links.

Das Tool begrenzt die Bildunterschrift auf 2.200 Zeichen und erzeugt höchstens fünf
Hashtags: zuerst `#Kulturbytes` und die Stadt, danach weitere Event-Tags. Das ist die
konservative Begrenzung dieses Publishers. Bei Platzmangel wird der Beschreibungstext
gekürzt. Kulturbytes-Link und erzeugte Hashtags bleiben vollständig; sind bereits die
festen Metadaten zu lang, wird der Termin mit einer Fehlermeldung abgebrochen.

## Veröffentlichungsablauf und lokale Daten

Nach deiner Bestätigung erzeugt `POST /{INSTAGRAM_USER_ID}/media` einen Container
mit `image_url` und `caption`. Das Tool prüft dessen `status_code` bis zu fünfmal
im Abstand von 60 Sekunden. Erst bei `FINISHED` ruft es
`POST /{INSTAGRAM_USER_ID}/media_publish` auf. Fehler oder Zeitüberschreitungen
beenden den Vorgang. Beschreibung des Ablaufs:
[Meta Content Publishing](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-ab559ffb-8e2c-4b0a-b43a-5737b6d2f672).

Erst die bestätigte Medien-ID wird zusammen mit der `date_uuid` in
`instagram_posts.sqlite3` gespeichert. Nutze eine eigene Datenbank für Instagram;
im Checkout liegt sie fest unter `instagram/`, bei einer separaten Installation
unter `$XDG_DATA_HOME/kulturbytes-social/` (Fallback: `~/.local/share/kulturbytes-social/`). Ein Dry-Run darf
die Datei anlegen, speichert aber keine Veröffentlichung. Bewahre die Datenbank auf,
damit bereits veröffentlichte Termine weiter erkannt werden. `INSTAGRAM_DATABASE_PATH` mit
einem absoluten Pfad verwendet deine bestehende Datei; relative Werte beziehen
sich auf das Standarddatenbankverzeichnis, nicht auf das Arbeitsverzeichnis.

Bei einer ausdrücklich bestätigten Wiederveröffentlichung ersetzt der neue
Instagram-Eintrag den bisherigen Eintrag in `published_events`; das Journal bewahrt die Versuchshistorie.
Scheitert die abschließende Anfrage durch einen Verbindungsabbruch, kann der Beitrag
remote trotzdem entstanden sein. Der ungeklärte Versuch bleibt gesperrt; prüfe das Konto und löse ihn ausdrücklich auf.
Das Tool wiederholt Veröffentlichungsanfragen nicht automatisch.

## Tests

Im Repository-Hauptordner:

```bash
uv run --all-packages python -m unittest discover -s tests -v
```

Die Instagram-Tests verwenden simulierte HTTP-Antworten und temporäre Datenbanken.
Sie veröffentlichen keine echten Beiträge.

Beim Wechsel von alten Aufrufen oder einer separaten Installation beachte die
[Migration und Datenbankpfade](../README.md#migration).

## Lizenz

[AGPL-3.0](../LICENSE)

## Gemeinsame Schutzmechanismen

Der plattformspezifische Datenbankpfad folgt `.env` vor Prozessumgebung. Fehlt er,
gilt noch `DATABASE_PATH` mit Veraltungswarnung, danach der bisherige Standard.
Ein fremdes Plattform-Schema wird abgelehnt. Bestehende Veröffentlichungen bleiben
bei der automatischen Ergänzung von `publisher_metadata`, `publication_attempts`
und dem eindeutigen Reservierungsindex erhalten.

API-Antworten werden vor der Verwendung validiert; „heute“ meint `Europe/Berlin`.
Medien folgen `media.allowed_hosts` der Quelle, ausschließlich über HTTPS/443.
Kulturbytes erlaubt `api.kulturbytes.de`; generische Quellen konfigurieren eigene Hosts. Der gemeinsame Transport
verbindet direkt zur geprüften öffentlichen IP mit ursprünglichem Host-Header,
TLS-SNI und aktivierter Zertifikatsprüfung. DNS-Rebinding und Umgebungs-Proxys können
diese lokale Zielbindung nicht umgehen; Medien verwenden `trust_env=False`.
Sichere GETs haben höchstens drei Versuche und respektieren die Client-Timeouts oder
ausdrückliche Overrides. POSTs werden nie automatisch wiederholt. Größenlimits
bleiben in Issue #6 offen; Metas eigener Bildabruf wird nicht durch unseren Transport gesteuert.

Jeder bestätigte Publish-Versuch reserviert den Termin vor dem Remote-Aufruf.
Remote-Erfolg wird vor der abschließenden lokalen Speicherung journalisiert.
Vor jedem POST steht die genaue `mutation_stage` im Journal. Termin-Slug,
`target_ref` und ein `content_sha256` des tatsächlich verwendeten Textes helfen bei
der Zuordnung. Tokens und vollständige Nachrichtentexte werden nicht gespeichert.
Die neuen Spalten werden ohne Datenverlust ergänzt; bestehende Versuche behalten
unbekannte Kontextwerte. Abschließende lokale Speicherung und Wiederherstellung
haben jeweils einen gemeinsamen Transaktionsrahmen.
Unklare oder teilweise abgeschlossene Versuche blockieren auch `--include-published`
bis zur manuellen Auflösung. Dry-Runs und abgelehnte Bestätigungen reservieren nichts.
Die [Projektanleitung](../README.md#veröffentlichungsjournal-und-wiederherstellung)
beschreibt `kulturbytes-social attempts list` mit `--active`, `--state`,
`--date-uuid`, `--limit` (neueste 50 zuerst; 0 = alle) und `attempts resolve`, einschließlich
der nötigen Prüfung nach einem Prozessabsturz. Dafür sind keine Tokens erforderlich.

## Konfigurierbare Quellen und Templates

Mit `kulturbytes-social publish --platform instagram --source NAME` oder dem bisherigen
Plattformbefehl mit `--source NAME` lässt sich eine YAML-/JMESPath-Quelle auswählen; Standard bleibt
`kulturbytes`. `--item-id ID` wählt einen Eintrag direkt aus. Die bisherigen
`--event-uuid`/`--date-identifier`-Flags bleiben für Kulturbytes erhalten.
Textkomposition erfolgt zentral über Jinja2, mit optionalen Overrides unter
`templates/<quelle>/`. Einzelbestätigung, Dry Run, Authentifizierung und Bildschutz
bleiben erhalten. Einrichtung, kanonische Felder, stabile IDs, installierte
Konfigurationspfade und vollständige Beispiele stehen im
[Quellenleitfaden](../README.md#data-sources).
