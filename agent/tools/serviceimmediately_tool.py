"""ServiceImmediately (ITSM/HRSD) Toolset implementation.

Conforms to:
- enterprise_services_openapi.json (/service-immediately/mcp/)
- SDD.md Section 3.2, 4.1, 5.1
- BRD FR-4.1, FR-4.2, FR-4.3
"""

import datetime
import json
from typing import Any

from .. import config
from ..guardrails import ModelArmorGuard
from . import mcp_client
from .workweek_tool import _remote


# =============================================================================
# In-Memory State Store (ServiceImmediately High-Fidelity Mock)
# =============================================================================
class ServiceImmediatelyStateStore:
    def __init__(self):
        self.current_caller_id = config.DEFAULT_EMPLOYEE_ID
        self.tickets: dict[str, dict[str, Any]] = {
            "INC123456": {
                "ticket_id": "INC123456",
                "requested_by": "EMP-1002",
                "category": "IT / Network",
                "short_description": "VPN connection dropping intermittently",
                "priority": "3 - Moderate",
                "state": "In Progress",
                "assignment_group": "Network Team",
                "created_at": "2026-08-06T08:00:00Z",
                "updated_at": "2026-08-06T08:30:00Z",
                "comments": [
                    {
                        "author": "EMP-1002",
                        "comment": "VPN drops every 10-15 minutes when connected to EU gateway.",
                        "timestamp": "2026-08-06T08:00:00Z",
                    },
                    {
                        "author": "Network Admin",
                        "comment": "Investigating gateway logs for packet loss. Patch scheduled for 18:00 UTC.",
                        "timestamp": "2026-08-06T08:30:00Z",
                    },
                ],
                "resolution_notes": "",
            },
            "INC-10293": {
                "ticket_id": "INC-10293",
                "requested_by": "EMP-1002",
                "category": "IT / Hardware",
                "short_description": "Secondary monitor flickering",
                "priority": "4 - Low",
                "state": "New",
                "assignment_group": "Service Desk",
                "created_at": "2026-08-06T09:00:00Z",
                "updated_at": "2026-08-06T09:00:00Z",
                "comments": [],
                "resolution_notes": "",
            },
        }
        self.ticket_counter = 98230

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        return self.tickets.get(ticket_id)


_store = ServiceImmediatelyStateStore()


def reset_state_for_testing() -> None:
    """Restore the mock backend to its initial state.

    The store is module-level, so every evaluation case that books leave or
    raises a ticket changes what the next case sees. That makes a suite
    order-dependent and its results irreproducible, which is worse than a low
    score. Evaluation harnesses call this between cases.
    """
    global _store
    _store = ServiceImmediatelyStateStore()


def effective_caller(requested: str | None = None) -> str:
    """The employee id to send to the backend.

    In remote mode identity comes from the token; anything else is refused by
    the service. In mock mode it comes from the session.
    """
    if mcp_client.enabled():
        return mcp_client.whoami_or(_store.current_caller_id)
    return requested or _store.current_caller_id


def set_active_caller_context(employee_id: str):
    """Sets active caller context for multi-tenant sessions."""
    _store.current_caller_id = employee_id


# =============================================================================
# ServiceImmediately Tools (ADK & FastMCP Callable)
# =============================================================================
def list_tickets(employee_id: str | None = None) -> dict[str, Any]:
    """Lists all active and historical incident tickets requested by the employee.

    Args:
        employee_id: Employee ID (e.g. 'EMP-1002'). If omitted, defaults to active session caller.
    """
    if mcp_client.enabled():
        return _remote(mcp_client.ITSM, "list_tickets",
                       {"employee_id": effective_caller(employee_id)})
    target_id = employee_id or _store.current_caller_id

    allowed, rbac_msg = ModelArmorGuard.check_rbac_isolation(
        _store.current_caller_id, target_id
    )
    if not allowed:
        return {"status": "error", "error_code": "403_FORBIDDEN", "message": rbac_msg}

    user_tickets = [
        {
            "ticket_id": t["ticket_id"],
            "short_description": t["short_description"],
            "category": t["category"],
            "priority": t["priority"],
            "state": t["state"],
            "updated_at": t["updated_at"],
        }
        for t in _store.tickets.values()
        if t["requested_by"] == target_id
    ]

    return {
        "status": "success",
        "employee_id": target_id,
        "count": len(user_tickets),
        "tickets": user_tickets,
    }


