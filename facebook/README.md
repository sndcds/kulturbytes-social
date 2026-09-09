# Kulturbytes Facebook Publisher

Teile Kulturbytes-Veranstaltungen auf deiner Facebook-Seite: Du wählst Termine
im Terminal aus, prüfst die Vorschau und bestätigst die Veröffentlichung.
Beim normalen Start bleibt es bei einer Vorschau.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Mastodon](../mastodon/README.md)

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv` und eine Internetverbindung.
Zum Veröffentlichen benötigst du zusätzlich
eine Facebook-Seiten-ID und den gemeinsamen Meta System User Access Token mit Zugriff auf diese Seite.
Behalte den gesamten Repository-Ordner: Der Publisher nutzt das gemeinsame
Paket in `common/`.

## Schnellstart

Öffne ein Terminal im Repository-Hauptordner. Installiere die Abhängigkeiten,
starte die Vorschau ohne Zugangsdaten:

```bash
uv sync --all-packages
uv run kulturbytes-social facebook --dry-run --limit 10
```

Das Programm zeigt bis zu zehn Termine. Gib beispielsweise `1` oder `1,3-5`
ein und drücke Enter, um die Vorschau zu sehen. `all` wählt alle angezeigten
Termine; eine leere Eingabe beendet die Auswahl. Es wird nichts veröffentlicht.

Alle weiteren Startbefehle auf dieser Seite führst du im Repository-Hauptordner aus.

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

## Konfiguration

Die Einstellungen werden aus den Umgebungsvariablen gelesen:

| Variable | Bedeutung | Standard |
|---|---|---|
| `FACEBOOK_PAGE_ID` | ID der Zielseite | für `--publish` und `--check-auth` erforderlich |
| `META_SYSTEM_USER_ACCESS_TOKEN` | Gemeinsamer Zugang für Facebook und Instagram | alternativ im OS-Keyring |
| `FACEBOOK_GRAPH_API_VERSION` | Verwendete Graph-API-Version | `v26.0` |
| `FACEBOOK_DATABASE_PATH` | Pfad zur lokalen Datenbank | `facebook_posts.sqlite3` |

Zugangsdaten werden erst für `--publish` und `--check-auth` geladen; validierte
primäre Fallback-Tokens werden dabei in `.env` übernommen.
`--dry-run`, `--help` und Modulimporte funktionieren ohne Zugangsdaten.
Die Vorschau lädt Veranstaltungsdaten aus der Kulturbytes-API.

Setze die Zugangsdaten vor dem Zugangstest oder einer Veröffentlichung:

```bash
export FACEBOOK_PAGE_ID="DEINE_NUMERISCHE_SEITEN_ID"
# Token verdeckt im gemeinsamen OS-Keyring speichern:
uv run kulturbytes-social facebook --credentials set
```

Die `export`-Befehle gelten für die aktuelle Terminal-Sitzung. Die deterministische `.env`
hat für Meta-Konfiguration Vorrang vor der Prozessumgebung. Bewahre echte Tokens außerhalb
der versionierten Dateien auf; `.env` und lokale Datenbanken sind bereits in
[`.gitignore`](../.gitignore) ausgeschlossen.

## Optionaler OS-Keyring

Meta-Tokens werden zuerst aus der deterministischen `.env`, dann aus der
Umgebung und schließlich aus dem OS-Keyring geladen. Eine vorhandene, aber leere Variable verhindert ebenfalls
den Keyring-Zugriff und zählt als fehlend. Hilfe und Dry-Run lesen keine Tokens.
`--publish` und `--check-auth` verwenden beide dieselbe Auflösung.

Im Repository-Hauptordner:

```bash
uv run kulturbytes-social facebook --credentials status
uv run kulturbytes-social facebook --credentials set --credential meta
uv run kulturbytes-social facebook --credentials delete --credential meta
```

Beim Speichern wird der Token verdeckt abgefragt. Status zeigt ausschließlich
vorhanden/nicht vorhanden; weder Werte, Teile, Längen noch Hashes werden ausgegeben.
Löschen verlangt eine Bestätigung und betrifft nur den Keyring, nicht `.env` oder Umgebung.
Die Verwaltung führt keine Netzwerk- oder Datenbankoperationen aus. Kombinationen
mit `--publish`, `--check-auth` oder `--resolve-page-token` sind nicht zulässig; Auswahloptionen werden ignoriert.
Die Paketbefehle akzeptieren dieselben Optionen.

Standardmäßig verwaltet dieser Befehl den gemeinsamen Meta-Token unter Service
`kulturbytes-social/meta`, Benutzername `system-user-access-token`. Instagram nutzt
denselben Eintrag; das Löschen betrifft beide Publisher. `FACEBOOK_PAGE_ID` bleibt
Konfiguration in `.env` oder Environment. Legacy-Selektoren `page` und `user` bleiben vorübergehend
mit Deprecation-Hinweis verfügbar; ohne Selektor wird immer `meta` verwendet.

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
uv run kulturbytes-social facebook --check-auth
```

