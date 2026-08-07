# Real backend: what it actually does

Observed against `mock-saas.aishprabhat.demo.altostrat.com` on 2026-08-07 with a
personal access token. Written down because three of these differ from
`enterprise_services_openapi.json` or from the BRD, and each one cost a debug
cycle.

## Protocol

* **MCP over Streamable HTTP**, not the REST paths in the OpenAPI file. Those
  return `302` to a Google login page. Invoke with JSON-RPC `tools/call` against
  `/{service}/mcp/`.
* Auth: `Authorization: Bearer <token>`. The `X-MCP-Token` header and `?pat=`
  query parameter documented for the REST surface also 302.
* Responses are **prose**, except `list_tickets` and `get_leave_requests`, which
  return JSON as text. Errors are prose too and carry HTTP 200.

## Identity

The caller is derived from the token. Any call naming a different employee is
refused:

```
Error: Access denied. Authenticated context is restricted to EMP-246.
Cannot act on behalf of EMP-1002.
```

`employee_id` is a required parameter but must equal the token's employee.
Resolve it once with `get_current_employee_id` and cache it; do not read it from
configuration.

## Tool surface

| WorkWeek | ServiceImmediately |
| :--- | :--- |
| `get_current_employee_id()` | `list_tickets(employee_id)` |
| `get_employee_balances(employee_id)` | `create_ticket(requested_by, category, short_description, priority)` |
| `get_personal_info(employee_id)` | `add_ticket_comment(ticket_id, author, comment)` |
| `update_personal_info(employee_id, address, phone)` | `update_ticket_status(ticket_id, status)` |
| `request_time_off(employee_id, start_date, end_date, leave_type, days)` | |
| `get_leave_requests(employee_id)` | |
| `cancel_leave_request(employee_id, request_id)` | |

There is **no per-ticket read**. `get_ticket_details` is served by filtering the
caller's own `list_tickets`, which also keeps the tenant boundary on the service
side.

## What the backend enforces

* **Tenant isolation.** Verified.
* **Leave balance.** A 30-day request against a 15-day balance is refused:
  `Denied: Insufficient vacation balance. Requested 30.0 days, remaining 15.0`.

## What the backend does NOT enforce, and one place it contradicts the BRD

* **The ticket state machine is the inverse of `FR-4.3`.**

  | Transition | Backend | `BRD FR-4.3` / `SDD 5.1.3` |
  | :--- | :--- | :--- |
  | `New → Closed` | **accepted** | **must be rejected** |
  | `New → Resolved` | **rejected** — "Invalid status transition from New" | required, as the abandon path |

  This is not a gap to be papered over. `FR-4.3` names `New → Closed` as the
  transition to prevent, because closing an untouched ticket leaves no record of
  why it was abandoned — and the backend allows exactly that. The agent enforces
  the requirement on its own side and refuses the transition before calling out.

  The consequence is that the documented abandon path (`New → Resolved` with
  notes, then `Closed`) cannot be executed against this backend. **Open question
  for the service owner**: is the backend's table intentional, or does `FR-4.3`
  describe a rule the service was meant to implement and does not?

## Note on test isolation

The service holds real state. Unit tests must never reach it: set
`ELEVATE_FORCE_MOCK=1`, which `tests/conftest.py` does for the whole suite. One
run before that guard existed wrote a London address over the employee's
Singapore record and left four test tickets open. Both were restored — the
address rewritten, the tickets commented and closed — and the original ticket
`INC0000943` was untouched.