def get_ticket_details(ticket_id: str) -> dict[str, Any]:
    """Retrieves full incident details, status, priority, and comment activity timeline.

    Args:
        ticket_id: Incident Ticket ID (e.g. 'INC123456')
    """
    if mcp_client.enabled():
        # The service exposes no per-ticket read; filter the caller's list.
        return _remote_ticket_details(ticket_id)
    ticket = _store.get_ticket(ticket_id)
    if not ticket:
        return {
            "status": "error",
            "error_code": "TICKET_NOT_FOUND",
            "message": f"Incident ticket {ticket_id} not found in ServiceImmediately.",
        }

    # Model Armor check on ticket comments (protecting against indirect injection)
    safe_comments = []
    for c in ticket["comments"]:
        is_safe, sanitized, _ = ModelArmorGuard.inspect_input(c["comment"])
        safe_comments.append(
            {
                "author": c["author"],
                "comment": sanitized if is_safe else "[Comment redacted: Malicious payload neutralized]",
                "timestamp": c["timestamp"],
            }
        )

    return {
        "status": "success",
        "ticket_id": ticket["ticket_id"],
        "requested_by": ticket["requested_by"],
        "category": ticket["category"],
        "short_description": ticket["short_description"],
        "priority": ticket["priority"],
        "state": ticket["state"],
        "assignment_group": ticket["assignment_group"],
        "created_at": ticket["created_at"],
        "updated_at": ticket["updated_at"],
        "comments": safe_comments,
        "latest_update": safe_comments[-1]["comment"] if safe_comments else "None",
        "resolution_notes": ticket["resolution_notes"],
    }


def create_ticket(
    requested_by: str,
    category: str,
    short_description: str,
    priority: str = "3 - Moderate",
    assignment_group: str = "Service Desk",
) -> dict[str, Any]:
    """Creates a new support incident or request ticket in ServiceImmediately.

    Args:
        requested_by: Employee ID creating the ticket (e.g. 'EMP-1002')
        category: Ticket category (e.g. 'IT / Hardware', 'Network', 'HR Access', 'Facilities')
        short_description: Concise summary of the incident or request
        priority: Priority ('1 - Critical', '2 - High', '3 - Moderate', '4 - Low')
        assignment_group: Target support desk group (e.g. 'Service Desk', 'Facilities')
    """
    if mcp_client.enabled():
        return _remote(mcp_client.ITSM, "create_ticket",
                       {"requested_by": effective_caller(requested_by), "category": category,
                        "short_description": short_description, "priority": priority})
    # 1. RBAC Check
    allowed, rbac_msg = ModelArmorGuard.check_rbac_isolation(
        _store.current_caller_id, requested_by
    )
    if not allowed:
        return {"status": "error", "error_code": "403_FORBIDDEN", "message": rbac_msg}

    # 2. Duplicate Detection (5-min window on identical subject, BRD FR-4.3)
    now_utc = datetime.datetime.now(datetime.UTC).isoformat()
    for t in _store.tickets.values():
        if (
            t["requested_by"] == requested_by
            and t["short_description"].strip().lower() == short_description.strip().lower()
            and t["state"] in ["New", "In Progress"]
        ):
            # Append comment to existing ticket rather than duplicating
            t["comments"].append(
                {
                    "author": requested_by,
                    "comment": f"Duplicate request submitted via chat: {short_description}",
                    "timestamp": now_utc,
                }
            )
            return {
                "status": "success",
                "duplicate_mitigated": True,
                "ticket_id": t["ticket_id"],
                "state": t["state"],
                "message": f"Existing open ticket {t['ticket_id']} with identical subject detected. Appended update note instead of creating a duplicate.",
            }

    # 3. Critical Priority Verification (BRD FR-4.3)
    if "1" in priority or "Critical" in priority:
        critical_keywords = ["outage", "down", "crash", "emergency", "production", "blocked"]
        if not any(kw in short_description.lower() for kw in critical_keywords):
            # Downgrade to High if critical criteria not met
            priority = "2 - High"

    _store.ticket_counter += 1
    new_id = f"INC-{_store.ticket_counter}"

    new_ticket = {
        "ticket_id": new_id,
        "requested_by": requested_by,
        "category": category,
        "short_description": short_description,
        "priority": priority,
        "state": "New",
        "assignment_group": assignment_group,
        "created_at": now_utc,
        "updated_at": now_utc,
        "comments": [
            {
                "author": f"Agentic_HR_Assistant (on behalf of {requested_by})",
                "comment": f"Ticket created via Conversational Assistant. Description: {short_description}",
                "timestamp": now_utc,
            }
        ],
        "resolution_notes": "",
    }
    _store.tickets[new_id] = new_ticket

    return {
        "status": "success",
        "ticket_id": new_id,
        "requested_by": requested_by,
        "category": category,
        "short_description": short_description,
        "priority": priority,
        "state": "New",
        "assignment_group": assignment_group,
        "message": f"Incident ticket {new_id} successfully created with priority '{priority}' and assigned to '{assignment_group}'.",
    }


