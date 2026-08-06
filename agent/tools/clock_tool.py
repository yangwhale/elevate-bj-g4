"""Current date, so relative dates resolve to the right year.

Asked to book "the last week of November", the agent produced 2024-11-25.
The model has no reliable notion of today, and a leave request written into
the wrong year is a silent data error: the API accepts it, the balance is
deducted, and nobody notices until the employee does not turn up.
"""

import datetime
from typing import Any


def get_today() -> dict[str, Any]:
    """Returns today's date. Call this before resolving any relative date.

    Use it for phrases such as 'next Monday', 'the last week of November',
    'tomorrow' or 'in three weeks'. Never assume the current year.
    """
    now = datetime.datetime.now(datetime.UTC)
    return {
        "status": "success",
        "today": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "year": now.year,
        "note": "All dates sent to WorkWeek must be absolute, formatted YYYY-MM-DD.",
    }
