from datetime import date

import click


def format_event_list_item(
    event: dict,
) -> str:
    start_date = event.get(
        "start_date",
        "",
    )

    start_time = (
        event.get("start_time")
        or ""
    )

    title = event.get(
        "title",
        "<ohne Titel>",
    )

    venue = event.get(
        "venue_name"
    )

    city = event.get(
        "venue_city"
    )

    try:
        parsed_date = date.fromisoformat(
            start_date
        )

        formatted_date = (
            parsed_date.strftime(
                "%d.%m.%Y"
            )
        )

    except ValueError:
        formatted_date = start_date

    result = (
        f"{formatted_date}"
    )

    if start_time:
        result += (
            f" {start_time}"
        )

    result += (
        f" — {title}"
    )

    if venue:
        result += (
            f" — {venue}"
        )

    if city:
        result += (
            f" ({city})"
        )

    return result


def parse_selection(
    value: str,
    count: int,
) -> list[int]:
    value = value.strip().lower()

    if not value:
        return []

    if value in {
        "all",
        "alle",
        "*",
    }:
        return list(
            range(count)
        )

    result: set[int] = set()

    parts = value.split(",")

    for part in parts:
        part = part.strip()

        if not part:
            continue

        if "-" in part:
            try:
                start_text, end_text = (
                    part.split("-", 1)
                )

                start = int(
                    start_text
                )

                end = int(
                    end_text
                )

            except ValueError as exc:
                raise click.ClickException(
                    f"Ungültige Auswahl: {part}"
                ) from exc

            if start > end:
                raise click.ClickException(
                    f"Ungültiger Bereich: {part}"
                )

            for number in range(
                start,
                end + 1,
            ):
                if (
                    number < 1
                    or number > count
                ):
                    raise click.ClickException(
                        (
                            "Eventnummer außerhalb "
                            f"des Bereichs: {number}"
                        )
                    )

                result.add(
                    number - 1
                )

        else:
            try:
                number = int(
                    part
                )

            except ValueError as exc:
                raise click.ClickException(
                    f"Ungültige Auswahl: {part}"
                ) from exc

            if (
                number < 1
                or number > count
            ):
                raise click.ClickException(
                    (
                        "Eventnummer außerhalb "
                        f"des Bereichs: {number}"
                    )
                )

            result.add(
                number - 1
            )

    return sorted(
        result
    )


def select_events(
    events: list[dict],
) -> list[dict]:
    if not events:
        click.secho(
            "Keine unveröffentlichten zukünftigen "
            "Events gefunden.",
            fg="yellow",
        )

        return []

    click.echo()
    click.secho(
        "Verfügbare Veranstaltungen",
        bold=True,
    )
    click.echo()

    for index, event in enumerate(
        events,
        start=1,
    ):
        click.echo(
            f"[{index:>3}] "
            f"{format_event_list_item(event)}"
        )

    click.echo()
    click.echo(
        "Du kannst beispielsweise auswählen:"
    )
    click.echo(
        "  2        → nur Event 2"
    )
    click.echo(
        "  1,4,7    → Events 1, 4 und 7"
    )
    click.echo(
        "  3-6      → Events 3 bis 6"
    )
    click.echo(
        "  1,3-5,9  → Kombination"
    )
    click.echo(
        "  all      → alle angezeigten Events"
    )
    click.echo()

    selection = click.prompt(
        "Welche Events möchtest du auswählen?",
        default="",
        show_default=False,
    )

    indices = parse_selection(
        selection,
        len(events),
    )

    return [
        events[index]
        for index in indices
    ]
