# Kulturbytes Mastodon Publisher

Teile Kulturbytes-Veranstaltungen auf deinem Mastodon-Konto: Du wählst Termine
im Terminal aus, prüfst die Vorschau und bestätigst die Veröffentlichung.
Beim normalen Start bleibt es bei einer Vorschau.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Mastodon](../mastodon/README.md)

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv` und eine Internetverbindung.
Zum Veröffentlichen benötigst du zusätzlich
die Adresse deiner Mastodon-Instanz und einen Access Token für dein Konto, der Beiträge veröffentlichen und Medien hochladen darf.
Behalte den gesamten Repository-Ordner: Der Publisher nutzt das gemeinsame
Paket in `common/`.

## Schnellstart

Öffne ein Terminal im Repository-Hauptordner. Installiere die Abhängigkeiten,
starte die Vorschau ohne Zugangsdaten:

```bash
uv sync --all-packages
uv run kulturbytes-social mastodon --dry-run --limit 10
```

Das Programm zeigt bis zu zehn Termine. Gib beispielsweise `1` oder `1,3-5`
ein und drücke Enter, um die Vorschau zu sehen. `all` wählt alle angezeigten
Termine; eine leere Eingabe beendet die Auswahl. Es wird nichts veröffentlicht.

Alle weiteren Startbefehle auf dieser Seite führst du im Repository-Hauptordner aus.

## Konfiguration

Token und Instanzadresse verwenden dieselben zentralen Resolver wie die anderen
Publisher: **`.env > Prozess-Environment > OS-Keyring`** für den Token und
**`.env > Prozess-Environment > Standard`** für `MASTODON_BASE_URL`.
`MASTODON_DATABASE_PATH` folgt ebenfalls `.env` vor Prozessumgebung.

| Variable | Bedeutung | Standard |
|---|---|---|
| `MASTODON_BASE_URL` | Adresse deiner Mastodon-Instanz | `https://norden.social` |
| `MASTODON_ACCESS_TOKEN` | Access Token für dein Konto auf dieser Instanz | für `--publish` und `--check-auth` erforderlich |
| `MASTODON_DATABASE_PATH` | Pfad zur lokalen Datenbank | `mastodon_posts.sqlite3` |

Zugangsdaten werden erst für `--publish` und `--check-auth` geladen.
`--dry-run`, `--help` und Modulimporte funktionieren ohne Zugangsdaten.
Die Vorschau lädt Veranstaltungsdaten aus der Kulturbytes-API.

Trage die Zugangsdaten in die lokale `.env` ein:

```dotenv
MASTODON_BASE_URL=https://norden.social
MASTODON_ACCESS_TOKEN=DEIN_ACCESS_TOKEN
```

Ein separates `export MASTODON_ACCESS_TOKEN=...` ist nicht erforderlich, wenn der
Token in `.env` vorhanden ist. Im Checkout wird immer `<repo>/.env` verwendet,
unabhängig vom Arbeitsverzeichnis. Installiert außerhalb eines Checkouts gilt
`$XDG_CONFIG_HOME/kulturbytes-social/.env` oder `~/.config/kulturbytes-social/.env`.
Relative XDG-Pfade werden ignoriert. Die Datei kann zugleich die Meta-Konfiguration
für Facebook und Instagram enthalten. **Never commit .env.** Verwende unter POSIX
`0600`-Rechte; `.env` ist in [`.gitignore`](../.gitignore) ausgeschlossen.

Leere oder nur aus Leerzeichen bestehende `.env`-Tokenwerte erlauben Fallback zur
Prozessumgebung. Eine explizit leere Prozess-Tokenvariable unterdrückt den Keyring.
Für die Instanzadresse überschreibt auch ein leerer `.env`-Wert die Umgebung und
führt zum bestehenden Validierungsfehler. Fehlt die Adresse überall, gilt `https://norden.social`.

Mastodon übernimmt keine Tokens automatisch in `.env` und startet keine interaktive
Auth-Einrichtung. Fehlende Zugangsdaten führen zum Fehler. `--check-auth` bleibt
lesend; Dry Runs benötigen weder Token noch Keyring und lesen die Instanzadresse
für die öffentliche Limit-Abfrage. Beim Veröffentlichen wird dieselbe einmal geladene
Konfiguration für Instanzlimit, Medienupload, Medienprüfung und Status verwendet.

## Optionaler OS-Keyring

Tokens werden zuerst aus `.env`, dann aus der Prozessumgebung und schließlich aus
dem OS-Keyring geladen. Eine vorhandene, aber leere Variable verhindert ebenfalls
den Keyring-Zugriff und zählt als fehlend. Hilfe und Dry-Run lesen keine Tokens.
`--publish` und `--check-auth` verwenden beide dieselbe Auflösung.

Im Repository-Hauptordner:

```bash
uv run kulturbytes-social mastodon --credentials status
uv run kulturbytes-social mastodon --credentials set
uv run kulturbytes-social mastodon --credentials delete
```

