# Kulturbytes Facebook Publisher

Teile Kulturbytes-Veranstaltungen auf deiner Facebook-Seite: Du wählst Termine
im Terminal aus, prüfst die Vorschau und bestätigst die Veröffentlichung.
Beim normalen Start bleibt es bei einer Vorschau.

[Projektübersicht](../README.md) · [Facebook](../facebook/README.md) · [Mastodon](../mastodon/README.md)

## Voraussetzungen

Du brauchst Python 3.12 oder neuer, `uv` und eine Internetverbindung.
Zum Veröffentlichen benötigst du zusätzlich
eine Facebook-Seiten-ID und einen Page Access Token, der Beiträge auf dieser Seite veröffentlichen darf.
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

## Konfiguration

Die Einstellungen werden aus den Umgebungsvariablen gelesen:

| Variable | Bedeutung | Standard |
|---|---|---|
| `FACEBOOK_PAGE_ID` | ID der Zielseite | für `--publish` und `--check-auth` erforderlich |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Page Access Token für die Zielseite | alternativ aus Keyring oder User Token ableitbar |
| `FACEBOOK_GRAPH_API_VERSION` | Verwendete Graph-API-Version | `v26.0` |
| `DATABASE_PATH` | Pfad zur lokalen Datenbank | `facebook_posts.sqlite3` |

Zugangsdaten werden erst für `--publish` und `--check-auth` geladen.
`--dry-run`, `--help` und Modulimporte funktionieren ohne Zugangsdaten.
Die Vorschau lädt Veranstaltungsdaten aus der Kulturbytes-API.

Setze die Zugangsdaten vor dem Zugangstest oder einer Veröffentlichung:

```bash
export FACEBOOK_PAGE_ID="DEINE_NUMERISCHE_SEITEN_ID"
export FACEBOOK_PAGE_ACCESS_TOKEN="DEIN_PAGE_ACCESS_TOKEN"
```

Die `export`-Befehle gelten für die aktuelle Terminal-Sitzung. Eine `.env`-Datei
wird vom Programm nicht automatisch geladen. Bewahre echte Tokens außerhalb
der versionierten Dateien auf; `.env` und lokale Datenbanken sind bereits in
[`.gitignore`](../.gitignore) ausgeschlossen.

## Optionaler OS-Keyring

Tokens werden zuerst aus der jeweiligen Umgebungsvariable, sonst aus dem
OS-Keyring geladen. Eine vorhandene, aber leere Variable verhindert ebenfalls
den Keyring-Zugriff und zählt als fehlend. Hilfe und Dry-Run lesen keine Tokens.
`--publish` und `--check-auth` verwenden beide dieselbe Auflösung.

Im Repository-Hauptordner:

```bash
uv run kulturbytes-social facebook --credentials status
uv run kulturbytes-social facebook --credentials set --credential page
uv run kulturbytes-social facebook --credentials delete --credential page
```

Beim Speichern wird der Token verdeckt abgefragt. Status zeigt ausschließlich
vorhanden/nicht vorhanden; weder Werte, Teile, Längen noch Hashes werden ausgegeben.
Löschen verlangt eine Bestätigung und betrifft nur den Keyring, nicht die Umgebung.
Die Verwaltung führt keine Netzwerk- oder Datenbankoperationen aus. Kombinationen
mit `--publish`, `--check-auth` oder `--resolve-page-token` sind nicht zulässig; Auswahloptionen werden ignoriert.
Die Paketbefehle akzeptieren dieselben Optionen.

