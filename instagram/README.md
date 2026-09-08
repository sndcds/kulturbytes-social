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

## Zugangsdaten und Veröffentlichung

Du benötigst ein Instagram-Professional-Konto (Business oder Creator), eine passend
konfigurierte Meta-App und einen gültigen Token mit Veröffentlichungsrechten.
Das Programm übernimmt bestehende Zugangsdaten; es implementiert keinen OAuth-Login
und keine automatische Token-Erneuerung.

Standardmäßig wird **Instagram Login** verwendet. Dieser Zugang benötigt keine
verknüpfte Facebook-Seite. Nutze die Instagram-Konto-ID und den Instagram User Access
Token aus diesem Login mit `instagram_business_basic` und
`instagram_business_content_publish`. Für fremde Konten können App Review und
Advanced Access erforderlich sein. Die genauen Voraussetzungen beschreibt
[Metas Instagram-API-Dokumentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-ab559ffb-8e2c-4b0a-b43a-5737b6d2f672).

```bash
export INSTAGRAM_USER_ID="DEINE_NUMERISCHE_INSTAGRAM_KONTO_ID"
export INSTAGRAM_ACCESS_TOKEN="DEIN_INSTAGRAM_ACCESS_TOKEN"
export INSTAGRAM_LOGIN_TYPE="instagram"
uv run kulturbytes-social instagram --publish --event-uuid "EVENT_UUID" --date-identifier "202609101830"
```

Vor jedem Beitrag erscheint eine Bestätigungsfrage. Ohne Zustimmung entstehen
weder Mediencontainer noch Instagram-Beitrag. Ohne `--publish` bleibt es beim Dry-Run.

Alternativ unterstützt `INSTAGRAM_LOGIN_TYPE=facebook` die **Instagram API mit
Facebook Login** über `graph.facebook.com`. Dafür muss das Professional-Konto mit
einer Facebook-Seite verknüpft sein. `INSTAGRAM_USER_ID` ist die ID des zugehörigen
Instagram-Kontos, nicht die Facebook-Seiten-ID. Verwende einen für diesen Zugang
gültigen Token mit `instagram_basic` und `instagram_content_publish`; für die
Seitenermittlung bzw. den Zugriff werden auch `pages_show_list` und
`pages_read_engagement` benötigt. Ein vorhandener Facebook-Publishing-Token besitzt
diese Instagram-Rechte nicht automatisch. Siehe
[Metas Facebook-Login-Anleitung](https://www.postman.com/meta/instagram/folder/u4g5a2a/instagram-api-with-facebook-login).

| Variable | Bedeutung | Standard |
|---|---|---|
| `INSTAGRAM_USER_ID` | Numerische Instagram-Konto-ID des gewählten Login-Verfahrens | erforderlich für `--publish` und `--check-auth` |
| `INSTAGRAM_ACCESS_TOKEN` | Passender Access Token | erforderlich für `--publish` und `--check-auth` |
| `INSTAGRAM_LOGIN_TYPE` | `instagram` oder `facebook` | `instagram` |
| `INSTAGRAM_GRAPH_API_VERSION` | Graph-API-Version für deine App | `v26.0` |
| `DATABASE_PATH` | Eigene SQLite-Datenbank | `instagram_posts.sqlite3` |

`v26.0` ist der konfigurierbare Projektstandard, keine automatische Ermittlung
der neuesten API-Version. `.env`-Dateien werden nicht automatisch geladen.
Tokens gehören nicht in versionierte Dateien oder geteilte Terminal-Ausgaben.

## Optionaler OS-Keyring

Tokens werden zuerst aus der jeweiligen Umgebungsvariable, sonst aus dem
OS-Keyring geladen. Eine vorhandene, aber leere Variable verhindert ebenfalls
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
Löschen verlangt eine Bestätigung und betrifft nur den Keyring, nicht die Umgebung.
Die Verwaltung führt keine Netzwerk- oder Datenbankoperationen aus. Kombinationen
mit `--publish` oder `--check-auth` sind nicht zulässig; Auswahloptionen werden ignoriert.
Die Paketbefehle akzeptieren dieselben Optionen.

Service: `kulturbytes-social/instagram`, Benutzername: `access-token`.
Instanz-/Kontokonfiguration wird weiterhin über Umgebungsvariablen gesetzt.

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
`--publish` prüft die erforderliche Konfiguration vor der Event-Abfrage.

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
damit bereits veröffentlichte Termine weiter erkannt werden. `DATABASE_PATH` mit
einem absoluten Pfad verwendet deine bestehende Datei; relative Werte beziehen
sich auf das Standarddatenbankverzeichnis, nicht auf das Arbeitsverzeichnis.

Bei einer ausdrücklich bestätigten Wiederveröffentlichung ersetzt der neue
Instagram-Eintrag den bisherigen Datenbankeintrag; eine Historie wird nicht geführt.
Scheitert die abschließende Anfrage durch einen Verbindungsabbruch, kann der Beitrag
remote trotzdem entstanden sein. Vor einem erneuten Versuch prüfe das Konto.
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