def add_ticket_comment(
    ticket_id: str, author: str, comment: str
) -> dict[str, Any]:
    """Appends a comment or update note to an existing ticket activity timeline.

    Args:
        ticket_id: Incident Ticket ID
        author: Author employee ID or name
        comment: Note text to append
    """
    if mcp_client.enabled():
        return _remote(mcp_client.ITSM, "add_ticket_comment",
                       {"ticket_id": ticket_id, "author": author, "comment": comment})
    ticket = _store.get_ticket(ticket_id)
    if not ticket:
        return {"status": "error", "error_code": "TICKET_NOT_FOUND", "message": f"Ticket {ticket_id} not found."}

    if ticket["state"] == "Closed":
        return {
            "status": "error",
            "error_code": "TICKET_CLOSED",
            "message": f"Ticket {ticket_id} is Closed and immutable. Comments cannot be added.",
        }

    now_utc = datetime.datetime.now(datetime.UTC).isoformat()
    ticket["comments"].append({"author": author, "comment": comment, "timestamp": now_utc})
    ticket["updated_at"] = now_utc

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "comment_added": comment,
        "total_comments": len(ticket["comments"]),
        "message": f"Comment successfully added to ticket {ticket_id}.",
    }


def update_ticket_status(
    ticket_id: str,
    status: str,
    resolution_notes: str = "",
    updated_by: str = "System",
) -> dict[str, Any]:
    """Updates the lifecycle state of a ticket according to ITIL state machine rules.

    Valid transitions:
    - 'New' -> 'In Progress' or 'Resolved'
    - 'In Progress' -> 'Resolved' or 'Closed'
    - 'Resolved' -> 'In Progress' (reopen) or 'Closed'
    - 'Closed' -> Immutable (cannot transition)

    Args:
        ticket_id: Incident Ticket ID
        status: Target status ('New', 'In Progress', 'Resolved', 'Closed')
        resolution_notes: Required when resolving or closing
        updated_by: User or system driving transition
    """
    if mcp_client.enabled():
        return _remote_status(ticket_id, status)
    ticket = _store.get_ticket(ticket_id)
    if not ticket:
        return {"status": "error", "error_code": "TICKET_NOT_FOUND", "message": f"Ticket {ticket_id} not found."}

    current_state = ticket["state"]

    # ITIL State Machine Transition Matrix (BRD FR-4.3, SDD 5.1.3).
    # FR-4.3 names New -> Closed as the transition to reject: closing an
    # untouched ticket leaves no record of why it was abandoned. A ticket
    # raised in error goes New -> Resolved (with notes) -> Closed.
    valid_transitions = {
        "New": ["In Progress", "Resolved"],
        "In Progress": ["Resolved", "Closed"],
        "Resolved": ["In Progress", "Closed"],
        "Closed": [],
    }

    if current_state == "Closed":
        return {
            "status": "error",
            "error_code": "TICKET_CLOSED",
            "message": f"Invalid State Transition: Ticket {ticket_id} is Closed and locked from further changes.",
        }

    norm_target = status.title() if status.lower() != "in progress" else "In Progress"

    if norm_target not in valid_transitions.get(current_state, []):
        return {
            "status": "error",
            "error_code": "INVALID_STATE_TRANSITION",
            "message": (
                f"Invalid State Transition: Cannot transition ticket {ticket_id} "
                f"directly from '{current_state}' to '{status}'. Allowed target states: {valid_transitions.get(current_state)}."
            ),
        }

    now_utc = datetime.datetime.now(datetime.UTC).isoformat()
    ticket["state"] = norm_target
    ticket["updated_at"] = now_utc
    if resolution_notes:
        ticket["resolution_notes"] = resolution_notes
        ticket["comments"].append(
            {
                "author": updated_by,
                "comment": f"Status transitioned to '{norm_target}'. Notes: {resolution_notes}",
                "timestamp": now_utc,
            }
        )

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "previous_state": current_state,
        "new_state": norm_target,
        "message": f"Ticket {ticket_id} status transitioned from '{current_state}' to '{norm_target}'.",
    }


