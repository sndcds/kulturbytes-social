"""Read-only local source configuration inspection, without HTTP or credentials."""

import click
from kulturbytes_common.rendering import TemplateRenderer
from kulturbytes_common.sources.loader import definitions, load_source


@click.group("sources")
def sources_command() -> None:
    """JSON-Quellen lokal auflisten und Konfiguration prüfen."""


@sources_command.command("list")
def list_sources() -> None:
    for definition in definitions().values():
        click.echo(f"{definition.name} ({definition.adapter})")


@sources_command.command("validate")
@click.argument("source")
def validate_source(source: str) -> None:
    adapter = load_source(source)
    TemplateRenderer().validate(adapter.name)
    click.echo(
        f"✓ Quelle {adapter.name}: YAML, Mapping und Templates gültig; keine HTTP-Anfrage ausgeführt."
    )
