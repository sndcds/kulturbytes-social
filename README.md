# Kulturbytes Publisher

Teile Kulturbytes-Veranstaltungen auf Facebook, Mastodon und Instagram. Du wählst die
gewünschten Termine im Terminal aus, siehst eine Vorschau und bestätigst jeden
Beitrag vor der Veröffentlichung. So behältst du die Kontrolle darüber, was
auf deiner Seite oder deinem Konto erscheint.

Wähle die Anleitung für deine Plattform:

| Plattform | Wofür du sie verwendest |
|---|---|
| [Facebook](facebook/README.md) | Veranstaltungsbeiträge auf einer Facebook-Seite veröffentlichen |
| [Mastodon](mastodon/README.md) | Veranstaltungsbeiträge auf einem Mastodon-Konto veröffentlichen |
| [Instagram](instagram/README.md) | Veranstaltungsbilder auf einem Instagram-Professional-Konto veröffentlichen |

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
uv run kulturbytes-social facebook --help
uv run kulturbytes-social mastodon --help
uv run kulturbytes-social instagram --help
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
`all` wählt alle angezeigten Termine; eine leere Eingabe beendet die Auswahl.
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

Alle Publisher übernehmen Veranstaltungsinformationen aus der Kulturbytes-API
und verlinken auf den Termin bei Kulturbytes. Vorhandene Veranstaltungsbilder
und Hashtags ergänzen die Beiträge.

Facebook verwendet einen ausführlichen Beitrag und veröffentlicht vorhandene
Bilder als Fotopost. Mastodon verwendet einen auf das Instanzlimit (Fallback: 500 Zeichen)
gekürzten Text und öffentliche Beiträge mit Alt-Text für Bilder. Die Details
stehen unter [Facebook](facebook/README.md#inhalt-der-beiträge) und
[Mastodon](mastodon/README.md#inhalt-der-beiträge). Instagram benötigt ein JPEG-Hauptbild
und verwendet bis zu 2.200 Zeichen sowie höchstens fünf erzeugte Hashtags; siehe
[Instagram](instagram/README.md#bild-und-beitragstext).

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

Kulturbytes-Antworten werden unmittelbar am API-Eingang mit Pydantic geprüft.
Ein ungültiger Listeneintrag wird gemeldet und übersprungen; gültige Nachbarn bleiben
verwendbar. Eine ungültige Gesamtantwort oder direkt gewählte Veranstaltung führt
zum Fehler. Event-UUID, Termin-UUID und Slug müssen zwischen Liste und Details
übereinstimmen. IDs sind bewusst begrenzte, nicht leere Pfadsegmente statt strikt
geparster UUIDs, damit auch bestehende vereinfachte IDs gültig bleiben. Fehlende
optionale Felder und `null` werden berücksichtigt. Die Listenzusammenfassung hat
weiter Vorrang vor der Detailbeschreibung. „Heute“ richtet sich für alle Plattformen
nach `Europe/Berlin`, unabhängig von der Zeitzone des Rechners.

Bildabrufe sind auf **`https://api.kulturbytes.de` (Port 443)** beschränkt; dieser
Medienhost ist durch die vorhandenen Kulturbytes-Beispiele belegt. Andere Hosts,
IP-URLs und eingebettete Zugangsdaten werden abgelehnt. Alle DNS-Antworten müssen
öffentliche, nicht reservierte Adressen sein. Der Medien-Transport verbindet
anschließend direkt zur geprüften numerischen IP. Der ursprüngliche Host-Header
und TLS-SNI bleiben `api.kulturbytes.de`; die Zertifikatsprüfung bleibt aktiviert.
Damit kann ein Wechsel der DNS-Antwort zwischen Prüfung und Verbindung den
lokalen Medienabruf nicht auf eine private Adresse umlenken.

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
  events.py       API-Abfragen und Veranstaltungsinformationen
  media.py        Bildadressen und Bilddownloads
  formatting.py   Gemeinsame Markdown-Bereinigung
  selection.py    Terminliste und interaktive Auswahl
  database.py     Prüfung auf bereits veröffentlichte Termine
  workflow.py     Laden, Filtern, Sortieren und Veröffentlichen
facebook/src/kulturbytes_facebook/cli.py
mastodon/src/kulturbytes_mastodon/cli.py
instagram/src/kulturbytes_instagram/cli.py
tests/test_publishers.py
tests/test_instagram.py
```

Die Plattformpakete enthalten ihre Konfiguration, Postformatierung, API-Aufrufe
und Datenbankschemata. Führe die gemeinsamen Tests im Repository-Hauptordner aus:

```bash
uv run --all-packages python -m unittest discover -s tests -v
```

Die Tests verwenden simulierte HTTP-Antworten, DNS, Schlafzeiten und temporäre Datenbanken.
Zusätzliche Regressionstests prüfen API-Modelle, Berliner Tagesgrenzen, GET-Retries,
SSRF/Redirects sowie Reservierungen über getrennte SQLite-Verbindungen und die
Wiederherstellung nach Remote-Erfolg mit anschließendem SQLite-Fehler.

## Lizenz

[AGPL-3.0](LICENSE)
