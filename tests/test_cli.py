"""
V7 CLI Smoke Test Suite - Try All Endpoints and Flag Combinations

This test suite systematically exercises every CLI endpoint with all valid
flag combinations against the REAL API to find compatibility issues.

Run with: python -m pytest tests/test_cli.py -v -s
Requires: V7_GO_API_KEY and V7_GO_WORKSPACE_ID environment variables

Results are printed as a matrix showing which combinations work/fail.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from v7_cli.core.client import APIClient, APIError

# =============================================================================
# Configuration
# =============================================================================

# Get credentials from environment
API_KEY = os.environ.get("V7_GO_API_KEY")
WORKSPACE_ID = os.environ.get("V7_GO_WORKSPACE_ID")
# Try V7_GO_BASE_API_URL first (for dev setups), fall back to V7_GO_BASE_URL
BASE_URL = os.environ.get("V7_GO_BASE_API_URL") or os.environ.get("V7_GO_BASE_URL")

# Test data - we'll discover real IDs during test setup
TEST_DATA: dict[str, Any] = {}


# =============================================================================
# Test Result Tracking
# =============================================================================


@dataclass
class CLITestResult:
    """Track result of a single CLI invocation."""

    command: str
    args: list[str]
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    error_type: str | None = None


@dataclass
class CLITestMatrix:
    """Track all test results."""

    results: list[CLITestResult] = field(default_factory=list)

    def add(self, result: CLITestResult) -> None:
        self.results.append(result)

    def print_summary(self) -> None:
        """Print a summary matrix of results."""
        passed = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]

        print("\n" + "=" * 80)
        print("V7 CLI SMOKE TEST RESULTS")
        print("=" * 80)
        print(f"\nTotal: {len(self.results)} | Passed: {len(passed)} | Failed: {len(failed)}")

        if failed:
            print("\n" + "-" * 80)
            print("FAILURES:")
            print("-" * 80)
            for r in failed:
                args_str = " ".join(r.args)
                print(f"\n❌ {r.command} {args_str}")
                print(f"   Exit code: {r.exit_code}")
                if r.error_type:
                    print(f"   Error type: {r.error_type}")
                if r.stderr:
                    # Show first 200 chars of stderr
                    stderr_preview = r.stderr[:200].replace("\n", " ")
                    print(f"   Stderr: {stderr_preview}...")

        print("\n" + "-" * 80)
        print("PASSED:")
        print("-" * 80)
        for r in passed:
            args_str = " ".join(r.args)
            print(f"✅ {r.command} {args_str}")


# Global test matrix
MATRIX = CLITestMatrix()


# =============================================================================
# CLI Runner
# =============================================================================


CLI_TIMEOUT = 60  # Timeout in seconds for CLI commands


def run_cli(*args: str, stdin: str | None = None, timeout: int = CLI_TIMEOUT) -> CLITestResult:
    """Run the CLI with given arguments and return a CLITestResult."""
    cmd = [sys.executable, "-m", "v7_cli.cli"] + list(args)

    env = os.environ.copy()
    if API_KEY:
        env["V7_GO_API_KEY"] = API_KEY
    if WORKSPACE_ID:
        env["V7_GO_WORKSPACE_ID"] = WORKSPACE_ID
    if BASE_URL:
        env["V7_GO_BASE_URL"] = BASE_URL

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=stdin,
            env=env,
            timeout=timeout,
            cwd=Path(__file__).resolve().parent.parent,
        )
    except subprocess.TimeoutExpired:
        command = args[0] if args else ""
        remaining_args = list(args[1:]) if len(args) > 1 else []
        return CLITestResult(
            command=command,
            args=remaining_args,
            success=False,
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            error_type="Timeout",
        )

    # Determine error type from stderr
    error_type = None
    if result.returncode != 0:
        if "APIError" in result.stderr or "API Error" in result.stderr:
            error_type = "APIError"
        elif "ValidationError" in result.stderr:
            error_type = "ValidationError"
        elif "not found" in result.stderr.lower():
            error_type = "NotFound"
        elif "KeyError" in result.stderr or "AttributeError" in result.stderr:
            error_type = "ParseError"
        else:
            error_type = "Unknown"

    # Try to parse JSON output for validation
    if result.returncode == 0 and result.stdout.strip():
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError:
            # Not JSON output (probably TTY mode), that's ok
            pass

    command = args[0] if args else ""
    remaining_args = list(args[1:]) if len(args) > 1 else []

    return CLITestResult(
        command=command,
        args=remaining_args,
        success=result.returncode == 0,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        error_type=error_type,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def require_credentials():
    """Skip test if credentials not available."""
    if not API_KEY or not WORKSPACE_ID:
        pytest.skip("V7_GO_API_KEY and V7_GO_WORKSPACE_ID required")
    return True


def _extract_list_data(data: Any) -> list[dict[str, Any]]:
    """Extract list data from API response, handling {"data": [...]} format."""
    if isinstance(data, dict):
        return data.get("data", [])
    if isinstance(data, list):
        return data
    return []


def _normalise_project_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Unwrap common project payload shapes."""
    if isinstance(data.get("data"), dict):
        data = data["data"]
    if isinstance(data.get("project"), dict):
        data = data["project"]
    if isinstance(data.get("data"), dict) and isinstance(data["data"].get("project"), dict):
        data = data["data"]["project"]
    return data


