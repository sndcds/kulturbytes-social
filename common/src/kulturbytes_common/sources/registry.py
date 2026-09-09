"""Bundled adapter registration, independent of a configured source's name."""

from .generic import JsonSourceAdapter
from .kulturbytes import KulturbytesSourceAdapter

ADAPTERS = {"json": JsonSourceAdapter, "kulturbytes": KulturbytesSourceAdapter}
