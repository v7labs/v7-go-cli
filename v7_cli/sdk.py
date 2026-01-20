"""
V7 SDK - High-level client with nice ergonomics.

This layer provides a clean, typed interface for common V7 Go operations.
Built on top of the core APIClient.
"""

import builtins
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from v7_cli.core.client import APIClient, APIError
from v7_cli.core.types import (
    AgentBuilderSession,
    AgentFixerSession,
    Entity,
    Export,
    Hub,
    HubFile,
    Invitation,
    PaginatedResponse,
    Project,
    Property,
    Template,
)


class V7Client:
    """
    High-level V7 Go API client with typed methods and nice ergonomics.

    Example:
        client = V7Client()

        # Create an agent
        session = client.agent.create("Extract invoice data")
        session = client.agent.wait_for_plan(session.request_id)
        session = client.agent.execute(session.request_id)

        # Get entity data
        entities = client.entities.list(project_id)
        entity = client.entities.get(project_id, entity_id)

    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        workspace_id: str | None = None,
        timeout: int = 60,
    ):
        """
        Initialize the V7 client.

        Args:
            api_key: V7 Go API key (or V7_GO_API_KEY env var)
            base_url: API base URL (or V7_GO_BASE_API_URL / V7_GO_BASE_URL env var)
            workspace_id: Default workspace ID (or V7_GO_WORKSPACE_ID env var)
            timeout: Request timeout in seconds

        """
        self._client = APIClient(
            api_key=api_key,
            base_url=base_url,
            workspace_id=workspace_id,
            timeout=timeout,
        )

        # Sub-clients for different domains
        self.agent = AgentOperations(self._client)
        self.projects = ProjectOperations(self._client)
        self.entities = EntityOperations(self._client)
        self.properties = PropertyOperations(self._client)
        self.exports = ExportOperations(self._client)
        self.invitations = InvitationOperations(self._client)
        self.templates = TemplateOperations(self._client)
        self.hubs = HubOperations(self._client)

    @property
    def workspace_id(self) -> str | None:
        """Get the current workspace ID."""
        return self._client.workspace_id

    @workspace_id.setter
    def workspace_id(self, value: str) -> None:
        """Set the workspace ID."""
        self._client.workspace_id = value


# =============================================================================
# Agent Operations (Agent Builder + Agent Fixer)
# =============================================================================


class AgentOperations:
    """Operations for creating and fixing agents."""

    def __init__(self, client: APIClient):
        self._client = client

    def create(self, prompt: str) -> AgentBuilderSession:
        """
        Create a new agent using the agent builder.

        Args:
            prompt: Description of the agent to build

        Returns:
            AgentBuilderSession with request_id and initial status

        """
        result = self._client.workspace_post("/agent_builder", {"user_prompt": prompt})
        return AgentBuilderSession.from_dict(result)

    def status(self, request_id: str) -> AgentBuilderSession:
        """
        Get the status of an agent builder session.

        Args:
            request_id: The request ID from create()

        Returns:
            AgentBuilderSession with current status and plan

        """
        result = self._client.workspace_get(f"/agent_builder/{request_id}")
        return AgentBuilderSession.from_dict(result)

    def followup(self, request_id: str, message: str) -> AgentBuilderSession:
        """
        Send a followup message to refine the agent plan.

        Args:
            request_id: The request ID from create()
            message: Refinement message

        Returns:
            Updated AgentBuilderSession

        """
        # Fetch current session to get the structured_plan
        session = self.status(request_id)
        structured_plan = [step.to_dict() for step in session.structured_plan]

        result = self._client.workspace_post(
            f"/agent_builder/{request_id}/followup",
            {"message": message, "structured_plan": structured_plan},
        )
        # Ensure request_id is present in response (API may not return it)
        if not result.get("request_id"):
            result["request_id"] = request_id
        return AgentBuilderSession.from_dict(result)

    def execute(self, request_id: str) -> AgentBuilderSession:
        """
        Execute the agent builder plan to create the agent.

        Args:
            request_id: The request ID from create()

        Returns:
            AgentBuilderSession with project_id on completion

        """
        # Fetch current session to get the structured_plan
        session = self.status(request_id)
        structured_plan = [step.to_dict() for step in session.structured_plan]

        result = self._client.workspace_post(
            f"/agent_builder/{request_id}/execute",
            {"structured_plan": structured_plan},
        )
        # Ensure request_id is present in response (API may not return it)
        if not result.get("request_id"):
            result["request_id"] = request_id
        return AgentBuilderSession.from_dict(result)

    def wait_for_plan(
        self,
        request_id: str,
        poll_interval: float = 1.0,
        timeout: float = 120.0,
    ) -> AgentBuilderSession:
        """
        Wait for the agent builder to generate a plan.

        Args:
            request_id: The request ID from create()
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            AgentBuilderSession when plan is ready

        Raises:
            APIError: On timeout or error status

        """
        start = time.time()
        while True:
            session = self.status(request_id)

            if session.status == "awaiting_confirmation":
                return session
            if session.status == "error":
                raise APIError(
                    session.error_message or "Agent builder failed",
                    details={"session": session.__dict__},
                )
            if session.is_complete:
                return session

            if time.time() - start > timeout:
                raise APIError(
                    f"Timeout waiting for plan (status: {session.status})",
                    details={"session": session.__dict__},
                )

            time.sleep(poll_interval)

    def wait_for_completion(
        self,
        request_id: str,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
    ) -> AgentBuilderSession:
        """
        Wait for the agent builder to complete execution.

        Args:
            request_id: The request ID from create()
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            AgentBuilderSession with project_id

        Raises:
            APIError: On timeout or error status

        """
        start = time.time()
        while True:
            session = self.status(request_id)

            if session.status == "completed":
                return session
            if session.status == "error":
                raise APIError(
                    session.error_message or "Agent builder failed",
                    details={"session": session.__dict__},
                )

            if time.time() - start > timeout:
                raise APIError(
                    f"Timeout waiting for completion (status: {session.status})",
                    details={"session": session.__dict__},
                )

            time.sleep(poll_interval)

    def fix(self, project_id: str, prompt: str) -> AgentFixerSession:
        """
        Fix an existing agent using the agent fixer.

        Args:
            project_id: ID of the project/agent to fix
            prompt: Description of what to fix

        Returns:
            AgentFixerSession with request_id and initial status

        """
        result = self._client.workspace_post(
            f"/projects/{project_id}/agent-fixer",
            {"prompt": prompt},
        )
        return AgentFixerSession.from_dict(result)


# =============================================================================
# Project Operations
# =============================================================================


class ProjectOperations:
    """Operations for managing projects."""

    def __init__(self, client: APIClient):
        self._client = client

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResponse[Project]:
        """
        List projects in the workspace.

        Args:
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            PaginatedResponse containing Projects

        """
        return self._client.paginate_response(
            "/projects",
            limit=limit,
            offset=offset,
            parser=Project.from_dict,
        )

    def list_all(self) -> builtins.list[Project]:
        """
        List all projects in the workspace.

        Returns:
            List of all Projects

        """
        return self._client.paginate_all("/projects", parser=Project.from_dict)

    def get(self, project_id: str) -> Project:
        """
        Get a project by ID.

        Args:
            project_id: The project ID

        Returns:
            Project details

        """
        result = self._client.workspace_get(f"/projects/{project_id}")
        return Project.from_dict(result)

    def delete(self, project_id: str) -> bool:
        """
        Delete a project.

        Args:
            project_id: The project ID

        Returns:
            True on success

        """
        self._client.workspace_delete(f"/projects/{project_id}")
        return True


# =============================================================================
# Entity Operations
# =============================================================================


class EntityOperations:
    """Operations for managing entities (rows)."""

    def __init__(self, client: APIClient):
        self._client = client

    def list(
        self,
        project_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResponse[Entity]:
        """
        List entities in a project.

        Args:
            project_id: The project ID
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            PaginatedResponse containing Entities

        """
        return self._client.paginate_response(
            f"/projects/{project_id}/entities",
            limit=limit,
            offset=offset,
            parser=Entity.from_dict,
        )

    def list_all(self, project_id: str) -> builtins.list[Entity]:
        """
        List all entities in a project.

        Args:
            project_id: The project ID

        Returns:
            List of all Entities

        """
        return self._client.paginate_all(
            f"/projects/{project_id}/entities",
            parser=Entity.from_dict,
        )

    def iterate(self, project_id: str, limit: int = 100) -> Iterator[Entity]:
        """
        Iterate through all entities in a project.

        Args:
            project_id: The project ID
            limit: Items per page

        Yields:
            Entity objects

        """
        return self._client.paginate(
            f"/projects/{project_id}/entities",
            limit=limit,
            parser=Entity.from_dict,
        )

    def get(self, project_id: str, entity_id: str) -> Entity:
        """
        Get an entity by ID.

        Args:
            project_id: The project ID
            entity_id: The entity ID

        Returns:
            Entity with all field values

        """
        result = self._client.workspace_get(f"/projects/{project_id}/entities/{entity_id}")
        return Entity.from_dict(result)

    def get_field(
        self,
        project_id: str,
        entity_id: str,
        field_slug: str,
    ) -> Any:
        """
        Get a specific field value from an entity.

        Args:
            project_id: The project ID
            entity_id: The entity ID
            field_slug: The property slug

        Returns:
            The field value (tool_value if present, else manual_value)

        Raises:
            APIError: If field not found

        """
        entity = self.get(project_id, entity_id)
        if field_slug not in entity.field_values:
            available = list(entity.field_values.keys())
            raise APIError(
                f"Field '{field_slug}' not found",
                details={"available_fields": available},
            )
        return entity.field_values[field_slug].value

    def create(
        self,
        project_id: str,
        fields: dict[str, Any] | None = None,
        parent_entity_id: str | None = None,
    ) -> Entity:
        """
        Create a new entity.

        Args:
            project_id: The project ID
            fields: Optional dict of field values to prefill (property_slug -> value)
            parent_entity_id: Optional parent entity ID (for collection projects)

        Returns:
            Created Entity

        """
        data: dict[str, Any] = {}
        if fields:
            data["fields"] = fields
        if parent_entity_id:
            data["parent_entity_id"] = parent_entity_id

        result = self._client.workspace_post(
            f"/projects/{project_id}/entities",
            data if data else None,
        )
        return Entity.from_dict(result)

    def set_field(
        self,
        project_id: str,
        entity_id: str,
        property_slug: str,
        value: Any,
    ) -> dict[str, Any]:
        """
        Set a field value on an entity.

        Args:
            project_id: The project ID
            entity_id: The entity ID
            property_slug: The property slug
            value: The value to set

        Returns:
            API response

        """
        return self._client.workspace_put(
            f"/projects/{project_id}/entities/{entity_id}/properties/{property_slug}/set_value",
            {"value": value},
        )

    def recalculate(self, project_id: str, entity_id: str) -> dict[str, Any]:
        """
        Recalculate computed fields for an entity.

        Args:
            project_id: The project ID
            entity_id: The entity ID

        Returns:
            API response

        """
        return self._client.workspace_post(f"/projects/{project_id}/entities/{entity_id}/recalculate")

    def delete(self, project_id: str, entity_id: str) -> bool:
        """
        Delete an entity.

        Args:
            project_id: The project ID
            entity_id: The entity ID

        Returns:
            True on success

        """
        self._client.workspace_delete(f"/projects/{project_id}/entities/{entity_id}")
        return True


# =============================================================================
# Property Operations
# =============================================================================


class PropertyOperations:
    """Operations for managing properties (columns)."""

    NOT_IMPLEMENTED_MESSAGE = (
        "Direct property creation is not supported via CLI.\n"
        "Use 'v7 agent create' to create a new agent with properties, or\n"
        "use 'v7 agent fix <project_id>' to add properties to an existing agent."
    )

    def __init__(self, client: APIClient):
        self._client = client

    def list(self, project_id: str) -> list[Property]:
        """
        List properties in a project.

        Args:
            project_id: The project ID

        Returns:
            List of Properties

        """
        result = self._client.workspace_get(f"/projects/{project_id}/properties")
        return [Property.from_dict(p) for p in result.get("data", [])]

    def get(self, project_id: str, property_id_or_slug: str) -> Property:
        """
        Get a property by ID or slug.

        Args:
            project_id: The project ID
            property_id_or_slug: Property ID or slug

        Returns:
            Property details

        """
        result = self._client.workspace_get(f"/projects/{project_id}/properties/{property_id_or_slug}")
        return Property.from_dict(result)

    def add_from_prompt(self, project_id: str, prompt: str) -> Property:
        """
        Add a property using AI-powered configuration.

        Note: This is an internal method. For CLI users, use agent builder/fixer.

        Args:
            project_id: The project ID
            prompt: Description of the property

        Returns:
            Created Property

        """
        result = self._client.workspace_post(
            f"/projects/{project_id}/properties/from_prompt",
            {"prompt": prompt},
        )
        return Property.from_dict(result)

    def delete(self, project_id: str, property_id_or_slug: str) -> bool:
        """
        Delete a property.

        Args:
            project_id: The project ID
            property_id_or_slug: Property ID or slug

        Returns:
            True on success

        """
        self._client.workspace_delete(f"/projects/{project_id}/properties/{property_id_or_slug}")
        return True


# =============================================================================
# Export Operations
# =============================================================================


class ExportOperations:
    """Operations for exporting project data."""

    def __init__(self, client: APIClient):
        self._client = client

    def create(
        self,
        project_id: str,
        export_format: str = "csv",
        name: str | None = None,
        view_id: str | None = None,
    ) -> Export:
        """
        Create an export job.

        Args:
            project_id: The project ID
            export_format: Export format (csv, xlsx)
            name: Export name (auto-generated if not provided)
            view_id: Optional view ID to filter entities

        Returns:
            Export job details

        """
        # Generate default name if not provided
        if name is None:
            name = f"export-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        data: dict[str, Any] = {"name": name, "format": export_format}
        if view_id:
            data["view_id"] = view_id

        result = self._client.workspace_post(
            f"/projects/{project_id}/exports",
            data,
        )
        return Export.from_dict(result)

    def get(self, project_id: str, export_id: str) -> Export:
        """
        Get export job status.

        Args:
            project_id: The project ID
            export_id: The export ID

        Returns:
            Export job details

        """
        result = self._client.workspace_get(f"/projects/{project_id}/exports/{export_id}")
        return Export.from_dict(result)

    def list(self, project_id: str) -> list[Export]:
        """
        List exports for a project.

        Args:
            project_id: The project ID

        Returns:
            List of Export jobs

        """
        result = self._client.workspace_get(f"/projects/{project_id}/exports")
        return [Export.from_dict(e) for e in result.get("data", [])]

    def wait_for_completion(
        self,
        project_id: str,
        export_id: str,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
    ) -> Export:
        """
        Wait for an export to complete.

        Args:
            project_id: The project ID
            export_id: The export ID
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            Completed Export with download_url

        Raises:
            APIError: On timeout or error

        """
        start = time.time()
        while True:
            export = self.get(project_id, export_id)

            if export.is_ready:
                return export
            if export.status == "error":
                raise APIError(
                    export.error_message or "Export failed",
                    details={"export": export.__dict__},
                )

            if time.time() - start > timeout:
                raise APIError(
                    f"Timeout waiting for export (status: {export.status})",
                    details={"export": export.__dict__},
                )

            time.sleep(poll_interval)


# =============================================================================
# Invitation Operations
# =============================================================================


class InvitationOperations:
    """Operations for managing workspace invitations."""

    def __init__(self, client: APIClient):
        self._client = client

    def list(self) -> list[Invitation]:
        """
        List pending invitations in the workspace.

        Returns:
            List of Invitations

        """
        result = self._client.workspace_get("/invitations")
        return [Invitation.from_dict(i) for i in result.get("data", [])]

    def create(
        self,
        email: str,
        role: str = "member",
    ) -> builtins.list[dict[str, Any]]:
        """
        Invite a user to the workspace.

        Args:
            email: User's email address
            role: Role to assign (admin, editor, contributor, reviewer, reader, worker)

        Returns:
            List of invitation results

        """
        result = self._client.workspace_post(
            "/invitations",
            {"invitations": [{"email": email, "role": role}]},
        )
        return result.get("data", [])

    def create_bulk(
        self,
        invitations: builtins.list[dict[str, str]],
    ) -> builtins.list[dict[str, Any]]:
        """
        Invite multiple users to the workspace.

        Args:
            invitations: List of {"email": str, "role": str} dicts

        Returns:
            List of invitation results

        """
        result = self._client.workspace_post(
            "/invitations",
            {"invitations": invitations},
        )
        return result.get("data", [])

    def delete(self, invitation_id: str) -> bool:
        """
        Cancel a pending invitation.

        Args:
            invitation_id: The invitation ID

        Returns:
            True on success

        """
        self._client.workspace_delete(f"/invitations/{invitation_id}")
        return True


# =============================================================================
# Template Operations
# =============================================================================


class TemplateOperations:
    """Operations for importing/exporting project templates."""

    def __init__(self, client: APIClient):
        self._client = client

    def export_project(self, project_id: str) -> Template:
        """
        Export a project to a template.

        Args:
            project_id: The project ID to export

        Returns:
            Template containing project configuration

        """
        result = self._client.workspace_post(
            "/projects/export_to_template",
            {
                "project_ids": [project_id],
                "unexported_references": "external_objects",
            },
        )
        return Template.from_dict(result)

    def import_template(
        self,
        template: Template | dict[str, Any],
        folder_id: str | None = None,
        auto_rename: bool = True,
        max_retries: int = 10,
    ) -> list[Project]:
        """
        Import projects from a template.

        Args:
            template: Template object or dict
            folder_id: Optional parent folder ID
            auto_rename: If True, automatically rename projects on duplicate name error
            max_retries: Maximum rename attempts (appends (1), (2), etc.)

        Returns:
            List of created Projects

        Note:
            When auto_rename is True and a duplicate_name error occurs, the SDK
            will append a suffix like "(1)", "(2)" to the project name and retry.

            TODO: Long-term solution - the backend should support a `deduplicate`
            flag that handles this server-side, similar to how project slugs are
            auto-deduplicated. This would be more atomic and avoid race conditions.
            See: lib/agidb/projects/internal/create_project.ex for slug dedup logic.

        """
        if isinstance(template, Template):
            data = template.to_dict()
        else:
            data = {
                "projects": template.get("projects", []),
                "external_objects": template.get("external_objects", {}),
            }

        if folder_id:
            data["parent_folder_id"] = folder_id

        # Track original names for suffix generation
        original_names = [p.get("name", "Unnamed") for p in data.get("projects", [])]
        suffix = 0

        while True:
            try:
                result = self._client.workspace_post("/projects/import_from_template", data)
                # API returns instantiated_objects dict mapping template IDs to real IDs
                # e.g. {"instantiated_objects": {"template_proj_id": "real_uuid", ...}}
                instantiated = result.get("instantiated_objects", {})
                if instantiated:
                    # Fetch the created projects by their real IDs
                    projects = []
                    for real_id in instantiated.values():
                        if isinstance(real_id, str):
                            try:
                                proj = self._client.workspace_get(f"/projects/{real_id}")
                                projects.append(Project.from_dict(proj))
                            except APIError:
                                # Project might not be accessible, skip
                                pass
                    return projects
                # Fallback to data array if present
                return [Project.from_dict(p) for p in result.get("data", [])]
            except APIError as e:
                # Check for duplicate_name error
                is_duplicate = (
                    "duplicate_name" in str(e).lower()
                    or "duplicate name" in str(e).lower()
                    or (e.details and "duplicate_name" in str(e.details).lower())
                )

                if not is_duplicate or not auto_rename or suffix >= max_retries:
                    raise

                # Increment suffix and rename all projects
                suffix += 1
                for i, project in enumerate(data.get("projects", [])):
                    project["name"] = f"{original_names[i]} ({suffix})"

    def import_properties(
        self,
        project_id: str,
        template: Template | dict[str, Any],
    ) -> dict[str, Any]:
        """
        Import properties from a template into an existing project.

        Args:
            project_id: Target project ID
            template: Template containing properties

        Returns:
            API response

        """
        if isinstance(template, Template):
            if template.projects:
                properties = template.projects[0].get("properties", [])
            else:
                properties = []
            external_objects = template.external_objects
        else:
            if template.get("projects"):
                properties = template["projects"][0].get("properties", [])
            else:
                properties = template.get("properties", [])
            external_objects = template.get("external_objects", {})

        return self._client.workspace_post(
            f"/projects/{project_id}/import_properties",
            {
                "properties": properties,
                "external_objects": external_objects,
            },
        )


# =============================================================================
# Hub Operations
# =============================================================================


class HubOperations:
    """Operations for managing knowledge hubs."""

    def __init__(self, client: APIClient):
        self._client = client

    def list(self) -> list[Hub]:
        """
        List all hubs in the workspace.

        Returns:
            List of Hubs

        """
        result = self._client.workspace_get("/hubs")
        return [Hub.from_dict(h) for h in result.get("data", [])]

    def get(self, hub_id: str) -> Hub:
        """
        Get a hub by ID.

        Args:
            hub_id: The hub ID

        Returns:
            Hub details

        """
        result = self._client.workspace_get(f"/hubs/{hub_id}")
        return Hub.from_dict(result)

    def create(
        self,
        name: str,
        description: str | None = None,
    ) -> Hub:
        """
        Create a new hub.

        Args:
            name: Hub name
            description: Optional description

        Returns:
            Created Hub

        """
        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description

        result = self._client.workspace_post("/hubs", data)
        return Hub.from_dict(result)

    def delete(self, hub_id: str) -> bool:
        """
        Delete a hub.

        Args:
            hub_id: The hub ID

        Returns:
            True on success

        """
        self._client.workspace_delete(f"/hubs/{hub_id}")
        return True

    def list_files(self, hub_id: str) -> builtins.list[HubFile]:
        """
        List files in a hub.

        Args:
            hub_id: The hub ID

        Returns:
            List of HubFiles

        """
        # Get hub details which contains index with file info
        hub_data = self._client.workspace_get(f"/hubs/{hub_id}")

        # Files are stored in the hub's index.tool_value.value as a JSON array
        index = hub_data.get("index", {})
        tool_value = index.get("tool_value", {})
        files_json = tool_value.get("value")

        if not files_json:
            return []

        try:
            import json

            files_data = json.loads(files_json) if isinstance(files_json, str) else files_json
            if not isinstance(files_data, list):
                return []

            # Convert index data format to HubFile format
            return [
                HubFile(
                    id=f.get("slug", ""),
                    name=f.get("path", "").lstrip("/"),
                    storage_key=None,
                    content_type=None,
                    size=None,
                )
                for f in files_data
                if isinstance(f, dict) and f.get("path")
            ]
        except (json.JSONDecodeError, TypeError):
            return []

    def reindex(self, hub_id: str) -> dict[str, Any]:
        """
        Trigger reindexing of a hub.

        Args:
            hub_id: The hub ID

        Returns:
            API response

        """
        return self._client.workspace_post(f"/hubs/{hub_id}/reindex")