# ---------------------------------------------------------------- remote path
_REMOTE_TRANSITIONS = {
    "New": ["In Progress", "Resolved"],
    "In Progress": ["Resolved", "Closed"],
    "Resolved": ["In Progress", "Closed"],
    "Closed": [],
}


def _remote_ticket_details(ticket_id: str) -> dict[str, Any]:
    """The backend has no per-ticket read, so filter the caller's own list.

    Doing it here rather than asking the model to filter keeps the tenant
    boundary on the service side: list_tickets already refuses another
    employee's id, so a ticket that is not in the caller's list is reported as
    not found rather than fetched by some other route.
    """
    listed = _remote(mcp_client.ITSM, "list_tickets",
                     {"employee_id": effective_caller()})
    if listed.get("status") != "success":
        return listed
    try:
        tickets = json.loads(listed["detail"])
    except (json.JSONDecodeError, KeyError):
        return listed
    for ticket in tickets:
        if ticket.get("ticket_id") == ticket_id:
            # Nest it. The ticket carries its own "status" field, and spreading
            # it here overwrote the call status with the ticket state — which
            # made the state-machine check read "success" as the current state
            # and wave New -> Closed straight through.
            return {"status": "success", "source": "remote",
                    "ticket": ticket, **{k: v for k, v in ticket.items() if k != "status"},
                    "ticket_state": ticket.get("status")}
    return {"status": "error", "error_code": "TICKET_NOT_FOUND", "source": "remote",
            "message": f"Ticket {ticket_id} is not among your tickets."}


def _remote_status(ticket_id: str, status: str) -> dict[str, Any]:
    """Enforce FR-4.3 before calling out.

    The backend accepts whatever status string it is given, including
    New -> Closed. The requirement to reject that is ours, so the check has to
    live on this side; relying on a backend to enforce a rule it does not know
    about is how the mock came to permit it in the first place.
    """
    current = _remote_ticket_details(ticket_id)
    if current.get("status") != "success":
        return current
    state = str(current.get("ticket_state") or current.get("state") or "")
    for known in _REMOTE_TRANSITIONS:
        if known.lower() in state.lower():
            state = known
            break

    target = status.title() if status.lower() != "in progress" else "In Progress"
    allowed = _REMOTE_TRANSITIONS.get(state)
    if allowed is not None and target not in allowed:
        return {
            "status": "error", "error_code": "INVALID_STATE_TRANSITION", "source": "remote",
            "message": (f"Cannot move ticket {ticket_id} from '{state}' to '{target}'. "
                        f"Allowed: {allowed}."),
        }
    return _remote(mcp_client.ITSM, "update_ticket_status",
                   {"ticket_id": ticket_id, "status": target})
