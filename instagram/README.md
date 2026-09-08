# Instagram

Der Adapter unterstützt einzelne JPEG-Bilder im Feed eines professionellen Instagram-Kontos.
Die CLI spricht ausschließlich mit dem FastAPI-Backend; PostgreSQL hält das Journal und
die gemeinsame Historie. [Backend einrichten](../README.md#installation-und-start).

```bash
uv run kulturbytes-social instagram
uv run kulturbytes-social instagram --publish
uv run kulturbytes-social instagram --city Flensburg --limit 20
uv run kulturbytes-social instagram --event-uuid EVENT_UUID --date-identifier DATE_SLUG
uv run kulturbytes-social instagram --check-auth
```

Ohne `--publish` nur Vorschau. Jede Veröffentlichung benötigt Bestätigung;
`--include-published` verlangt zusätzlich die ausdrückliche Wiederholung und erhält ältere
Historienzeilen. Direkte Auswahl umgeht die nummerierte Liste, behält aber die Filter.

## Server-Konfiguration

Empfohlener gemeinsamer Meta-Zugang für Facebook Login:

```dotenv
META_SYSTEM_USER_ACCESS_TOKEN=
INSTAGRAM_USER_ID=
INSTAGRAM_LOGIN_TYPE=facebook
INSTAGRAM_GRAPH_API_VERSION=v26.0
```

Ein passender System User muss Zugriff auf das professionelle Instagram-Konto und die
zugehörige Page haben. Dieser Login verwendet `graph.facebook.com`; relevante Berechtigungen
umfassen `instagram_basic` und `instagram_content_publish`. `INSTAGRAM_USER_ID` ist die
numerische Instagram-Konto-ID des gewählten Login-Flows, nicht die Facebook-Page-ID.
Die Versionsangabe ist der Projektstandard.

Der eigenständige Instagram-Login bleibt mit `INSTAGRAM_LOGIN_TYPE=instagram` und
`INSTAGRAM_ACCESS_TOKEN` verfügbar. Er verwendet `graph.instagram.com` und einen Instagram
User Access Token mit `instagram_business_basic`/`instagram_business_content_publish`.
Ohne explizite Konfiguration ist `instagram` der Code-Standard. Ein gesetzter gemeinsamer
Meta-System-Zugang erfordert hingegen `facebook` und hat Vorrang vor dem separaten Token.

`.env > Environment > OS-Keyring` gilt serverseitig. Keine interaktiven Token-Prompts im
Backend. `--check-auth` führt ausschließlich einen lesenden Konto-Check durch und erzeugt
keine Publikationsdaten. Die Vorschau benötigt keine Instagram-Credentials.
[Meta Instagram Publishing](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-ab559ffb-8e2c-4b0a-b43a-5737b6d2f672).

## Inhalt und Publikationsablauf

Die Listen-Summary hat Vorrang vor der Detail-Description; leere/Whitespace-Summaries
fallen auf die Description zurück. Der Adapter entfernt unterstützte Markdown-Syntax.
Die Caption ist auf 2.200 Zeichen und fünf generierte Hashtags begrenzt, mit Vorrang für
`#Kulturbytes` und den Ort. Zuerst wird die Summary gekürzt. Kulturbytes-URL und Hashtags
bleiben vollständig; zu lange feste Metadaten werden abgelehnt.

Das Bild stammt aus `images.main.url` der Details. Auch die Vorschau prüft die JPEG-Signatur
über den abgesicherten Downloader. Fehlende und andere Bildformate werden abgelehnt.
Es gibt keine Konvertierung, Bildgenerierung, externes Hosting oder Text-Fallback. Meta
lädt die öffentliche URL selbst und validiert weitere Plattformvorgaben wie Dimensionen.

Nach Bestätigung erstellt `POST /{user_id}/media` einen Container (`instagram_container`).
Bis zu fünf lesende Statusprüfungen erfolgen in Abständen von 60 Sekunden. Nur `FINISHED`
erlaubt `POST /{user_id}/media_publish` (`instagram_publish`). Fehler, unerwartete Zustände,
Ablauf oder Timeout schreiben keinen Erfolg. Ein ungeklärter Versuch bleibt gesperrt.
POSTs werden nicht automatisch wiederholt; HTTP-Client und Proxy müssen ausreichend lange
Antwortzeiten für die synchrone Verarbeitung erlauben.

```bash
uv run kulturbytes-social attempts list --platform instagram --active
uv run kulturbytes-social attempts resolve ATTEMPT_UUID --platform instagram --outcome published --remote-id MEDIA_ID
```

Vor Auflösung den Publisher stoppen und das Konto manuell prüfen. Eine Container-ID ist
keine veröffentlichte Medien-ID. Bei bestätigtem Remote-Erfolg bleibt die tatsächliche
Medien-ID auch nach fehlgeschlagener lokaler Finalisierung erhalten.
[Wiederherstellung und Cutover](../README.md#datenbank-und-wiederherstellung).