Beim Speichern wird der Token verdeckt abgefragt. Status zeigt ausschließlich
vorhanden/nicht vorhanden und die Quelle (`.env`, `Environment` oder `OS-Keyring`);
weder Werte, Teile, Längen noch Hashes werden ausgegeben.
Löschen verlangt eine Bestätigung und betrifft nur den Keyring, nicht `.env` oder die Umgebung.
Die Verwaltung führt keine Netzwerk- oder Datenbankoperationen aus. Kombinationen
mit `--publish` oder `--check-auth` sind nicht zulässig; Auswahloptionen werden ignoriert.
Die Paketbefehle akzeptieren dieselben Optionen.

Service: `kulturbytes-social/mastodon`, Benutzername: `access-token`.
`MASTODON_BASE_URL` wird ebenfalls zentral aus `.env` vor der Umgebung gelesen.

Keyring ist optional. Auf Ubuntu können `sudo apt install gnome-keyring libsecret-tools`
und eine entsperrte Secret-Service-Sitzung benötigt werden. Die Python-Abhängigkeit
`keyring` wird über `uv sync --all-packages` installiert; die Anwendung ruft kein
`secret-tool` auf und verwendet keine Klartext-Dateiablage. Backend-Fehler werden
als bereinigte Click-Fehler angezeigt. Umgebungsvariablen funktionieren auch bei
kaputtem Keyring. Server können extern bereitgestellte Systemd-Credentials bevorzugen;
eine automatische Provisionierung ist nicht enthalten. Details und unterstützte
OS-Backends: [Projektübersicht](../README.md#tokens-optional-im-os-keyring-speichern).

## Zugang ohne Veröffentlichung prüfen

Im Repository-Hauptordner, nach dem Setzen der Zugangsdaten:

```bash
uv run kulturbytes-social mastodon --check-auth
```

Beispiel einer erfolgreichen Prüfung (Exitcode 0):

```text
✓ Mastodon Token gültig
✓ Konto: @kulturbytes@norden.social
```

Bei Fehlern endet der Check mit Exitcode 1, zum Beispiel `Error: Mastodon-Zugangsdaten ungültig oder abgelaufen.`
API-Fehler können zusätzlich HTTP-Status und bereinigte Details enthalten.
Tokens werden niemals angezeigt, auch wenn die API sie zurückgibt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und Auswahloptionen.
Es werden keine Kulturbytes-Termine geladen, keine Bilder oder Mediencontainer
erzeugt und keine Beiträge oder Datenbankeinträge geschrieben. Der Check verwendet
nur `GET /api/v1/accounts/verify_credentials`. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff,
aber nicht sämtliche Veröffentlichungsrechte. Siehe [Mastodon-Kontoprüfung](https://docs.joinmastodon.org/methods/accounts/#verify_credentials).

`MASTODON_BASE_URL` muss eine HTTP(S)-Instanzadresse ohne eingebettete
Zugangsdaten, Pfad, Query oder Fragment sein. Fehlende Zugangsdaten beenden
`--publish` vor der Event-Abfrage.

## Termine auswählen und veröffentlichen

Starte mit einer kleinen Auswahl:

```bash
uv run kulturbytes-social mastodon --publish --limit 10 --city Flensburg
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

Der einzige öffentliche CLI-Befehl ist `kulturbytes-social` mit dem Unterbefehl `mastodon`. `DRY_RUN` und `MAX_POSTS_PER_RUN` werden nicht
als Umgebungsvariablen ausgewertet.

## Einzelnen Termin direkt auswählen

Im Repository-Hauptordner kannst du die nummerierte Auswahl überspringen:

```bash
uv run kulturbytes-social mastodon --publish --event-uuid "EVENT_UUID" --date-identifier "202609101830"
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

Der Publisher erstellt öffentliche Mastodon-Beiträge. Er bereinigt Markdown
und berücksichtigt das Zeichenlimit der Zielinstanz. Je nach verfügbaren Daten
enthält der Beitrag Veranstaltungsinformationen, einen Kulturbytes-Link und
Hashtags. Ein vorhandenes Veranstaltungsbild wird mit Alt-Text hochgeladen.
Ohne hinterlegtes Bild entsteht ein Textbeitrag.

Das Limit wird beim ersten gültigen ausgewählten Termin über die öffentliche
`GET /api/v2/instance`-Abfrage aus `configuration.statuses.max_characters` gelesen
und im gesamten Lauf wiederverwendet, auch im Dry-Run ohne Token. Fehlt ein gültiger
positiver Ganzzahlwert oder scheitert die Abfrage, verwendet das Programm mit einem
Hinweis 500 Zeichen. `--check-auth` führt diese Abfrage nicht aus. Siehe die
[Mastodon-Instanzdokumentation](https://docs.joinmastodon.org/entities/Instance/).

Titel, Datum/Zeit, Ort, Kulturbytes-Link und sämtliche erzeugten Hashtags bleiben
vollständig. Die Beschreibung wird zuerst an Wortgrenzen gekürzt oder weggelassen.
Optionale Metadaten werden nur ganz übernommen, in dieser Priorität: Untertitel,
Preis, Ticket-Link, Veranstalter; die Beschreibung erhält den verbleibenden Platz.
Ein Ticket-Link wird niemals teilweise übernommen. Passen bereits die Pflichtangaben
nicht, wird der Termin vor Bild-Upload und Veröffentlichung mit einer Fehlermeldung
abgebrochen; der bestehende Datenbankeintrag bleibt unverändert.

Die Vorschau zeigt `Zeichen: verwendete/erlaubte`, etwa `Zeichen: 611/750`.
Exakt dieser Vorschautext wird veröffentlicht. Gezählt wird mit Python `len()`;
eine besondere URL- oder Graphemzählung der Instanz wird nicht nachgebildet.
Die Sichtbarkeit bleibt fest auf öffentlich eingestellt.

## Lokale Daten

Der Publisher verwendet im Checkout fest `mastodon/mastodon_posts.sqlite3`,
unabhängig vom Arbeitsverzeichnis. Bei einer Installation außerhalb eines Checkouts
liegt die Datei unter `$XDG_DATA_HOME/kulturbytes-social/` (Fallback:
`~/.local/share/kulturbytes-social/`). Ein Vorschau-Lauf darf die Datei anlegen. Erst nach einer
erfolgreichen Veröffentlichung speichert er die Termin-ID (`date_uuid`),
Veranstaltungsdaten und die Mastodon-Status-ID und gegebenenfalls die Status-URL.
So erkennt er beim nächsten Lauf bereits veröffentlichte Termine.

Behalte diese Datenbank bei einem Umzug oder Update. Mit `MASTODON_DATABASE_PATH` kannst
du einen anderen Pfad festlegen. Relative Werte beziehen sich auf das Verzeichnis
der Standarddatenbank, absolute Werte werden unverändert verwendet. Facebook und Mastodon benötigen
jeweils eine eigene Datenbank.

`--include-published` erlaubt nach zusätzlichen Bestätigungen auch eine erneute
Veröffentlichung eines bekannten Termins. Nach erfolgreicher Veröffentlichung
ersetzt der neue Eintrag die gespeicherte Mastodon-Status-ID und die Status-URL
für dieselbe `date_uuid` und aktualisiert Veranstaltungsdaten und `published_at`.
`published_events` speichert die letzte Veröffentlichung; das Journal bewahrt alle Versuche. Schlägt die Veröffentlichung
auf der Plattform fehl, bleibt der bisherige Datenbankeintrag unverändert.

## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Eine Zugangsdaten-Variable fehlt | Prüfe `.env`, Prozessumgebung und Keyring gemäß „Konfiguration“. |
| Es stehen keine Termine zur Auswahl | Prüfe den Stadtfilter. Bereits veröffentlichte Termine siehst du mit `--include-published`; vergangene oder nicht freigegebene Termine werden ausgefiltert. |
| Mastodon lehnt die Veröffentlichung ab | Prüfe die ausgegebene API-Antwort und ob der Access Token zur eingestellten Instanz gehört und Beiträge veröffentlichen darf. |
| Der Bild-Upload schlägt fehl | Prüfe die Bildadresse aus der Vorschau und ob der Token Medien hochladen darf. |
| Die Datenbank lässt sich nicht öffnen | Prüfe, ob der übergeordnete Ordner von `MASTODON_DATABASE_PATH` existiert und beschreibbar ist. |

Die verfügbaren Optionen zeigt `uv run kulturbytes-social mastodon --help` auch ohne Zugangsdaten.

## Entwicklung

Der Plattformcode liegt in [`src/kulturbytes_mastodon/cli.py`](src/kulturbytes_mastodon/cli.py).
Gemeinsame API-Abfragen, Terminauswahl und Bilddownloads liegen in
[`common/`](../common/). Hinweise zur Struktur und zum Testlauf findest du in
der [Projektübersicht](../README.md#entwicklung).

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
Bildabrufe verwenden die gemeinsame HTTPS-/DNS-/Redirect-Prüfung. Sichere GETs
haben höchstens drei Versuche mit begrenzter Pause; veröffentlichende POSTs werden
nie automatisch wiederholt. Die DNS-Prüfung ist keine Bindung der tatsächlichen
Verbindung an eine bestimmte IP. Größenlimits bleiben in Issue #6 offen.

Jeder bestätigte Publish-Versuch reserviert den Termin vor dem Remote-Aufruf.
Remote-Erfolg wird vor der abschließenden lokalen Speicherung journalisiert.
Unklare oder teilweise abgeschlossene Versuche blockieren auch `--include-published`
bis zur manuellen Auflösung. Dry-Runs und abgelehnte Bestätigungen reservieren nichts.
Die [Projektanleitung](../README.md#veröffentlichungsjournal-und-wiederherstellung)
beschreibt `kulturbytes-social attempts list` und `attempts resolve`, einschließlich
der nötigen Prüfung nach einem Prozessabsturz. Dafür sind keine Tokens erforderlich.