Beispiel einer erfolgreichen Prüfung (Exitcode 0):

```text
✓ Facebook-Seite erreichbar: Kulturbytes (1173614782497494)
✓ Facebook Publishing-Ziel mit Meta System User Token validiert
```

Bei Fehlern endet der Check mit Exitcode 1, zum Beispiel `Error: Facebook Access Token ist abgelaufen.`
API-Fehler können zusätzlich HTTP-Status und bereinigte Details enthalten.
Tokens werden niemals angezeigt, auch wenn die API sie zurückgibt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und Auswahloptionen.
Es werden keine Kulturbytes-Termine geladen, keine Bilder oder Mediencontainer
erzeugt und keine Beiträge oder Datenbankeinträge geschrieben. Der Check verwendet
`GET /{version}/{page_id}?fields=id,name` und im gemeinsamen Meta-Pfad zunächst `/me/accounts`. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff,
aber nicht sämtliche Veröffentlichungsrechte. Siehe [Meta Pages API](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api).

Die zurückgegebene Seiten-ID muss mit `FACEBOOK_PAGE_ID` übereinstimmen.
Seiten-IDs müssen numerisch sein; die API-Version hat das Format `v26.0`.
Fehlende Zugangsdaten beenden `--publish` vor der Event-Abfrage.

## Termine auswählen und veröffentlichen

Starte mit einer kleinen Auswahl:

```bash
uv run kulturbytes-social facebook --publish --limit 10 --city Flensburg
```

Das Programm bietet freigegebene Termine ab dem heutigen Datum chronologisch
an und blendet bereits gespeicherte Veröffentlichungen aus. Wähle Nummern wie
`1,3-5` oder `all`. Vor jedem Beitrag erscheinen eine Vorschau und eine eigene
Bestätigungsfrage. Ohne Zustimmung wird dieser Termin übersprungen.

`--limit` begrenzt die angebotene Terminliste. Wie viele Beiträge entstehen,
entscheidest du mit deiner Auswahl und den Bestätigungen. Der Ablauf ist
interaktiv und eignet sich derzeit nicht für unbeaufsichtigte Timer-Läufe.

| Option | Wirkung | Standard |
|---|---|---|
| `--dry-run` | Vorschau der ausgewählten Beiträge anzeigen | aktiv |
| `--check-auth` | Nur Zugang prüfen, ohne Veröffentlichung | aus |
| `--publish` | Beiträge nach einzelner Bestätigung veröffentlichen | aus |
| `--limit 10` | Höchstens zehn Termine zur Auswahl anbieten | `50` |
| `--limit 0` | Alle passenden Termine zur Auswahl anbieten | — |
| `--city Flensburg` | Nach Stadt filtern, unabhängig von Groß- und Kleinschreibung | alle Städte |
| `--include-published` | Bereits veröffentlichte Termine mit zusätzlicher Rückfrage anbieten | aus |
| `--help` | Hilfe zu den Befehlen anzeigen | — |

