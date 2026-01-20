"""
Core HTTP client for the V7 Go API.

Handles authentication, request/response, pagination, and error handling.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

from v7_cli.core.types import PaginatedResponse

# Configuration
DEFAULT_BASE_URL = "https://api.go.v7labs.com"
DEFAULT_TIMEOUT = 60

T = TypeVar("T")


class CLIError(Exception):
    """Base error class for CLI errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON output."""
        result: dict[str, Any] = {"error": self.message}
        if self.details:
            result["details"] = self.details
        return result


class APIError(CLIError):
    """API error with status code and message."""

    def __init__(self, message: str, status: int = 0, details: dict | None = None):
        super().__init__(message, details)
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON output."""
        result = super().to_dict()
        if self.status:
            result["status"] = self.status
        return result


class ValidationError(CLIError):
    """Validation error for local input/data issues (not API errors)."""


class APIClient:
    """
    Low-level HTTP client for the V7 Go API.

    Handles:
    - Authentication via API key
    - HTTP methods (GET, POST, PUT, DELETE)
    - Error handling and response parsing
    - Pagination for list endpoints
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        workspace_id: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the API client.

        Args:
            api_key: V7 Go API key (or V7_GO_API_KEY env var)
            base_url: API base URL (or V7_GO_BASE_API_URL / V7_GO_BASE_URL env var)
            workspace_id: Default workspace ID (or V7_GO_WORKSPACE_ID env var)
            timeout: Request timeout in seconds

        """
        self.api_key = api_key or os.environ.get("V7_GO_API_KEY")
        # Check V7_GO_BASE_API_URL first (for dev), then V7_GO_BASE_URL
        env_base_url = os.environ.get("V7_GO_BASE_API_URL") or os.environ.get("V7_GO_BASE_URL", DEFAULT_BASE_URL)
        self.base_url = (base_url or env_base_url).rstrip("/")
        self.workspace_id = workspace_id or os.environ.get("V7_GO_WORKSPACE_ID")
        self.timeout = timeout

    def _ensure_api_key(self) -> str:
        """Ensure API key is configured."""
        if not self.api_key:
            raise APIError("V7_GO_API_KEY environment variable not set")
        return self.api_key

    def _ensure_workspace_id(self, workspace_id: str | None = None) -> str:
        """Ensure workspace ID is available."""
        ws_id = workspace_id or self.workspace_id
        if not ws_id:
            raise APIError("Workspace ID required. Set V7_GO_WORKSPACE_ID env var or use --workspace flag")
        return ws_id

    def _build_url(self, path: str) -> str:
        """Build full URL from path."""
        if path.startswith("http"):
            return path
        return f"{self.base_url}{path}"

    def _make_request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., /api/workspaces/{id}/projects)
            data: Request body for POST/PUT
            timeout: Request timeout override

        Returns:
            Parsed JSON response

        Raises:
            APIError: On HTTP or parsing errors

        """
        api_key = self._ensure_api_key()

        url = self._build_url(path)
        headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = json.dumps(data).encode("utf-8") if data else None
        request_timeout = timeout or self.timeout

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=request_timeout) as response:
                response_data = response.read().decode("utf-8")
                if response_data:
                    return json.loads(response_data)
                return {"success": True}

        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
                error_data = json.loads(error_body)
                # Handle both {"error": "message"} and {"error": {"message": "..."}}
                error_field = error_data.get("error", {})
                if isinstance(error_field, str):
                    message = error_field
                elif isinstance(error_field, dict):
                    message = error_field.get("message", str(e))
                else:
                    message = str(e)
                raise APIError(message, status=e.code, details=error_data)
            except json.JSONDecodeError:
                raise APIError(str(e), status=e.code)

        except urllib.error.URLError as e:
            raise APIError(f"Connection error: {e.reason}")

        except TimeoutError:
            raise APIError(f"Request timed out after {request_timeout} seconds")

        except json.JSONDecodeError as e:
            raise APIError(f"Invalid JSON response: {e}")

    # =========================================================================
    # HTTP Methods
    # =========================================================================

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a GET request."""
        if params:
            # Filter out None values and URL-encode
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if filtered_params:
                query_string = urllib.parse.urlencode(filtered_params)
                separator = "&" if "?" in path else "?"
                path = f"{path}{separator}{query_string}"
        return self._make_request("GET", path)

    def post(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Make a POST request."""
        return self._make_request("POST", path, data)

    def put(self, path: str, data: dict | None = None) -> dict[str, Any]:
        """Make a PUT request."""
        return self._make_request("PUT", path, data)

    def delete(self, path: str) -> dict[str, Any]:
        """Make a DELETE request."""
        return self._make_request("DELETE", path)

    # =========================================================================
    # Workspace-scoped helpers
    # =========================================================================

    def workspace_path(self, workspace_id: str | None = None) -> str:
        """Get the workspace path prefix."""
        ws_id = self._ensure_workspace_id(workspace_id)
        return f"/api/workspaces/{ws_id}"

    def workspace_get(
        self,
        path: str,
        workspace_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request to a workspace-scoped endpoint."""
        ws_path = self.workspace_path(workspace_id)
        return self.get(f"{ws_path}{path}", params)

    def workspace_post(
        self,
        path: str,
        data: dict | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Make a POST request to a workspace-scoped endpoint."""
        ws_path = self.workspace_path(workspace_id)
        return self.post(f"{ws_path}{path}", data)

    def workspace_put(
        self,
        path: str,
        data: dict | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request to a workspace-scoped endpoint."""
        ws_path = self.workspace_path(workspace_id)
        return self.put(f"{ws_path}{path}", data)

    def workspace_delete(
        self,
        path: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request to a workspace-scoped endpoint."""
        ws_path = self.workspace_path(workspace_id)
        return self.delete(f"{ws_path}{path}")

    # =========================================================================
    # Pagination
    # =========================================================================

    def paginate(
        self,
        path: str,
        workspace_id: str | None = None,
        limit: int = 100,
        parser: Callable[[dict[str, Any]], T] | None = None,
    ) -> Iterator[T]:
        """
        Iterate through all pages of a paginated endpoint.

        Args:
            path: API path (relative to workspace)
            workspace_id: Workspace ID override
            limit: Items per page
            parser: Optional function to parse each item

        Yields:
            Items from all pages (parsed if parser provided)

        """
        ws_path = self.workspace_path(workspace_id)
        offset = 0

        while True:
            result = self.get(f"{ws_path}{path}", {"limit": limit, "offset": offset})

            data = result.get("data", [])
            for item in data:
                if parser:
                    yield parser(item)
                else:
                    yield item

            meta = result.get("metadata", {})
            total = meta.get("total_count", 0)
            offset += len(data)

            if offset >= total or not data:
                break

    def paginate_all(
        self,
        path: str,
        workspace_id: str | None = None,
        limit: int = 100,
        parser: Callable[[dict[str, Any]], T] | None = None,
    ) -> list[T]:
        """
        Fetch all items from a paginated endpoint.

        Args:
            path: API path (relative to workspace)
            workspace_id: Workspace ID override
            limit: Items per page
            parser: Optional function to parse each item

        Returns:
            List of all items

        """
        return list(self.paginate(path, workspace_id, limit, parser))

    def paginate_response(
        self,
        path: str,
        workspace_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        parser: Callable[[dict[str, Any]], T] | None = None,
    ) -> PaginatedResponse[T]:
        """
        Fetch a single page and return a PaginatedResponse.

        Args:
            path: API path (relative to workspace)
            workspace_id: Workspace ID override
            limit: Items per page
            offset: Starting offset
            parser: Optional function to parse each item

        Returns:
            PaginatedResponse with data and metadata

        """
        ws_path = self.workspace_path(workspace_id)
        result = self.get(f"{ws_path}{path}", {"limit": limit, "offset": offset})

        data = result.get("data", [])
        if parser:
            data = [parser(item) for item in data]

        meta = result.get("metadata", {})
        return PaginatedResponse(
            data=data,
            total_count=meta.get("total_count", len(data)),
            offset=offset,
            limit=limit,
        )
