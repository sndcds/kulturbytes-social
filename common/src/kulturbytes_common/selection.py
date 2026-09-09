import click


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
                            "Eintragsnummer außerhalb "
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
                        "Eintragsnummer außerhalb "
                        f"des Bereichs: {number}"
                    )
                )

            result.add(
                number - 1
            )

    return sorted(
        result
    )