Der einzige öffentliche CLI-Befehl ist `kulturbytes-social` mit dem Unterbefehl `facebook`. `DRY_RUN` und `MAX_POSTS_PER_RUN` werden nicht
als Umgebungsvariablen ausgewertet.

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

Der Publisher erstellt einen Fotobeitrag mit dem Veranstaltungsbild. Ist kein
Bild hinterlegt, erstellt er einen Textbeitrag. Der Text enthält je nach
verfügbaren Daten Titel, Untertitel, Datum, Uhrzeit, Ort, Adresse, Beschreibung,
Veranstalter, Eintrittsinformationen, Kulturbytes-Link und Hashtags.

Es entstehen Beiträge auf deiner Seite; eigenständige Facebook-Veranstaltungen
werden vom Programm nicht angelegt.

## Lokale Daten

Der Publisher verwendet im Checkout fest `facebook/facebook_posts.sqlite3`,
unabhängig vom Arbeitsverzeichnis. Bei einer Installation außerhalb eines Checkouts
liegt die Datei unter `$XDG_DATA_HOME/kulturbytes-social/` (Fallback:
`~/.local/share/kulturbytes-social/`). Ein Vorschau-Lauf darf die Datei anlegen. Erst nach einer
erfolgreichen Veröffentlichung speichert er die Termin-ID (`date_uuid`),
Veranstaltungsdaten und die Facebook-Post-ID.
So erkennt er beim nächsten Lauf bereits veröffentlichte Termine.

Behalte diese Datenbank bei einem Umzug oder Update. Mit `FACEBOOK_DATABASE_PATH` kannst
du einen anderen Pfad festlegen. Relative Werte beziehen sich auf das Verzeichnis
der Standarddatenbank, absolute Werte werden unverändert verwendet. Facebook und Mastodon benötigen
jeweils eine eigene Datenbank.

`--include-published` erlaubt nach zusätzlichen Bestätigungen auch eine erneute
Veröffentlichung eines bekannten Termins. Nach erfolgreicher Veröffentlichung
ersetzt der neue Eintrag die gespeicherte Facebook-Post-ID
für dieselbe `date_uuid` und aktualisiert Veranstaltungsdaten und `published_at`.
`published_events` speichert die letzte Veröffentlichung; das Journal bewahrt alle Versuche. Schlägt die Veröffentlichung
auf der Plattform fehl, bleibt der bisherige Datenbankeintrag unverändert.

## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Eine Zugangsdaten-Variable fehlt | Setze die erforderlichen Variablen unter „Konfiguration“ im selben Terminal. |
| Es stehen keine Termine zur Auswahl | Prüfe den Stadtfilter. Bereits veröffentlichte Termine siehst du mit `--include-published`; vergangene oder nicht freigegebene Termine werden ausgefiltert. |
| Facebook lehnt die Veröffentlichung ab | Prüfe die ausgegebene API-Antwort, die Seiten-ID sowie Gültigkeit und Veröffentlichungsrechte des Page Access Tokens. |
| Ein Fotobeitrag schlägt fehl | Prüfe die Bildadresse aus der Vorschau und die API-Fehlermeldung. Bei einem fehlerhaften Bild erfolgt kein automatischer Wechsel zum Textbeitrag. |
| Die Datenbank lässt sich nicht öffnen | Prüfe, ob der übergeordnete Ordner von `FACEBOOK_DATABASE_PATH` existiert und beschreibbar ist. |

Die verfügbaren Optionen zeigt `uv run kulturbytes-social facebook --help` auch ohne Zugangsdaten.

## Entwicklung