def _find_parent_project_id_by_scan(child_project_id: str, parent_property_id: str | None) -> str | None:
    """Scan projects to find the parent project for a collection child."""
    client = APIClient()
    try:
        projects = client.paginate_all("/projects")
    except APIError as e:
        raise AssertionError(f"projects list failed: {e}") from e

    for project_item in projects:
        if not isinstance(project_item, dict):
            continue
        project = _normalise_project_payload(project_item)
        if project.get("id") == child_project_id:
            continue
        properties = project.get("properties")
        if not isinstance(properties, list):
            continue
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            if parent_property_id and prop.get("id") == parent_property_id:
                return project.get("id")
            config = prop.get("config") or {}
            sub_config = config.get("subproject_config") or config.get("subprojectConfig") or {}
            child_id = sub_config.get("child_project_id") or sub_config.get("childProjectId")
            if child_id == child_project_id:
                return project.get("id")
    return None


def _resolve_parent_project_id(project_id: str, data: dict[str, Any]) -> str | None:
    """Resolve parent project ID from a project payload."""
    data = _normalise_project_payload(data)

    parent_project_id = data.get("parent_project_id") or data.get("parentProjectId")
    if parent_project_id:
        return parent_project_id

    parent_project = data.get("parent_project") or data.get("parentProject")
    if isinstance(parent_project, dict):
        parent_project_id = parent_project.get("id") or parent_project.get("project_id")
        if parent_project_id:
            return parent_project_id

    parent_property = data.get("parent_property") or data.get("parentProperty")
    if isinstance(parent_property, dict):
        parent_project_id = (
            parent_property.get("parent_project_id")
            or parent_property.get("parentProjectId")
            or parent_property.get("project_id")
            or parent_property.get("projectId")
        )
        if parent_project_id:
            return parent_project_id
        parent_property_id = parent_property.get("id")
        parent_project_id = _find_parent_project_id_by_scan(project_id, parent_property_id)
        if parent_project_id:
            return parent_project_id

    properties = data.get("properties")
    if isinstance(properties, list):
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            parent_project_id = prop.get("parent_project_id") or prop.get("parentProjectId")
            if parent_project_id:
                return parent_project_id
    return None


def _parent_required(result: CLITestResult) -> bool:
    """Check if create failed due to missing parent_entity_id."""
    output = (result.stdout or "").lower()
    return "parent_entity_id" in output and "required" in output


def _get_project_details(project_id: str) -> dict[str, Any]:
    """Fetch project details directly from the API."""
    client = APIClient()
    try:
        data = client.workspace_get(f"/projects/{project_id}")
    except APIError as e:
        raise AssertionError(f"project get failed: {e}") from e
    if not isinstance(data, dict):
        raise TypeError("project get returned non-object JSON")
    return _normalise_project_payload(data)


