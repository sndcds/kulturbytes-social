"""Concise errors without raw source payloads, URLs or template contents."""

import click


class SourceError(click.ClickException):
    pass


class SourceNotFound(SourceError):
    pass


class SourceConfigurationError(SourceError):
    pass


class SourceMappingError(SourceError):
    pass


class SourceValidationError(SourceError):
    pass


class TemplateRenderingError(SourceError):
    pass


class SourceFetchError(SourceMappingError):
    """A request failed before mapping; retained under mapping errors for callers."""