Der Plattformcode liegt in [`src/kulturbytes_facebook/cli.py`](src/kulturbytes_facebook/cli.py).
Gemeinsame API-Abfragen, Terminauswahl und Bilddownloads liegen in
[`common/`](../common/). Hinweise zur Struktur und zum Testlauf findest du in
der [Projektübersicht](../README.md#entwicklung).

Beim Wechsel von alten Aufrufen oder einer separaten Installation beachte die
[Migration und Datenbankpfade](../README.md#migration).

## Lizenz

[AGPL-3.0](../LICENSE)

## Gemeinsamer Meta System User Token

Der normale Zugang benötigt nur `META_SYSTEM_USER_ACCESS_TOKEN` aus `.env`, Environment
oder dem gemeinsamen Keyring. Der System User muss im Meta Business Portfolio der
App und der Zielseite mit passenden Rechten zugeordnet sein (unter anderem
`pages_show_list`, `pages_read_engagement`, `pages_manage_posts`; je nach Asset-Zugriff
auch `business_management`). Die Abfrage `/me/accounts?fields=id,name,access_token`
wählt die exakte `FACEBOOK_PAGE_ID` auch auf Folgeseiten. Cursor werden ausschließlich
am festen Graph-Endpunkt verwendet; fremde `paging.next`-URLs werden abgewiesen.
Der abgeleitete Page Token muss anschließend die Seiten-ID-/Namensprüfung bestehen.
Er wird nur im Speicher gehalten: keine Recovery-Frage, keine separate Tokenpflege
und kein Speichern des abgeleiteten Tokens. Auth-Fehler brechen vor Event-, Bild-
und Datenbankzugriffen ab. Ein API-Fehler löst keinen Legacy-Fallback aus.

## Legacy-Migration und frühere Recovery

Nur wenn kein gemeinsamer Token verfügbar ist, bleiben die bisherigen Page-/User-Tokens
als veralteter Fallback verfügbar: jeweils Environment vor altem OS-Keyring.
Auch eine leere gemeinsame Environment-Variable unterdrückt den gemeinsamen Keyring
und erlaubt Legacy-Fallback. Die Migration und Entfernung alter Einträge beschreibt
[die Projektübersicht](../README.md#migration-bestehender-meta-zugänge).

Im Legacy-Pfad validieren `--check-auth` und `--publish` zunächst den Page Token.
Fehlt er oder meldet Meta Code 190 (einschließlich Subcode 463), wird über den User
Token wiederhergestellt. Nur im TTY gibt es eine Bestätigung (Standard: Nein),
gegebenenfalls verdeckte User-Token-Eingabe und nach erfolgreicher Validierung eine
separate Speicherbestätigung. Ohne TTY muss der User Token bereits vorhanden sein.
Fehler verändern bestehende Credentials nicht. Die veraltete Option
`--resolve-page-token` erzwingt diese Ableitung; mit gemeinsamem Meta-Token entspricht
sie `--check-auth`. Beide Prüfoptionen haben Vorrang vor Veröffentlichung.

Die Kompatibilität bleibt für diese Übergangsversion bestehen; Entfernung erst nach
separater Ankündigung in einer kommenden inkompatiblen Version. Es gibt keinen
Browser-OAuth-Login, keine User-/System-Token-Erneuerung und keine automatische
System-User-Provisionierung. API-Grundlage: [Metas Pages-Token-Abfrage](https://www.postman.com/meta/facebook/request/bqfxwbp/get-access-tokens-of-pages-you-manage).

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

Mit `kulturbytes-social publish --platform facebook --source NAME` oder dem bisherigen
Plattformbefehl mit `--source NAME` lässt sich eine YAML-/JMESPath-Quelle auswählen; Standard bleibt
`kulturbytes`. `--item-id ID` wählt einen Eintrag direkt aus. Die bisherigen
`--event-uuid`/`--date-identifier`-Flags bleiben für Kulturbytes erhalten.
Textkomposition erfolgt zentral über Jinja2, mit optionalen Overrides unter
`templates/<quelle>/`. Einzelbestätigung, Dry Run, Authentifizierung und Bildschutz
bleiben erhalten. Einrichtung, kanonische Felder, stabile IDs, installierte
Konfigurationspfade und vollständige Beispiele stehen im
[Quellenleitfaden](../README.md#data-sources).
