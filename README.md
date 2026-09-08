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

Alle Publisher lesen ihre Einstellungen aus Umgebungsvariablen; Tokens können
alternativ im OS-Keyring liegen. Die
plattformabhängigen Variablen und ihre Standardwerte stehen in den Anleitungen:

- [Facebook konfigurieren](facebook/README.md#konfiguration)
- [Mastodon konfigurieren](mastodon/README.md#konfiguration)
- [Instagram konfigurieren](instagram/README.md#zugangsdaten-und-veröffentlichung)

Alle drei Publisher benötigen Zugangsdaten nur für `--publish` und `--check-auth`.
Import, Vorschau (`--dry-run`) und Befehlshilfe (`--help`) funktionieren ohne Tokens. `.env`-Dateien werden nicht automatisch geladen.
Echte Tokens gehören außerhalb der versionierten Dateien aufbewahrt.

## Tokens optional im OS-Keyring speichern

Umgebungsvariablen haben Vorrang vor dem OS-Keyring. Ist eine Tokenvariable gesetzt,
wird der Keyring für diesen Token nicht angesprochen, auch bei leerem Wert.
Ein leerer Wert zählt als fehlender Token; entferne die Variable mit `unset`,
wenn der gespeicherte Token verwendet werden soll. Hilfe und Dry-Run benötigen
weder Tokens noch einen funktionierenden Keyring.

Im Repository-Hauptordner, hier am Beispiel Facebook:

```bash
uv run kulturbytes-social facebook --credentials status
uv run kulturbytes-social facebook --credentials set
uv run kulturbytes-social facebook --credentials delete
```

`status` zeigt nur vorhanden/nicht vorhanden nach derselben Quellenpriorität wie
`--publish` und `--check-auth`. `set` fragt den Token verdeckt ab und speichert ihn
im OS-Keyring; `delete` löscht nur den Keyring-Eintrag nach Bestätigung. Gesetzte
Umgebungsvariablen werden weder verändert noch gelöscht. Bei Facebook wählst du
`page` oder `user`, alternativ mit `--credential page` bzw. `--credential user`.
Es gibt keine Option zur Übergabe des Tokenwerts auf der Kommandozeile.

Die Verwaltung startet keine Event-Abfrage, Veröffentlichung oder Datenbankoperation.
Auswahloptionen werden dabei ignoriert; Kombinationen mit `--publish` oder
`--check-auth` werden als Bedienfehler abgewiesen. Die Paketbefehle unterstützen
dieselben Optionen. Es werden weder Tokenwerte noch Präfixe, Längen oder Hashes angezeigt.

Auf Ubuntu-Desktops kann eine entsperrte Secret-Service-/GNOME-Keyring-Sitzung
verwendet werden. Optionale Systempakete:

```bash
sudo apt install gnome-keyring libsecret-tools
```

Die Python-Abhängigkeit `keyring` liegt in `kulturbytes-common` und wird mit
`uv sync --all-packages` installiert (hinzugefügt mit
`uv add --package kulturbytes-common keyring`). Die Anwendung nutzt Python
`keyring`, nicht `secret-tool`. Unterstützt werden die OS-Backends Secret Service,
KWallet, macOS Keychain und Windows Credential Locker; Datei-/Klartext-Backends
und deaktivierte Backends werden abgewiesen. Details zu den Systemdiensten:
[Python-keyring-Dokumentation](https://keyring.readthedocs.io/en/latest/).

Ist der benötigte Keyring gesperrt, nicht erreichbar oder ungeeignet, erscheint
`OS-Keyring ist nicht verfügbar` mit einem Hinweis auf Umgebungsvariablen.
Rohe Backend-Fehler werden nicht ausgegeben. Die Anwendung schreibt keine Tokens
in SQLite, `.env`, temporäre Dateien oder Shell-Startdateien.

Für CI, Container und Server bleiben Umgebungsvariablen vollständig unterstützt.
Systemd-Dienste können vorzugsweise extern provisionierte Systemd-Credentials
(`systemd-creds`) verwenden; deren Übergabe an die Token-Umgebungsvariablen muss
der Dienststart übernehmen. Diese Anwendung richtet keine Systemd-Credentials ein.
Ein Desktop-Keyring ist für den Betrieb mit Umgebungsvariablen nicht erforderlich.

| Plattform | Keyring-Service | Benutzername |
|---|---|---|
| Facebook | `kulturbytes-social/facebook` | `page-access-token`, `user-access-token` |
| Instagram | `kulturbytes-social/instagram` | `access-token` |
| Mastodon | `kulturbytes-social/mastodon` | `access-token` |

Seiten-/Konto-IDs, Instanzadresse, Login-Typ und API-Version bleiben Konfiguration
in Umgebungsvariablen. Die Namen gelten pro Plattform, nicht pro Konto; beim
Kontowechsel muss auch der gespeicherte Token passen. Facebook-User-Tokens können
zur Wiederherstellung eines fehlenden oder abgelaufenen Page Tokens verwendet werden.
`uv run kulturbytes-social facebook --resolve-page-token` leitet den Token gezielt ab
und validiert ihn, ohne Events zu laden oder Beiträge zu erstellen. `--check-auth`
und `--publish` versuchen die Wiederherstellung bei fehlenden Tokens oder Meta-Code 190.
Reihenfolge: Page Token aus Environment, sonst Keyring; danach User Token aus
Environment, sonst Keyring, sonst verdeckte Eingabe im TTY. Auch leere Environment-
Variablen unterdrücken den jeweiligen Keyring-Lookup. Im TTY wird eine Wiederherstellung
bestätigt; ohne TTY sind nur vorhandene User Tokens nutzbar. Ein validierter neuer
Page Token kann nach separater Bestätigung im OS-Keyring gespeichert werden.
Tokens werden nie ausgegeben. Dies ist kein OAuth-Browserlogin und erneuert keine
User Tokens. Details: [Facebook](facebook/README.md).

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

Jede Plattform behält ihre eigene SQLite-Datenbank und ihr bisheriges Schema.
Im Checkout sind die Standardpfade fest am Repository verankert:

- `facebook/facebook_posts.sqlite3`
- `mastodon/mastodon_posts.sqlite3`
- `instagram/instagram_posts.sqlite3`

Bestehende Dateien an diesen Orten werden weiterverwendet. Bei einer separaten
Installation außerhalb eines Checkouts liegen die Dateien unter
`$XDG_DATA_HOME/kulturbytes-social/`, standardmäßig `~/.local/share/kulturbytes-social/`.
Ein Arbeitsverzeichniswechsel ändert diese Pfade nicht. Verzeichnisse werden erst
beim Initialisieren der Datenbank angelegt, nicht bei Hilfe oder Auth-Checks.

`DATABASE_PATH` überschreibt den jeweiligen Pfad. Absolute Werte werden direkt
verwendet; relative Werte beziehen sich auf das Standarddatenbankverzeichnis der
Plattform. Niemals mehrere Plattformen auf dieselbe Datenbankdatei verweisen lassen.
Dry-Runs können die Datei anlegen, schreiben aber keine Veröffentlichung.
Erst nach bestätigtem Remote-Erfolg wird die `date_uuid` gespeichert; bestätigte
Wiederveröffentlichungen ersetzen den bisherigen Eintrag.

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
setze **vor der nächsten Veröffentlichung** `DATABASE_PATH` auf den absoluten Pfad
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

Die Tests verwenden simulierte HTTP-Antworten und temporäre Datenbanken.

## Lizenz

[AGPL-3.0](LICENSE)
