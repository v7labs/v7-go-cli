# v7-cli

Command-line interface and Python SDK for the [V7 Go](https://go.v7labs.com) API.

## Installation

```bash
uv pip install git+https://github.com/v7labs/v7-go-cli.git
```

## Quick Start

### 1. Set up credentials

```bash
export V7_GO_API_KEY="your-api-key"
export V7_GO_WORKSPACE_ID="your-workspace-id"
```

### 2. Use the CLI

```bash
# List projects
v7 projects list

# Create an AI agent from natural language
v7 agent_builder create "Extract invoice data: vendor, amount, due date"

# Export project data
v7 export <project_id> --format csv
```

## Commands

| Command | Description |
|---------|-------------|
| `v7 projects list` | List all projects |
| `v7 projects get <id>` | Get project details |
| `v7 ent list <project>` | List entities (rows) |
| `v7 ent get <project> <id>` | Get entity details |
| `v7 ent set <project> <id> <field> "value"` | Set field value |
| `v7 props list <project>` | List properties (columns) |
| `v7 export <project>` | Export project data |
| `v7 hub list` | List knowledge hubs |
| `v7 hub files <id>` | List files in a hub |
| `v7 invite <email>` | Invite user to workspace |
| `v7 agent_builder create "prompt"` | Create agent from description |
| `v7 template export <project>` | Export project as template |
| `v7 template import <file>` | Import template |

Run `v7 --help` or `v7 <command> --help` for full usage.

## Output Modes

The CLI automatically detects how it's being used:

| Context | Output | Behavior |
|---------|--------|----------|
| Terminal (TTY) | Pretty tables | Limited rows, human-readable |
| Piped (`\| jq`) | JSON | Full data, all pages, machine-readable |

```bash
# Human-readable table
v7 projects list

# JSON for scripting
v7 projects list | jq '.data[].id'

# Bulk operations
v7 ent list <project> | jq -r '.data[].id' | while read id; do
  v7 ent recalc <project> $id
done
```

## Python SDK

The CLI includes a typed Python SDK for programmatic access.

### SDK Layer (Recommended)

```python
from v7_cli import V7Client

client = V7Client()

# List all projects
projects = client.projects.list_all()
for p in projects:
    print(p.name, p.id)

# Create an AI agent
session = client.agent.create("Extract invoice fields: vendor, amount, date")
session = client.agent.wait_for_plan(session.request_id)
session = client.agent.execute(session.request_id)
print(f"Created project: {session.project_id}")

# Work with entities
entities = client.entities.list_all(project_id)
for entity in entities:
    print(entity.name, entity.field_values)

# Get a specific field value
value = client.entities.get_field(project_id, entity_id, "vendor-name")

# Export project data
export = client.exports.create(project_id, export_format="csv")
export = client.exports.wait_for_completion(project_id, export.id)
print(export.download_url)
```

### Core Layer (Low-level)

```python
from v7_cli.core import APIClient, Project, Entity

client = APIClient()

# Raw API calls
result = client.workspace_get("/projects/123")
project = Project.from_dict(result)

# Pagination
for entity_data in client.paginate("/projects/123/entities"):
    entity = Entity.from_dict(entity_data)
    print(entity.id)
```

## Architecture

```
CLI (opinionated commands, TTY detection)
  │
  ▼
SDK (typed, ergonomic, chainable)
  │
  ▼
Core (raw HTTP, pagination, types)
```

## Configuration

| Environment Variable | Description | Required |
|---------------------|-------------|----------|
| `V7_GO_API_KEY` | Your API key | Yes |
| `V7_GO_WORKSPACE_ID` | Default workspace ID | Yes (or use `-w` flag) |
| `V7_GO_BASE_URL` | API base URL | No (default: `https://api.go.v7labs.com`) |

## Development

```bash
# Clone and install
git clone https://github.com/v7labs/v7-go-cli.git
cd v7-go-cli
uv sync --group dev

# Run tests
uv run pytest

# Type checking
uv run mypy v7_cli

# Linting
uv run ruff check v7_cli
```

## License

MIT
