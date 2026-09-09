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


@sources_command.command("show")
@click.argument("source")
def show_source(source: str) -> None:
    """Sichere lokale Metadaten ohne Header-, Query- oder Credential-Werte."""
    from urllib.parse import urlsplit

    adapter = load_source(source)
    definition = adapter.definition
    renderer = TemplateRenderer()
    renderer.validate(adapter.name)
    click.echo(f"name: {definition.name}\nadapter: {definition.adapter}")
    url = urlsplit(definition.listing.url)
    click.echo(f"list host/path: {url.hostname}{url.path}")
    click.echo(f"mode: {definition.listing.mode}")
    click.echo(f"detail: {'yes' if definition.detail else 'no'}")
    if definition.detail:
        url = urlsplit(definition.detail.url)
        click.echo(f"detail host/path: {url.hostname}{url.path}")
        click.echo(
            "placeholders: " + ", ".join(definition.detail.placeholders or {"id": None})
        )
        click.echo(f"identity checks: {len(definition.detail.identity_checks)}")
    click.echo("identity: " + (", ".join(definition.identity) or "source:id (default)"))
    click.echo("legacy selectors: " + ", ".join(definition.selectors))
    click.echo("fields: " + ", ".join(sorted(definition.fields)))
    click.echo(
        "media allowed_hosts: " + ", ".join(sorted(definition.media.allowed_hosts))
    )
    click.echo(f"skip_past: {definition.behavior.skip_past}")
    for platform in ("facebook", "instagram", "mastodon"):
        override = any(
            (root / definition.name / f"{platform}.j2").is_file()
            for root in renderer.roots
        )
        click.echo(f"{platform} template override: {'yes' if override else 'no'}")