def _resolve_parent_chain(project_id: str) -> list[str]:
    """Resolve parent project chain from root -> target project."""
    chain = [project_id]
    seen = {project_id}
    current = project_id
    while True:
        details = _get_project_details(current)
        parent_id = _resolve_parent_project_id(current, details)
        if not parent_id:
            break
        if parent_id in seen:
            raise AssertionError("Detected parent project cycle")
        seen.add(parent_id)
        chain.append(parent_id)
        current = parent_id
    return list(reversed(chain))


def _ensure_parent_entity_chain(project_id: str) -> str | None:
    """Ensure parent entities exist for nested collection projects."""
    chain = _resolve_parent_chain(project_id)
    if len(chain) == 1:
        return None

    created = TEST_DATA.setdefault("created_parent_entity_ids", {})
    parent_entity_id: str | None = None

    # Create entities from root -> parent of target
    for proj_id in chain[:-1]:
        if proj_id in created:
            parent_entity_id = created[proj_id]
            continue

        if parent_entity_id:
            result = run_cli("ent", "create", proj_id, "--parent", parent_entity_id)
        else:
            result = run_cli("ent", "create", proj_id)

        if result.success and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                created[proj_id] = data.get("id")
                parent_entity_id = created[proj_id]
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                raise AssertionError(f"parent entity create parse failed: {e}") from e
        else:
            raise AssertionError(f"parent entity create failed: {result.stderr or result.stdout}")

    return parent_entity_id


@pytest.fixture(scope="session")
def discover_test_data(require_credentials):
    """Discover real IDs from the API for use in tests."""
    discovery_errors: list[str] = []

    # Get first project
    result = run_cli("projects", "list", "--limit", "1")
    if result.success and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            projects = _extract_list_data(data)
            if projects:
                TEST_DATA["project_id"] = projects[0].get("id")
                TEST_DATA["project_name"] = projects[0].get("name", "Unknown")
                parent_project_id = _resolve_parent_project_id(TEST_DATA["project_id"], projects[0])
                if parent_project_id:
                    TEST_DATA["parent_project_id"] = parent_project_id
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            discovery_errors.append(f"projects: {e}")
    elif not result.success:
        discovery_errors.append(f"projects list failed: {result.stderr or result.stdout}")

    # Get project details (parent_property determines collection projects)
    if TEST_DATA.get("project_id") and not TEST_DATA.get("parent_project_id"):
        try:
            data = _get_project_details(TEST_DATA["project_id"])
            parent_project_id = _resolve_parent_project_id(TEST_DATA["project_id"], data)
            if parent_project_id:
                TEST_DATA["parent_project_id"] = parent_project_id
        except AssertionError as e:
            discovery_errors.append(str(e))

    # Get first hub
    result = run_cli("hub", "list")
    if result.success and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            hubs = _extract_list_data(data)
            if hubs:
                TEST_DATA["hub_id"] = hubs[0].get("id")
                TEST_DATA["hub_name"] = hubs[0].get("name", "Unknown")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            discovery_errors.append(f"hubs: {e}")
    elif not result.success:
        discovery_errors.append(f"hub list failed: {result.stderr or result.stdout}")

    # Get first entity (if we have a project)
    if TEST_DATA.get("project_id"):
        result = run_cli("ent", "list", TEST_DATA["project_id"], "--limit", "1")
        if result.success and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                entities = _extract_list_data(data)
                if entities:
                    TEST_DATA["entity_id"] = entities[0].get("id")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                discovery_errors.append(f"entities: {e}")

    # Get first property (if we have a project)
    if TEST_DATA.get("project_id"):
        result = run_cli("props", "list", TEST_DATA["project_id"])
        if result.success and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                props = _extract_list_data(data)
                if props:
                    TEST_DATA["property_id"] = props[0].get("id")
                    TEST_DATA["property_slug"] = props[0].get("slug")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                discovery_errors.append(f"properties: {e}")

    # Create an agent session for followup tests
    result = run_cli("agent_builder", "create", "Test agent for smoke testing - extract document info")
    if result.success and result.stdout.strip():
        try:
            data = json.loads(result.stdout)
            TEST_DATA["agent_request_id"] = data.get("request_id")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            discovery_errors.append(f"agent_builder create: {e}")

    # Log discovery results
    print(f"\n[TEST DATA] Discovered: {TEST_DATA}")
    if discovery_errors:
        print(f"[TEST DATA] Discovery errors: {discovery_errors}")
    return TEST_DATA


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data(request):
    """Cleanup created resources after all tests complete."""
    yield
    # Cleanup created entities
    if TEST_DATA.get("created_entity_id") and TEST_DATA.get("project_id"):
        run_cli("ent", "delete", TEST_DATA["project_id"], TEST_DATA["created_entity_id"])
    if TEST_DATA.get("created_parent_entity_ids"):
        for project_id, entity_id in TEST_DATA["created_parent_entity_ids"].items():
            if entity_id:
                run_cli("ent", "delete", project_id, entity_id)


