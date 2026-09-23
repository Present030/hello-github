"""Small package used to exercise a persistent GitHub-backed workspace."""

from .version import get_version

__version__ = get_version()

__all__ = ["__version__", "get_version"]
