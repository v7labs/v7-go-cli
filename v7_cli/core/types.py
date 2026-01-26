"""
Core types derived from the V7 Go OpenAPI specification.

These dataclasses provide type safety and IDE support for API responses.
"""

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

# =============================================================================
# Pagination
# =============================================================================


T = TypeVar("T")


@dataclass
class PaginatedResponse(Generic[T]):
    """Paginated API response."""

    data: list[T]
    total_count: int
    offset: int = 0
    limit: int = 50

    @property
    def has_more(self) -> bool:
        """Check if there are more results."""
        return self.offset + len(self.data) < self.total_count


@dataclass
class Metadata:
    """Response metadata."""

    total_count: int = 0
    offset: int = 0
    limit: int = 50


# =============================================================================
# Project Types
# =============================================================================


@dataclass
class Project:
    """A V7 Go project (agent)."""

    id: str
    name: str
    type: str = "regular"
    description: str | None = None
    icon: str | None = None
    icon_color: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    folder_id: str | None = None
    main_view_id: str | None = None
    auto_recalculations: bool = True
    parent_property: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        """Create from API response dict."""
        return cls(
            id=data["id"],
            name=data.get("name") or "",
            type=data.get("type") or "regular",
            description=data.get("description"),
            icon=data.get("icon"),
            icon_color=data.get("icon_color"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            folder_id=data.get("folder_id"),
            main_view_id=data.get("main_view_id"),
            auto_recalculations=data.get("auto_recalculations", True),
            parent_property=data.get("parent_property") or data.get("parentProperty"),
        )


# =============================================================================
# Property Types
# =============================================================================


@dataclass
class Property:
    """A project property (column)."""

    id: str
    slug: str
    name: str
    type: str
    tool: str = "manual"
    description: str | None = None
    tool_config: dict[str, Any] | None = None
    property_config: dict[str, Any] | None = None
    position: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Property":
        """Create from API response dict."""
        return cls(
            id=data["id"],
            slug=data["slug"],
            name=data["name"],
            type=data["type"],
            tool=data.get("tool", "manual"),
            description=data.get("description"),
            tool_config=data.get("tool_config"),
            property_config=data.get("property_config"),
            position=data.get("position", 0),
        )


# =============================================================================
# Entity Types
# =============================================================================


@dataclass
class FieldValue:
    """A field value on an entity."""

    property_id: str
    slug: str
    manual_value: Any = None
    tool_value: Any = None
    status: str | None = None
    error: str | None = None
    updated_by: str | None = None

    @property
    def value(self) -> Any:
        """Get the effective value (tool_value if present, else manual_value)."""
        if self.tool_value is not None:
            return self.tool_value
        return self.manual_value

    @classmethod
    def from_dict(cls, slug: str, data: dict[str, Any]) -> "FieldValue":
        """Create from API response dict."""
        return cls(
            property_id=data.get("property_id", ""),
            slug=slug,
            manual_value=data.get("manual_value"),
            tool_value=data.get("tool_value"),
            status=data.get("status"),
            error=data.get("error"),
            updated_by=data.get("updated_by"),
        )


@dataclass
class Entity:
    """An entity (row) in a project."""

    id: str
    project_id: str
    name: str | None = None
    parent_entity_id: str | None = None
    field_values: dict[str, FieldValue] = field(default_factory=dict)
    active_view_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entity":
        """Create from API response dict."""
        field_values = {}

        # Handle both 'fields' (list endpoint) and 'field_values' (get endpoint)
        raw_fields = data.get("fields") or data.get("field_values") or {}
        for slug, fv_data in raw_fields.items():
            field_values[slug] = FieldValue.from_dict(slug, fv_data)

        return cls(
            id=data["id"],
            project_id=data.get("project_id", ""),
            name=data.get("name"),
            parent_entity_id=data.get("parent_entity_id"),
            field_values=field_values,
            active_view_ids=data.get("active_view_ids", []),
        )


# =============================================================================
# Agent Builder Types
# =============================================================================


@dataclass
class AgentBuilderStep:
    """A step in the agent builder plan."""

    property_id: str
    title: str
    description: str
    dependencies: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentBuilderStep":
        """Create from API response dict."""
        return cls(
            property_id=data.get("property_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            dependencies=data.get("dependencies", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API request."""
        return {
            "property_id": self.property_id,
            "title": self.title,
            "description": self.description,
            "dependencies": self.dependencies,
        }


@dataclass
class AgentBuilderSession:
    """An agent builder session."""

    id: str
    request_id: str
    status: str
    project_id: str | None = None
    case_id: str | None = None
    structured_plan: list[AgentBuilderStep] = field(default_factory=list)
    created_property_ids: list[str] = field(default_factory=list)
    error_message: str | None = None
    inserted_at: str | None = None
    updated_at: str | None = None

    @property
    def is_complete(self) -> bool:
        """Check if the session is complete."""
        return self.status in ("completed", "error")

    @property
    def is_awaiting_confirmation(self) -> bool:
        """Check if waiting for user confirmation."""
        return self.status == "awaiting_confirmation"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentBuilderSession":
        """Create from API response dict."""
        steps = []
        for step_data in data.get("structured_plan") or []:
            steps.append(AgentBuilderStep.from_dict(step_data))

        return cls(
            id=data.get("id", data.get("request_id", "")),
            request_id=data.get("request_id", data.get("id", "")),
            status=data.get("status", ""),
            project_id=data.get("project_id"),
            case_id=data.get("case_id"),
            structured_plan=steps,
            created_property_ids=data.get("created_property_ids", []),
            error_message=data.get("error_message"),
            inserted_at=data.get("inserted_at"),
            updated_at=data.get("updated_at"),
        )


# =============================================================================
# Agent Fixer Types
# =============================================================================


@dataclass
class AgentFixerSession:
    """An agent fixer session."""

    request_id: str
    status: str
    project_id: str | None = None
    error_message: str | None = None

    @property
    def is_complete(self) -> bool:
        """Check if the session is complete."""
        return self.status in ("completed", "error")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentFixerSession":
        """Create from API response dict."""
        return cls(
            request_id=data.get("request_id", ""),
            status=data.get("status", ""),
            project_id=data.get("project_id"),
            error_message=data.get("error_message"),
        )


# =============================================================================
# Export Types
# =============================================================================


@dataclass
class Export:
    """An export job."""

    id: str
    status: str
    format: str
    download_url: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    completed_at: str | None = None

    @property
    def is_complete(self) -> bool:
        """Check if the export is complete."""
        return self.status in ("completed", "error")

    @property
    def is_ready(self) -> bool:
        """Check if the export is ready for download."""
        return self.status == "completed" and self.download_url is not None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Export":
        """Create from API response dict."""
        return cls(
            id=data["id"],
            status=data.get("status", ""),
            format=data.get("format", ""),
            # API returns 'url' but we normalize to 'download_url'
            download_url=data.get("download_url") or data.get("url"),
            error_message=data.get("error_message"),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
        )


# =============================================================================
# Invitation Types
# =============================================================================


@dataclass
class Invitation:
    """A workspace or project invitation."""

    id: str
    email: str
    role: str
    status: str = "pending"
    expires_at: str | None = None
    created_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Invitation":
        """Create from API response dict."""
        return cls(
            id=data["id"],
            email=data.get("email", ""),
            role=data.get("role", "member"),
            status=data.get("status", "pending"),
            expires_at=data.get("expires_at"),
            created_at=data.get("created_at"),
        )


# =============================================================================
# Template Types
# =============================================================================


@dataclass
class Template:
    """A project template for import/export."""

    projects: list[dict[str, Any]] = field(default_factory=list)
    external_objects: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Template":
        """Create from API response dict."""
        return cls(
            projects=data.get("projects", []),
            external_objects=data.get("external_objects", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API request."""
        return {
            "projects": self.projects,
            "external_objects": self.external_objects,
        }


# =============================================================================
# Hub Types
# =============================================================================


@dataclass
class HubFile:
    """A file in a hub."""

    id: str
    name: str
    storage_key: str | None = None
    content_type: str | None = None
    size: int | None = None
    created_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HubFile":
        """Create from API response dict."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            storage_key=data.get("storage_key"),
            content_type=data.get("content_type"),
            size=data.get("size"),
            created_at=data.get("created_at"),
        )


@dataclass
class Hub:
    """A knowledge hub."""

    id: str
    name: str
    description: str | None = None
    status: str = "ready"
    file_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hub":
        """Create from API response dict."""
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description"),
            status=data.get("status", "ready"),
            file_count=data.get("file_count", 0),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
