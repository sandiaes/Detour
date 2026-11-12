"""Detour backend API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("detour-api")
except PackageNotFoundError:  # pragma: no cover - only when run from a bare source tree
    __version__ = "0.0.0"