# =============================================================================
# Help Tests - All Commands Should Have Working Help
# =============================================================================


class TestHelpCommands:
    """Test that all help commands work."""

    def test_main_help(self):
        result = run_cli("--help")
        MATRIX.add(result)
        assert result.success, f"Main help failed: {result.stderr}"
        assert "V7 Go CLI" in result.stdout

    def test_agent_builder_help(self):
        result = run_cli("agent_builder", "--help")
        MATRIX.add(result)
        assert result.success, f"Agent builder help failed: {result.stderr}"

    def test_projects_help(self):
        result = run_cli("projects", "--help")
        MATRIX.add(result)
        assert result.success, f"Projects help failed: {result.stderr}"

    def test_ent_help(self):
        result = run_cli("ent", "--help")
        MATRIX.add(result)
        assert result.success, f"Ent help failed: {result.stderr}"

    def test_props_help(self):
        result = run_cli("props", "--help")
        MATRIX.add(result)
        assert result.success, f"Props help failed: {result.stderr}"

    def test_hub_help(self):
        result = run_cli("hub", "--help")
        MATRIX.add(result)
        assert result.success, f"Hub help failed: {result.stderr}"

    def test_export_help(self):
        result = run_cli("export", "--help")
        MATRIX.add(result)
        assert result.success, f"Export help failed: {result.stderr}"

    def test_template_help(self):
        result = run_cli("template", "--help")
        MATRIX.add(result)
        assert result.success, f"Template help failed: {result.stderr}"


# =============================================================================
# Projects Endpoint Tests
# =============================================================================


