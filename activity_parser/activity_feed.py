"""
Trims a parsed, filtered activity list down to a small "recent activity"
feed for one account — date, subject, and a type label — for surfacing
alongside a staleness verdict without dumping every raw record.

Usage:
    from activity_feed import build_activity_feed
    build_activity_feed(records)
"""

from parser import parse_last_modified_date

DEFAULT_LIMIT = 8

# Every logged record has SOME activity type in Salesforce (Task/Call/
# Meeting/Email), but this export format doesn't reliably expose which —
# the "Task" checkbox column has only ever been seen checked/unchecked,
# never carrying an actual subtype value (see
# salesforce_api_access_request.md, open question #2). The one type we CAN
# tell apart reliably is a real logged email (nested To/Subject/Body), so
# that's the only distinction drawn here rather than guessing at Call vs.
# Meeting vs. Task from data that doesn't say.
def _activity_type(record):
    comments = record.get("comments")
    return "Email" if comments and comments.get("email") else "Activity"


def build_activity_feed(records, limit=DEFAULT_LIMIT):
    """records: a filtered activity list for ONE account. Returns the most
    recent `limit` activities as [{"date": iso_date, "subject": str,
    "type": "Email" | "Activity"}, ...], newest first."""
    dated = []
    for r in records:
        dt = parse_last_modified_date(r.get("last_modified_date"))
        if dt is None:
            continue
        dated.append(
            {
                "date": dt.date().isoformat(),
                "subject": r.get("subject"),
                "type": _activity_type(r),
            }
        )
    dated.sort(key=lambda a: a["date"], reverse=True)
    return dated[:limit]
