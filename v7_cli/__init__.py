"""
V7 CLI - Three-layer architecture for V7 Go API.

Layers:
- core: Raw types and HTTP client (from OpenAPI)
- sdk: High-level V7Client with nice ergonomics
- cli: Opinionated command-line interface
"""

from v7_cli.sdk import V7Client

__version__ = "0.1.0"
__all__ = ["V7Client"]
