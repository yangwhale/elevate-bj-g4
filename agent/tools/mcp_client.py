"""Client for the WorkWeek and ServiceImmediately MCP services.

The enterprise backends speak MCP over Streamable HTTP, not the REST paths in
`enterprise_services_openapi.json` — those return 302 to a login page. Tools
are invoked with JSON-RPC `tools/call`.

Two properties of the real service differ from the mock the project was built
against, and both matter:

1. **Identity comes from the token, not from a parameter.** The service resolves
   the caller from the bearer token and rejects any call naming someone else:
   "Access denied. Authenticated context is restricted to EMP-246." Passing an
   employee_id is still required by the schema, but it must match.
2. **Every response is prose, not JSON.** `get_employee_balances` returns a
   formatted block of text. Callers parse what they need and pass the rest to
   the model as-is.

With no token configured the tools fall back to the in-process mock, and say so
in the `source` field of the result. A silent fallback would make a broken
credential look like a working backend.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

WORKWEEK = "work-week"
ITSM = "service-immediately"

_TOKEN_FILE = Path.home() / ".config/elevate/mcp-token"
_TIMEOUT = 45


def base_url() -> str:
    return os.environ.get(
        "MCP_BASE_URL", "https://mock-saas.aishprabhat.demo.altostrat.com"
    ).rstrip("/")


def token() -> str:
    tok = os.environ.get("MCP_TOKEN", "").strip()
    if tok and tok != "mcp_your_token_here":
        return tok
    if _TOKEN_FILE.is_file():
        return _TOKEN_FILE.read_text().strip()
    return ""


def enabled() -> bool:
    """True when a usable token is configured and the mock is not forced.

    ELEVATE_FORCE_MOCK exists so the unit tests exercise the in-process
    backends deterministically. Without it, having a token on the machine
    silently rewires every test to hit the network, which is both slow and
    a different system under test.
    """
    if os.environ.get("ELEVATE_FORCE_MOCK", "").strip() not in ("", "0", "false"):
        return False
    return bool(token())


class RemoteError(RuntimeError):
    """The service was reached and refused, or could not be reached."""


def _parse(raw: str) -> dict:
    """Accept both a plain JSON body and an SSE frame."""
    if "data:" in raw and not raw.lstrip().startswith("{"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                raw = line[5:]
                break
    return json.loads(raw)


def call(service: str, tool: str, arguments: dict[str, Any] | None = None) -> str:
    """Invoke a tool and return its text content.

    Raises RemoteError on transport failure or a JSON-RPC error. Application
    errors — "Employee X not found", "Access denied" — come back as ordinary
    text, because that is how the service reports them, and the caller decides
    what to do with them.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments or {}},
    }
    request = urllib.request.Request(
        f"{base_url()}/{service}/mcp/",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            body = response.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RemoteError(f"{type(exc).__name__}: {exc}") from exc

    parsed = _parse(body)
    if "error" in parsed:
        raise RemoteError(json.dumps(parsed["error"])[:300])
    content = parsed.get("result", {}).get("content", [])
    return "\n".join(part.get("text", "") for part in content).strip()


_IDENTITY: dict[str, str] = {}


def whoami() -> str:
    """The employee this token authenticates as, resolved once and cached.

    The real service derives the caller from the token and refuses any call
    naming someone else, so the session's notion of "me" has to come from here
    rather than from configuration. DEFAULT_EMPLOYEE_ID is EMP-1002 and the
    token authenticates as EMP-246; using the former produced 403 on every
    call.
    """
    cached = _IDENTITY.get(base_url())
    if cached:
        return cached
    resolved = call(WORKWEEK, "get_current_employee_id").strip()
    _IDENTITY[base_url()] = resolved
    return resolved


def whoami_or(default: str) -> str:
    """whoami(), falling back to `default` if the service cannot be reached."""
    try:
        return whoami()
    except RemoteError:
        return default


def is_denial(text: str) -> bool:
    lowered = text.lower()
    return "access denied" in lowered or "not authorized" in lowered


def is_missing(text: str) -> bool:
    return "not found" in text.lower()