`--credential user` verwaltet den User Access Token; ohne Auswahl fragt `set`/`delete`
nach `page` oder `user`. Service: `kulturbytes-social/facebook`; Benutzernamen:
`page-access-token` und `user-access-token`. Umgebungsvariablen:
`FACEBOOK_PAGE_ACCESS_TOKEN` und `FACEBOOK_USER_ACCESS_TOKEN`. Veröffentlichen
verwendet einen validierten Page Token, der bei Bedarf aus dem User Token abgeleitet wird. `FACEBOOK_PAGE_ID` bleibt eine Umgebungsvariable.

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
uv run kulturbytes-social facebook --check-auth
```

Beispiel einer erfolgreichen Prüfung (Exitcode 0):

```text
✓ Facebook Token gültig
✓ Seite erreichbar: Kulturbytes (1173614782497494)
```

Bei Fehlern endet der Check mit Exitcode 1, zum Beispiel `Error: Facebook Access Token ist abgelaufen.`
API-Fehler können zusätzlich HTTP-Status und bereinigte Details enthalten.
Tokens werden niemals angezeigt, auch wenn die API sie zurückgibt.

`--check-auth` hat Vorrang vor `--publish`, `--dry-run` und Auswahloptionen.
Es werden keine Kulturbytes-Termine geladen, keine Bilder oder Mediencontainer
erzeugt und keine Beiträge oder Datenbankeinträge geschrieben. Der Check verwendet
`GET /{version}/{page_id}?fields=id,name` und bei Wiederherstellung zusätzlich `/me/accounts`. Ein erfolgreicher Lesezugriff bestätigt den Kontozugriff,
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

Behalte diese Datenbank bei einem Umzug oder Update. Mit `DATABASE_PATH` kannst
du einen anderen Pfad festlegen. Relative Werte beziehen sich auf das Verzeichnis
der Standarddatenbank, absolute Werte werden unverändert verwendet. Facebook und Mastodon benötigen
jeweils eine eigene Datenbank.

`--include-published` erlaubt nach zusätzlichen Bestätigungen auch eine erneute
Veröffentlichung eines bekannten Termins. Nach erfolgreicher Veröffentlichung
ersetzt der neue Eintrag die gespeicherte Facebook-Post-ID
für dieselbe `date_uuid` und aktualisiert Veranstaltungsdaten und `published_at`.
Es wird nur die letzte Veröffentlichung gespeichert. Schlägt die Veröffentlichung
auf der Plattform fehl, bleibt der bisherige Datenbankeintrag unverändert.

## Hilfe bei Problemen

| Problem | Was du prüfen kannst |
|---|---|
| `uv` wird nicht gefunden | Prüfe, ob `uv` installiert und im Suchpfad deines Terminals verfügbar ist. |
| Eine Zugangsdaten-Variable fehlt | Setze die erforderlichen Variablen unter „Konfiguration“ im selben Terminal. |
| Es stehen keine Termine zur Auswahl | Prüfe den Stadtfilter. Bereits veröffentlichte Termine siehst du mit `--include-published`; vergangene oder nicht freigegebene Termine werden ausgefiltert. |
| Facebook lehnt die Veröffentlichung ab | Prüfe die ausgegebene API-Antwort, die Seiten-ID sowie Gültigkeit und Veröffentlichungsrechte des Page Access Tokens. |
| Ein Fotobeitrag schlägt fehl | Prüfe die Bildadresse aus der Vorschau und die API-Fehlermeldung. Bei einem fehlerhaften Bild erfolgt kein automatischer Wechsel zum Textbeitrag. |
| Die Datenbank lässt sich nicht öffnen | Prüfe, ob der übergeordnete Ordner von `DATABASE_PATH` existiert und beschreibbar ist. |

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

## Page Token wiederherstellen

```bash
uv run kulturbytes-social facebook --resolve-page-token
```

Ein User Access Token gehört einem Facebook-Nutzer und erlaubt die Abfrage seiner
verwalteten Seiten. Der daraus abgeleitete Page Access Token gehört der konfigurierten
Seite und wird zum Veröffentlichen verwendet. `FACEBOOK_PAGE_ID` bleibt erforderlich.

`--check-auth` und `--publish` prüfen zuerst den Page Token aus der Environment-Variable,
sonst aus dem OS-Keyring. Fehlt er oder meldet Meta Code 190 (einschließlich Ablaufcode
463), folgt der User Token aus `FACEBOOK_USER_ACCESS_TOKEN`, sonst aus dem Keyring.
Eine gesetzte, auch leere Environment-Variable unterdrückt den jeweiligen Keyring-Wert.
Ein nicht verfügbarer optionaler Keyring verhindert die Wiederherstellung aus Environment
oder interaktiver Eingabe nicht. Berechtigungsfehler (10/200), Netzwerkfehler und
ungültige Validierungsantworten brechen ab.

Im TTY wird die Wiederherstellung zunächst bestätigt (Standard: Nein). Fehlt ein User
Token, folgt eine verdeckte Eingabe. Ohne TTY gibt es keine Rückfragen; ohne vorhandenen
User Token endet der Befehl mit einem Fehler. `--resolve-page-token` fordert die Ableitung
gezielt an und überspringt die anfängliche Page-Token-Prüfung und Wiederherstellungsfrage.
Wie `--check-auth` hat diese Option Vorrang vor Veröffentlichung und Eventauswahl.

Die Abfrage `GET /{version}/me/accounts?fields=id,name,access_token` wählt ausschließlich
die konfigurierte Seiten-ID, auch auf Folgeseiten. Folgeseiten werden über geprüfte Cursor
am festen Graph-Endpunkt abgefragt; fremde URLs werden nicht aufgerufen. Der neue Token
muss anschließend `GET /{version}/{page_id}?fields=id,name` erfolgreich bestehen.
Erst danach kann im TTY das Speichern im bestehenden OS-Keyring bestätigt werden
(Standard: Ja). Eine fehlgeschlagene Wiederherstellung verändert keine gespeicherten Tokens.
Environment-Variablen werden nicht verändert; ein dort abgelaufener Token bleibt beim
nächsten Aufruf vorrangig, bis die Umgebung angepasst wird. Der aktuelle Aufruf verwendet
den neuen Token direkt im Speicher.

Vor `--publish` erfolgt diese Prüfung vor Event-, Bild- und Datenbankzugriffen.
Die Bestätigung jedes Beitrags bleibt erforderlich. Dry Runs benötigen keine Tokens.
Tokens werden niemals ausgegeben oder in SQLite, `.env` oder Dateien gespeichert;
Auth-Fehler zeigen HTTP-Status und gegebenenfalls Meta-Code statt roher Antwortkörper.
Dies ist kein OAuth-Browserlogin und keine Erneuerung eines User Tokens.
