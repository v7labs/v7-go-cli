"""
V7 CLI - Opinionated command-line interface.

This layer provides the user-facing CLI commands, using the SDK layer
for all operations. It handles:
- Argument parsing
- TTY detection for human vs machine output
- Pretty formatting for human output
- JSON output for piping/automation
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from v7_cli.core.client import APIError, CLIError, ValidationError
from v7_cli.sdk import V7Client

# =============================================================================
# Output Helpers
# =============================================================================


HUMAN_LIMIT = 20  # Default limit for human-readable output


def is_tty() -> bool:
    """Check if stdout is a TTY (human) or pipe (LLM/machine)."""
    return sys.stdout.isatty()


def json_output(data: Any, pretty: bool = False) -> None:
    """Print JSON output."""
    indent = 2 if pretty or is_tty() else None
    print(json.dumps(data, indent=indent, default=str))


def error_output(error: CLIError) -> None:
    """Print error and exit."""
    json_output(error.to_dict())
    sys.exit(1)


def success_output(data: Any) -> None:
    """Print success output."""
    json_output(data)


def table_output(
    headers: list[str],
    rows: list[list[str]],
    widths: list[int],
) -> None:
    """Print a formatted table for human output."""
    # Header
    header_line = "  ".join(h.ljust(w) if i < len(widths) else h for i, (h, w) in enumerate(zip(headers, widths)))
    print(header_line)
    print("-" * len(header_line))

    # Rows
    for row in rows:
        row_line = "  ".join(
            str(v)[:w].ljust(w) if i < len(widths) else str(v) for i, (v, w) in enumerate(zip(row, widths))
        )
        print(row_line)


# =============================================================================
# CLI Commands
# =============================================================================


def cmd_agent_create(client: V7Client, args: argparse.Namespace) -> None:
    """Create a new agent using the agent builder."""
    try:
        session = client.agent.create(args.prompt)
        success_output(
            {
                "request_id": session.request_id,
                "status": session.status,
                "message": "Agent builder started. Use 'v7 agent_builder status <request_id>' to check progress.",
            }
        )
    except APIError as e:
        error_output(e)


def cmd_agent_status(client: V7Client, args: argparse.Namespace) -> None:
    """Get agent builder session status."""
    try:
        session = client.agent.status(args.request_id)

        if is_tty():
            print(f"Status: {session.status}")
            if session.project_id:
                print(f"Project ID: {session.project_id}")
            if session.error_message:
                print(f"Error: {session.error_message}")
            if session.structured_plan:
                print(f"\nPlan ({len(session.structured_plan)} steps):")
                for i, step in enumerate(session.structured_plan, 1):
                    print(f"  {i}. [{step.property_id}] {step.title}: {step.description}")
        else:
            success_output(
                {
                    "request_id": session.request_id,
                    "status": session.status,
                    "project_id": session.project_id,
                    "structured_plan": [s.to_dict() for s in session.structured_plan],
                    "error_message": session.error_message,
                }
            )
    except APIError as e:
        error_output(e)


def cmd_agent_followup(client: V7Client, args: argparse.Namespace) -> None:
    """Send a followup message to refine the agent plan."""
    try:
        session = client.agent.followup(args.request_id, args.message)
        success_output(
            {
                "request_id": session.request_id,
                "status": session.status,
                "message": "Followup sent. Use 'v7 agent_builder status <request_id>' to check the updated plan.",
            }
        )
    except APIError as e:
        error_output(e)


def cmd_agent_execute(client: V7Client, args: argparse.Namespace) -> None:
    """Execute the agent builder plan."""
    try:
        session = client.agent.execute(args.request_id)
        success_output(
            {
                "request_id": session.request_id,
                "status": session.status,
                "project_id": session.project_id,
                "message": "Execution started. Use 'v7 agent_builder status <request_id>' to check progress.",
            }
        )
    except APIError as e:
        error_output(e)


def cmd_projects_list(client: V7Client, args: argparse.Namespace) -> None:
    """List projects in the workspace."""
    try:
        if is_tty():
            response = client.projects.list(
                limit=args.limit if args.limit is not None else HUMAN_LIMIT,
                offset=args.offset or 0,
            )
            if not response.data:
                print("No projects found.")
                return

            table_output(
                ["ID", "Name", "Type"],
                [[p.id, (p.name or "")[:40], p.type or ""] for p in response.data],
                [36, 40, 12],
            )

            if response.has_more:
                print(f"\nShowing {len(response.data)} of {response.total_count} projects")
        else:
            projects = client.projects.list_all()
            success_output(
                {
                    "data": [{"id": p.id, "name": p.name, "type": p.type} for p in projects],
                    "total_count": len(projects),
                }
            )
    except APIError as e:
        error_output(e)


def cmd_projects_get(client: V7Client, args: argparse.Namespace) -> None:
    """Get a project by ID."""
    try:
        project = client.projects.get(args.project_id)
        success_output(
            {
                "id": project.id,
                "name": project.name,
                "type": project.type,
                "description": project.description,
                "created_at": project.created_at,
                "folder_id": project.folder_id,
                "parent_property": project.parent_property,
            }
        )
    except APIError as e:
        error_output(e)


def cmd_projects_delete(client: V7Client, args: argparse.Namespace) -> None:
    """Delete a project."""
    try:
        client.projects.delete(args.project_id)
        success_output({"success": True, "message": f"Project {args.project_id} deleted"})
    except APIError as e:
        error_output(e)


def cmd_props_list(client: V7Client, args: argparse.Namespace) -> None:
    """List properties for a project."""
    try:
        props = client.properties.list(args.project_id)

        if is_tty():
            if not props:
                print("No properties found.")
                return

            table_output(
                ["Slug", "Name", "Type", "Tool"],
                [
                    [
                        (p.slug or "")[:25],
                        (p.name or "")[:30],
                        (p.type or "")[:12],
                        (p.tool or "")[:15],
                    ]
                    for p in props
                ],
                [25, 30, 12, 15],
            )
        else:
            success_output(
                {
                    "data": [
                        {
                            "id": p.id,
                            "slug": p.slug,
                            "name": p.name,
                            "type": p.type,
                            "tool": p.tool,
                        }
                        for p in props
                    ]
                }
            )
    except APIError as e:
        error_output(e)


def cmd_props_add(_client: V7Client, _args: argparse.Namespace) -> None:
    """Add a property - redirects to agent builder."""
    print("Direct property creation is not supported via CLI.", file=sys.stderr)
    print(file=sys.stderr)
    print("Use the agent builder instead:", file=sys.stderr)
    print(
        '  v7 agent_builder create "<prompt>"  - Create a new agent with properties',
        file=sys.stderr,
    )
    sys.exit(1)


def cmd_props_get(client: V7Client, args: argparse.Namespace) -> None:
    """Get property details."""
    try:
        prop = client.properties.get(args.project_id, args.property_id)
        success_output(
            {
                "id": prop.id,
                "slug": prop.slug,
                "name": prop.name,
                "type": prop.type,
                "tool": prop.tool,
                "description": prop.description,
                "tool_config": prop.tool_config,
            }
        )
    except APIError as e:
        error_output(e)


def cmd_props_delete(client: V7Client, args: argparse.Namespace) -> None:
    """Delete a property."""
    try:
        client.properties.delete(args.project_id, args.property_id)
        success_output({"success": True, "message": f"Property {args.property_id} deleted"})
    except APIError as e:
        error_output(e)


def cmd_ent_list(client: V7Client, args: argparse.Namespace) -> None:
    """List entities in a project."""
    try:
        if is_tty():
            response = client.entities.list(
                args.project_id,
                limit=args.limit if args.limit is not None else HUMAN_LIMIT,
                offset=args.offset or 0,
            )
            if not response.data:
                print("No entities found.")
                return

            table_output(
                ["ID", "Name"],
                [[e.id, (e.name or "(unnamed)")[:50]] for e in response.data],
                [36, 50],
            )

            if response.has_more:
                print(f"\nShowing {len(response.data)} of {response.total_count} entities")
        else:
            entities = client.entities.list_all(args.project_id)
            success_output(
                {
                    "data": [
                        {
                            "id": e.id,
                            "name": e.name,
                            "field_values": {slug: fv.value for slug, fv in e.field_values.items()},
                        }
                        for e in entities
                    ],
                    "total_count": len(entities),
                }
            )
    except APIError as e:
        error_output(e)


def cmd_ent_get(client: V7Client, args: argparse.Namespace) -> None:
    """Get an entity by ID."""
    try:
        entity = client.entities.get(args.project_id, args.entity_id)

        if args.field:
            # Extract specific field value
            if args.field not in entity.field_values:
                raise ValidationError(
                    f"Field '{args.field}' not found",
                    details={"available_fields": list(entity.field_values.keys())},
                )
            value = entity.field_values[args.field].value
            if isinstance(value, (dict, list)):
                json_output(value)
            else:
                print(value if value is not None else "")
        else:
            success_output(
                {
                    "id": entity.id,
                    "name": entity.name,
                    "project_id": entity.project_id,
                    "field_values": {
                        slug: {
                            "value": fv.value,
                            "status": fv.status,
                            "error": fv.error,
                        }
                        for slug, fv in entity.field_values.items()
                    },
                }
            )
    except CLIError as e:
        error_output(e)


def cmd_ent_create(client: V7Client, args: argparse.Namespace) -> None:
    """Create a new entity."""
    try:
        # Parse optional fields from JSON argument or stdin
        fields = None
        if hasattr(args, "fields") and args.fields:
            try:
                if args.fields == "-":
                    fields = json.load(sys.stdin)
                else:
                    fields = json.loads(args.fields)
            except json.JSONDecodeError as e:
                raise ValidationError(f"Invalid JSON in --fields: {e}")

        entity = client.entities.create(
            args.project_id,
            fields=fields,
            parent_entity_id=getattr(args, "parent_entity_id", None),
        )
        success_output(
            {
                "id": entity.id,
                "project_id": entity.project_id,
                "message": "Entity created",
            }
        )
    except CLIError as e:
        error_output(e)


def cmd_ent_set(client: V7Client, args: argparse.Namespace) -> None:
    """Set a field value on an entity."""
    try:
        # Try to parse value as JSON, otherwise treat as string
        try:
            value = json.loads(args.value)
        except json.JSONDecodeError:
            value = args.value

        result = client.entities.set_field(
            args.project_id,
            args.entity_id,
            args.property_slug,
            value,
        )
        success_output(result)
    except APIError as e:
        error_output(e)


def cmd_ent_recalc(client: V7Client, args: argparse.Namespace) -> None:
    """Recalculate computed fields for an entity."""
    try:
        result = client.entities.recalculate(args.project_id, args.entity_id)
        success_output(result)
    except APIError as e:
        error_output(e)


def cmd_ent_delete(client: V7Client, args: argparse.Namespace) -> None:
    """Delete an entity."""
    try:
        client.entities.delete(args.project_id, args.entity_id)
        success_output({"success": True, "message": f"Entity {args.entity_id} deleted"})
    except APIError as e:
        error_output(e)


def cmd_export(client: V7Client, args: argparse.Namespace) -> None:
    """Export project data."""
    try:
        # Create export
        export = client.exports.create(
            args.project_id,
            export_format=args.format,
            name=getattr(args, "name", None),
        )

        if is_tty():
            print(f"Export started: {export.id}")
            print(f"Format: {export.format}")
            print(f"Status: {export.status}")

            if not args.no_wait:
                print("\nWaiting for export to complete...")
                export = client.exports.wait_for_completion(args.project_id, export.id)
                print("\nExport ready!")
                print(f"Download URL: {export.download_url}")
        else:
            if not args.no_wait:
                export = client.exports.wait_for_completion(args.project_id, export.id)

            success_output(
                {
                    "id": export.id,
                    "status": export.status,
                    "format": export.format,
                    "download_url": export.download_url,
                }
            )
    except APIError as e:
        error_output(e)


def cmd_invite(client: V7Client, args: argparse.Namespace) -> None:
    """Invite a user to the workspace."""
    try:
        result = client.invitations.create(args.email, args.role)
        success_output(
            {
                "success": True,
                "message": f"Invitation sent to {args.email}",
                "data": result,
            }
        )
    except APIError as e:
        error_output(e)


def cmd_template_export(client: V7Client, args: argparse.Namespace) -> None:
    """Export a project to template JSON."""
    try:
        template = client.templates.export_project(args.project_id)
        json_output(template.to_dict(), pretty=True)
    except APIError as e:
        error_output(e)


def cmd_template_import(client: V7Client, args: argparse.Namespace) -> None:
    """Import projects from a template."""
    try:
        # Read template from file or stdin
        if args.file == "-":
            template_json = sys.stdin.read()
        else:
            template_json = Path(args.file).read_text()

        template = json.loads(template_json)
        auto_rename = not getattr(args, "no_auto_rename", False)
        projects = client.templates.import_template(
            template,
            folder_id=args.folder,
            auto_rename=auto_rename,
        )

        success_output(
            {
                "success": True,
                "message": f"Imported {len(projects)} project(s)",
                "projects": [{"id": p.id, "name": p.name} for p in projects],
            }
        )
    except FileNotFoundError:
        error_output(APIError(f"File not found: {args.file}"))
    except json.JSONDecodeError as e:
        error_output(APIError(f"Invalid JSON: {e}"))
    except APIError as e:
        error_output(e)


def cmd_hub_list(client: V7Client, _args: argparse.Namespace) -> None:
    """List hubs in the workspace."""
    try:
        hubs = client.hubs.list()

        if is_tty():
            if not hubs:
                print("No hubs found.")
                return

            table_output(
                ["ID", "Name", "Files", "Status"],
                [[h.id, (h.name or "")[:40], str(h.file_count or 0), h.status or ""] for h in hubs],
                [36, 40, 8, 10],
            )
        else:
            success_output(
                {
                    "data": [
                        {
                            "id": h.id,
                            "name": h.name,
                            "file_count": h.file_count,
                            "status": h.status,
                        }
                        for h in hubs
                    ]
                }
            )
    except APIError as e:
        error_output(e)


def cmd_hub_get(client: V7Client, args: argparse.Namespace) -> None:
    """Get a hub by ID."""
    try:
        hub = client.hubs.get(args.hub_id)
        success_output(
            {
                "id": hub.id,
                "name": hub.name,
                "description": hub.description,
                "status": hub.status,
                "file_count": hub.file_count,
                "created_at": hub.created_at,
            }
        )
    except APIError as e:
        error_output(e)


def cmd_hub_files(client: V7Client, args: argparse.Namespace) -> None:
    """List files in a hub."""
    try:
        files = client.hubs.list_files(args.hub_id)

        if is_tty():
            if not files:
                print("No files in hub.")
                return

            table_output(
                ["ID", "Name", "Type", "Size"],
                [[f.id, (f.name or "")[:50], f.content_type or "", str(f.size or "")] for f in files],
                [36, 50, 20, 10],
            )
        else:
            success_output(
                {
                    "data": [
                        {
                            "id": f.id,
                            "name": f.name,
                            "content_type": f.content_type,
                            "size": f.size,
                        }
                        for f in files
                    ]
                }
            )
    except APIError as e:
        error_output(e)


# =============================================================================
# Main CLI
# =============================================================================


def create_parser() -> argparse.ArgumentParser:  # noqa: PLR0915
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="V7 Go CLI - Command-line interface for V7 Go API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Output Modes:
  TTY (human):  Pretty tables, limited rows
  Pipe (LLM):   Full JSON, auto-paginates all results

Examples:
  v7 agent_builder create "Extract invoice data: vendor, amount, due date"
  v7 agent_builder status <request_id>
  v7 agent_builder execute <request_id>
  v7 ent list <project_id> | jq '.data[].id'
  v7 export <project_id> --format csv
""",
    )
    parser.add_argument("--workspace", "-w", help="Workspace ID (overrides V7_GO_WORKSPACE_ID)")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ========== Agent Builder ==========
    agent = subparsers.add_parser("agent_builder", help="Create agents from natural language")
    agent.set_defaults(func=lambda _c, _a: agent.print_help())
    agent_sub = agent.add_subparsers(dest="subcommand")

    a_create = agent_sub.add_parser("create", help="Create new agent from prompt")
    a_create.add_argument("prompt", help="Describe the agent you want to build")
    a_create.set_defaults(func=cmd_agent_create)

    a_status = agent_sub.add_parser("status", help="Check agent builder status")
    a_status.add_argument("request_id", help="Request ID from create")
    a_status.set_defaults(func=cmd_agent_status)

    a_followup = agent_sub.add_parser("followup", help="Refine the agent plan")
    a_followup.add_argument("request_id", help="Request ID")
    a_followup.add_argument("message", help="Refinement message")
    a_followup.set_defaults(func=cmd_agent_followup)

    a_execute = agent_sub.add_parser("execute", help="Execute the plan to create agent")
    a_execute.add_argument("request_id", help="Request ID")
    a_execute.set_defaults(func=cmd_agent_execute)

    # ========== Projects ==========
    projects = subparsers.add_parser("projects", help="List and manage projects")
    projects.set_defaults(func=lambda _c, _a: projects.print_help())
    projects_sub = projects.add_subparsers(dest="subcommand")

    p_list = projects_sub.add_parser("list", help="List projects")
    p_list.add_argument("--limit", "-l", type=int, help="Max results (TTY only)")
    p_list.add_argument("--offset", "-o", type=int, help="Offset for pagination")
    p_list.set_defaults(func=cmd_projects_list)

    p_get = projects_sub.add_parser("get", help="Get project details")
    p_get.add_argument("project_id", help="Project ID")
    p_get.set_defaults(func=cmd_projects_get)

    p_delete = projects_sub.add_parser("delete", help="Delete a project")
    p_delete.add_argument("project_id", help="Project ID")
    p_delete.set_defaults(func=cmd_projects_delete)

    # ========== Properties ==========
    props = subparsers.add_parser("props", help="Manage properties (columns)")
    props.set_defaults(func=lambda _c, _a: props.print_help())
    props_sub = props.add_subparsers(dest="subcommand")

    pr_list = props_sub.add_parser("list", help="List properties")
    pr_list.add_argument("project_id", help="Project ID")
    pr_list.set_defaults(func=cmd_props_list)

    pr_add = props_sub.add_parser("add", help="Add property (use agent builder instead)")
    pr_add.add_argument("project_id", help="Project ID")
    pr_add.add_argument("prompt", help="Property description")
    pr_add.set_defaults(func=cmd_props_add)

    pr_get = props_sub.add_parser("get", help="Get property details")
    pr_get.add_argument("project_id", help="Project ID")
    pr_get.add_argument("property_id", help="Property ID or slug")
    pr_get.set_defaults(func=cmd_props_get)

    pr_delete = props_sub.add_parser("delete", help="Delete a property")
    pr_delete.add_argument("project_id", help="Project ID")
    pr_delete.add_argument("property_id", help="Property ID or slug")
    pr_delete.set_defaults(func=cmd_props_delete)

    # ========== Entities ==========
    ent = subparsers.add_parser("ent", help="Manage entities (rows)")
    ent.set_defaults(func=lambda _c, _a: ent.print_help())
    ent_sub = ent.add_subparsers(dest="subcommand")

    e_list = ent_sub.add_parser("list", help="List entities")
    e_list.add_argument("project_id", help="Project ID")
    e_list.add_argument("--limit", "-l", type=int, help="Max results (TTY only)")
    e_list.add_argument("--offset", "-o", type=int, help="Offset for pagination")
    e_list.set_defaults(func=cmd_ent_list)

    e_create = ent_sub.add_parser("create", help="Create an entity")
    e_create.add_argument("project_id", help="Project ID")
    e_create.add_argument(
        "--fields",
        "-f",
        help="JSON object with field values to prefill (or - for stdin)",
    )
    e_create.add_argument(
        "--parent",
        dest="parent_entity_id",
        help="Parent entity ID (required for collection projects)",
    )
    e_create.set_defaults(func=cmd_ent_create)

    e_get = ent_sub.add_parser("get", help="Get entity details")
    e_get.add_argument("project_id", help="Project ID")
    e_get.add_argument("entity_id", help="Entity ID")
    e_get.add_argument("--field", "-f", help="Extract specific field value by slug")
    e_get.set_defaults(func=cmd_ent_get)

    e_set = ent_sub.add_parser("set", help="Set a field value")
    e_set.add_argument("project_id", help="Project ID")
    e_set.add_argument("entity_id", help="Entity ID")
    e_set.add_argument("property_slug", help="Property slug")
    e_set.add_argument("value", help="Value (JSON or string)")
    e_set.set_defaults(func=cmd_ent_set)

    e_recalc = ent_sub.add_parser("recalc", help="Recalculate computed fields")
    e_recalc.add_argument("project_id", help="Project ID")
    e_recalc.add_argument("entity_id", help="Entity ID")
    e_recalc.set_defaults(func=cmd_ent_recalc)

    e_delete = ent_sub.add_parser("delete", help="Delete an entity")
    e_delete.add_argument("project_id", help="Project ID")
    e_delete.add_argument("entity_id", help="Entity ID")
    e_delete.set_defaults(func=cmd_ent_delete)

    # ========== Export ==========
    export = subparsers.add_parser("export", help="Export project data")
    export.add_argument("project_id", help="Project ID to export")
    export.add_argument("--format", "-f", default="csv", choices=["csv", "xlsx"], help="Export format")
    export.add_argument("--name", "-n", help="Export name (auto-generated if not provided)")
    export.add_argument("--no-wait", action="store_true", help="Don't wait for export to complete")
    export.set_defaults(func=cmd_export)

    # ========== Invite ==========
    invite = subparsers.add_parser("invite", help="Invite a user to the workspace")
    invite.add_argument("email", help="Email address to invite")
    invite.add_argument(
        "--role",
        "-r",
        default="editor",
        choices=["admin", "editor", "contributor", "reviewer", "reader", "worker"],
        help="Role to assign (admin, editor, contributor, reviewer, reader, worker)",
    )
    invite.set_defaults(func=cmd_invite)

    # ========== Template ==========
    template = subparsers.add_parser("template", help="Import/export agent templates")
    template.set_defaults(func=lambda _c, _a: template.print_help())
    template_sub = template.add_subparsers(dest="subcommand")

    t_export = template_sub.add_parser("export", help="Export project to template JSON")
    t_export.add_argument("project_id", help="Project ID to export")
    t_export.set_defaults(func=cmd_template_export)

    t_import = template_sub.add_parser("import", help="Import projects from template")
    t_import.add_argument("file", help="Template JSON file (or - for stdin)")
    t_import.add_argument("--folder", "-f", help="Parent folder ID for imported projects")
    t_import.add_argument(
        "--no-auto-rename",
        action="store_true",
        help="Disable auto-renaming on duplicate names (will error instead)",
    )
    t_import.set_defaults(func=cmd_template_import)

    # ========== Hub ==========
    hub = subparsers.add_parser("hub", help="Manage knowledge hubs")
    hub.set_defaults(func=lambda _c, _a: hub.print_help())
    hub_sub = hub.add_subparsers(dest="subcommand")

    h_list = hub_sub.add_parser("list", help="List hubs")
    h_list.set_defaults(func=cmd_hub_list)

    h_get = hub_sub.add_parser("get", help="Get hub details")
    h_get.add_argument("hub_id", help="Hub ID")
    h_get.set_defaults(func=cmd_hub_get)

    h_files = hub_sub.add_parser("files", help="List files in hub")
    h_files.add_argument("hub_id", help="Hub ID")
    h_files.set_defaults(func=cmd_hub_files)

    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Create client
    client = V7Client(workspace_id=args.workspace)

    # Run command (all subparsers have default funcs that print help)
    args.func(client, args)


if __name__ == "__main__":
    main()
