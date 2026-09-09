"""CLI defaults and legacy option dispatch, outside core execution."""

import click

from .loader import load_source

DEFAULT_SOURCE = "kulturbytes"


def prepare_source(
    source: str, *, legacy_selector=(None, None), item_id: str | None = None
):
    adapter = load_source(source)
    target = adapter.resolve_legacy_selector(legacy_selector)
    if target is not None and item_id is not None:
        raise click.UsageError(
            "--item-id ist nicht mit Legacy-Selektoren kombinierbar."
        )
    return adapter, target if target is not None else item_id
