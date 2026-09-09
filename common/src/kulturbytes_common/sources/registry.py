"""Generic adapter registration, independent of configured source names."""

from .generic import JsonSourceAdapter

ADAPTERS = {"json": JsonSourceAdapter}