class TestProjectsEndpoint:
    """Test all projects endpoint variations."""

    @pytest.mark.parametrize(
        "args,desc",
        [
            ([], "no flags"),
            (["--limit", "5"], "with limit"),
            (["--offset", "0"], "with offset"),
            (["--limit", "10", "--offset", "0"], "with limit and offset"),
        ],
    )
    def test_projects_list_variations(self, discover_test_data, args, desc):
        result = run_cli("projects", "list", *args)
        MATRIX.add(result)
        assert result.success, f"projects list {desc} failed: {result.stderr}"

    def test_projects_get(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available for testing")
        result = run_cli("projects", "get", TEST_DATA["project_id"])
        MATRIX.add(result)
        assert result.success, f"projects get failed: {result.stderr}"

    def test_projects_get_invalid_id(self, discover_test_data):
        result = run_cli("projects", "get", "invalid-project-id-12345")
        MATRIX.add(result)
        # Should fail gracefully with proper error
        assert not result.success, "Getting invalid project ID should fail"


# =============================================================================
# Entity Endpoint Tests
# =============================================================================


class TestEntityEndpoint:
    """Test all entity endpoint variations."""

    @pytest.mark.parametrize(
        "args,desc",
        [
            ([], "no flags"),
            (["--limit", "5"], "with limit"),
            (["--offset", "0"], "with offset"),
        ],
    )
    def test_ent_list_variations(self, discover_test_data, args, desc):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("ent", "list", TEST_DATA["project_id"], *args)
        MATRIX.add(result)
        assert result.success, f"ent list {desc} failed: {result.stderr}"

    def test_ent_get(self, discover_test_data):
        if not TEST_DATA.get("project_id") or not TEST_DATA.get("entity_id"):
            pytest.skip("No entity available")
        result = run_cli("ent", "get", TEST_DATA["project_id"], TEST_DATA["entity_id"])
        MATRIX.add(result)
        assert result.success, f"ent get failed: {result.stderr}"

    def test_ent_get_with_field(self, discover_test_data):
        if not TEST_DATA.get("project_id") or not TEST_DATA.get("entity_id") or not TEST_DATA.get("property_slug"):
            pytest.skip("No entity or property available")
        result = run_cli(
            "ent",
            "get",
            TEST_DATA["project_id"],
            TEST_DATA["entity_id"],
            "--field",
            TEST_DATA["property_slug"],
        )
        MATRIX.add(result)
        # May succeed or fail if field not set - just check it doesn't crash
        assert result.exit_code in [0, 1], f"ent get --field crashed: {result.stderr}"

    def test_ent_create_empty(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("ent", "create", TEST_DATA["project_id"])
        if not result.success and _parent_required(result):
            parent_entity_id = _ensure_parent_entity_chain(TEST_DATA["project_id"])
            if not parent_entity_id:
                details = _get_project_details(TEST_DATA["project_id"])
                raise AssertionError(f"parent required but parent_project_id missing: {details.get('parent_property')}")
            result = run_cli("ent", "create", TEST_DATA["project_id"], "--parent", parent_entity_id)
        MATRIX.add(result)
        # Store created entity for cleanup
        if result.success:
            try:
                data = json.loads(result.stdout)
                TEST_DATA["created_entity_id"] = data.get("id")
            except (json.JSONDecodeError, KeyError):
                pass
        assert result.success, f"ent create failed: {result.stderr}"

    def test_ent_create_with_fields(self, discover_test_data):
        if not TEST_DATA.get("project_id") or not TEST_DATA.get("property_slug"):
            pytest.skip("No project or property available")
        fields = json.dumps({TEST_DATA["property_slug"]: "test value from smoke test"})
        result = run_cli("ent", "create", TEST_DATA["project_id"], "--fields", fields)
        if not result.success and _parent_required(result):
            parent_entity_id = _ensure_parent_entity_chain(TEST_DATA["project_id"])
            if not parent_entity_id:
                details = _get_project_details(TEST_DATA["project_id"])
                raise AssertionError(f"parent required but parent_project_id missing: {details.get('parent_property')}")
            result = run_cli(
                "ent",
                "create",
                TEST_DATA["project_id"],
                "--fields",
                fields,
                "--parent",
                parent_entity_id,
            )
        MATRIX.add(result)
        # May fail if property doesn't accept text - that's ok
        assert result.exit_code in [0, 1], f"ent create --fields crashed: {result.stderr}"

    def test_ent_create_with_invalid_json(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("ent", "create", TEST_DATA["project_id"], "--fields", "{invalid json}")
        MATRIX.add(result)
        # Should fail gracefully with error about JSON
        assert not result.success, "Invalid JSON should fail"
        # Check for JSON-related error in stdout or stderr
        output = result.stdout.lower() + result.stderr.lower()
        assert "json" in output or "invalid" in output or "error" in output

    def test_ent_set(self, discover_test_data):
        if not TEST_DATA.get("project_id") or not TEST_DATA.get("entity_id") or not TEST_DATA.get("property_slug"):
            pytest.skip("No entity or property available")
        result = run_cli(
            "ent",
            "set",
            TEST_DATA["project_id"],
            TEST_DATA["entity_id"],
            TEST_DATA["property_slug"],
            "smoke test value",
        )
        MATRIX.add(result)
        # May fail if property type doesn't match - that's ok
        assert result.exit_code in [0, 1], f"ent set crashed: {result.stderr}"

    def test_ent_recalc(self, discover_test_data):
        if not TEST_DATA.get("project_id") or not TEST_DATA.get("entity_id"):
            pytest.skip("No entity available")
        result = run_cli("ent", "recalc", TEST_DATA["project_id"], TEST_DATA["entity_id"])
        MATRIX.add(result)
        assert result.success, f"ent recalc failed: {result.stderr}"


# =============================================================================
# Properties Endpoint Tests
# =============================================================================


class TestPropsEndpoint:
    """Test all properties endpoint variations."""

    def test_props_list(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("props", "list", TEST_DATA["project_id"])
        MATRIX.add(result)
        assert result.success, f"props list failed: {result.stderr}"

    def test_props_get(self, discover_test_data):
        if not TEST_DATA.get("project_id") or not TEST_DATA.get("property_id"):
            pytest.skip("No property available")
        result = run_cli("props", "get", TEST_DATA["project_id"], TEST_DATA["property_id"])
        MATRIX.add(result)
        assert result.success, f"props get failed: {result.stderr}"

    def test_props_get_invalid_id(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("props", "get", TEST_DATA["project_id"], "invalid-prop-id-12345")
        MATRIX.add(result)
        # Should fail gracefully
        assert not result.success, "Getting invalid property ID should fail"


# =============================================================================
# Hub Endpoint Tests
# =============================================================================


class TestHubEndpoint:
    """Test all hub endpoint variations."""

    def test_hub_list(self, discover_test_data):
        result = run_cli("hub", "list")
        MATRIX.add(result)
        assert result.success, f"hub list failed: {result.stderr}"

    def test_hub_get(self, discover_test_data):
        if not TEST_DATA.get("hub_id"):
            pytest.skip("No hub available")
        result = run_cli("hub", "get", TEST_DATA["hub_id"])
        MATRIX.add(result)
        assert result.success, f"hub get failed: {result.stderr}"

    def test_hub_files(self, discover_test_data):
        if not TEST_DATA.get("hub_id"):
            pytest.skip("No hub available")
        result = run_cli("hub", "files", TEST_DATA["hub_id"])
        MATRIX.add(result)
        assert result.success, f"hub files failed: {result.stderr}"

    def test_hub_get_invalid_id(self, discover_test_data):
        result = run_cli("hub", "get", "invalid-hub-id-12345")
        MATRIX.add(result)
        # Should fail gracefully
        assert not result.success


# =============================================================================
# Export Endpoint Tests
# =============================================================================


class TestExportEndpoint:
    """Test export endpoint variations."""

    def test_export_csv_no_wait(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("export", TEST_DATA["project_id"], "--format", "csv", "--no-wait")
        MATRIX.add(result)
        assert result.exit_code in [0, 1], f"export --format csv --no-wait crashed: {result.stderr}"

    def test_export_xlsx_no_wait(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("export", TEST_DATA["project_id"], "--format", "xlsx", "--no-wait")
        MATRIX.add(result)
        assert result.exit_code in [0, 1], f"export --format xlsx --no-wait crashed: {result.stderr}"


# =============================================================================
# Agent Builder Endpoint Tests
# =============================================================================


class TestAgentBuilderEndpoint:
    """Test agent builder endpoint variations."""

    def test_agent_builder_create(self, discover_test_data):
        # agent_builder create takes a single prompt argument
        result = run_cli(
            "agent_builder",
            "create",
            "Create an agent to extract key info from documents for smoke testing",
        )
        MATRIX.add(result)
        assert result.success, f"agent_builder create failed: {result.stderr}"

    def test_agent_builder_status(self, discover_test_data):
        if not TEST_DATA.get("agent_request_id"):
            pytest.skip("No agent request_id available")
        result = run_cli("agent_builder", "status", TEST_DATA["agent_request_id"])
        MATRIX.add(result)
        assert result.success, f"agent_builder status failed: {result.stderr}"

    def test_agent_builder_followup(self, discover_test_data):
        if not TEST_DATA.get("agent_request_id"):
            pytest.skip("No agent request_id available")
        result = run_cli(
            "agent_builder",
            "followup",
            TEST_DATA["agent_request_id"],
            "Add a field for invoice number",
        )
        MATRIX.add(result)
        # May fail if plan not ready - that's ok
        assert result.exit_code in [0, 1], f"agent_builder followup crashed: {result.stderr}"


# =============================================================================
# Template Endpoint Tests
# =============================================================================


class TestTemplateEndpoint:
    """Test template endpoint variations."""

    def test_template_export(self, discover_test_data):
        if not TEST_DATA.get("project_id"):
            pytest.skip("No project available")
        result = run_cli("template", "export", TEST_DATA["project_id"])
        MATRIX.add(result)
        assert result.success, f"template export failed: {result.stderr}"


# =============================================================================
# Invite Endpoint Tests
# =============================================================================


class TestInviteEndpoint:
    """Test invite endpoint variations."""

    def test_invite_default_role(self, discover_test_data):
        # Use a fake email to avoid actually sending invites
        result = run_cli("invite", "smoketest-fake@v7labs.invalid")
        MATRIX.add(result)
        # May fail due to invalid email domain - that's ok
        assert result.exit_code in [0, 1], f"invite crashed: {result.stderr}"

    def test_invite_with_role(self, discover_test_data):
        result = run_cli("invite", "smoketest-fake@v7labs.invalid", "--role", "editor")
        MATRIX.add(result)
        assert result.exit_code in [0, 1], f"invite --role crashed: {result.stderr}"


# =============================================================================
# Global Flag Tests
# =============================================================================


class TestGlobalFlags:
    """Test global flags work with various commands."""

    def test_workspace_flag(self, discover_test_data):
        result = run_cli("--workspace", WORKSPACE_ID, "projects", "list", "--limit", "1")
        MATRIX.add(result)
        assert result.success, f"--workspace flag failed: {result.stderr}"

    def test_help_with_workspace(self, discover_test_data):
        result = run_cli("--workspace", "test-ws", "--help")
        MATRIX.add(result)
        assert result.success, f"--workspace --help failed: {result.stderr}"


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases that might break the CLI."""

    def test_empty_response_handling(self, discover_test_data):
        """Test that empty API responses don't crash."""
        result = run_cli("projects", "list", "--limit", "0")
        MATRIX.add(result)
        # May return empty or error - just shouldn't crash
        assert result.exit_code in [0, 1], f"Empty response crashed: {result.stderr}"

    def test_large_limit(self, discover_test_data):
        """Test large limit value."""
        result = run_cli("projects", "list", "--limit", "1000")
        MATRIX.add(result)
        assert result.success, f"Large limit failed: {result.stderr}"

    def test_unicode_in_input(self, discover_test_data):
        """Test unicode characters in input."""
        # agent_builder create takes a single prompt argument
        result = run_cli("agent_builder", "create", "Extract info from 日本語 documents with Ëxtract ïnfo")
        MATRIX.add(result)
        # Should handle unicode gracefully
        assert result.exit_code in [0, 1], f"Unicode input crashed: {result.stderr}"

    def test_special_chars_in_input(self, discover_test_data):
        """Test special characters in input."""
        # agent_builder create takes a single prompt argument
        result = run_cli(
            "agent_builder",
            "create",
            "Test & Project <with> 'special' \"chars\" to extract info",
        )
        MATRIX.add(result)
        assert result.exit_code in [0, 1], f"Special chars crashed: {result.stderr}"

    def test_very_long_input(self, discover_test_data):
        """Test very long input strings."""
        long_prompt = "Extract key information from documents. " * 50
        result = run_cli("agent_builder", "create", long_prompt)
        MATRIX.add(result)
        assert result.exit_code in [0, 1], f"Long input crashed: {result.stderr}"


# =============================================================================
# Print Summary at End
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def print_matrix_at_end(request):
    """Print the test matrix at the end of all tests."""
    yield
    MATRIX.print_summary()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
