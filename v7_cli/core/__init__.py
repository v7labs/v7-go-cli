"""
Core layer - Raw types and HTTP client.

This layer provides:
- Typed dataclasses matching the OpenAPI spec
- Low-level HTTP client with auth and error handling
"""

from v7_cli.core.client import APIClient, APIError, CLIError, ValidationError
from v7_cli.core.types import (
    AgentBuilderSession,
    AgentFixerSession,
    Entity,
    Export,
    FieldValue,
    Hub,
    HubFile,
    Invitation,
    PaginatedResponse,
    Project,
    Property,
)

__all__ = [
    "APIClient",
    "APIError",
    "AgentBuilderSession",
    "AgentFixerSession",
    "CLIError",
    "Entity",
    "Export",
    "FieldValue",
    "Hub",
    "HubFile",
    "Invitation",
    "PaginatedResponse",
    "Project",
    "Property",
    "ValidationError",
]
