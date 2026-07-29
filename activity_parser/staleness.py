"""
Flags whether an account looks "stalled" — quiet for longer than the team's
real outreach cadence — from a parsed, filtered, chronologically sorted
activity list (see parser.py).

Usage:
    python staleness.py mckee.mhtml
    python staleness.py noom.mhtml --account-name Noom
"""

import argparse
import statistics
from datetime import date, datetime

from parser import extract_html_from_mhtml, filter_and_sort_activities, parse_activities, parse_last_modified_date

# Need at least this many distinct days of activity to call this an
# established relationship. Below this, one or two touches don't tell you
# anything about a rhythm, so status becomes "new" or "never_engaged" (see
# NEW_LEAD_GRACE_DAYS) rather than guessing at one. This is purely a count
# threshold -- it's about whether real back-and-forth happened at all, not
# about timing, so it stays independent of the flat day thresholds below.
MIN_ENGAGEMENT_DAYS = 3

# Flat day thresholds for an established relationship (3+ real touches) --
# NOT relative to that account's own historical rhythm. Explicit choice,
# not an oversight: relative thresholds let a naturally slow-cadence
# account hide behind its own history, but the real BDS standard is a flat
# company-wide cadence (BDS_Best_Practices: touch every ~48 hours, 5-7
# touches over a 2-3 week cycle before recycling) -- "it's been a couple
# weeks" is a real problem regardless of how that specific account has
# historically been treated.
COOLING_OFF_DAYS = 14
STALLED_DAYS = 21

# Below MIN_ENGAGEMENT_DAYS there's no established relationship yet, but
# that bucket was hiding two very different accounts under one label: one
# just added with a single recent touch (nothing wrong, just early), and
# one touched once or twice and never followed up on (a real, actionable
# gap -- but a different one than "went quiet," since there was never a
# relationship here to re-engage). 7 days -- one BDS touch cycle -- is the
# line between them.
NEW_LEAD_GRACE_DAYS = 7


def _engagement_days(records):
    """Collapse activity timestamps down to one entry per calendar day.

    Salesforce exports often log several activities within seconds/minutes
    of each other (an email plus its auto-logged send confirmation, bot
    logging, etc.). Left in, those near-duplicate timestamps would crush a
    median gap toward ~0-1 days. Deduping to distinct days keeps
    typical_gap_days meaningful for display and revival-precedent matching
    even though it no longer drives the status itself (see COOLING_OFF_DAYS
    / STALLED_DAYS above).
    """
    dates = (parse_last_modified_date(r.get("last_modified_date")) for r in records)
    return sorted({d.date() for d in dates if d is not None})


def assess_staleness(records, as_of=None):
    """Compare an account's current silence to the team's flat outreach
    cadence (COOLING_OFF_DAYS / STALLED_DAYS) -- not to that account's own
    historical rhythm.

    records: a filtered, chronologically-sorted activity list (the output of
        parser.filter_and_sort_activities), or any list of activity dicts
        with a 'last_modified_date' field — order doesn't actually matter
        here since we sort internally.
    as_of: the date to treat as "today" (defaults to today's date). Accepts
        a date or datetime.

    Returns a dict with:
        typical_gap_days      - median days between engagement days, or None
                                 if there isn't enough history. Descriptive
                                 only now (shown to a rep, used to rank
                                 revival-library precedent matches) -- does
                                 NOT drive status; see module docstring.
        days_since_last_touch - whole days since the most recent activity
        last_touch_date       - ISO date of the most recent activity, or None
        threshold_days         - the flat silence threshold that trips
                                 "stalled" (STALLED_DAYS), or None
        cooling_threshold_days - the flat silence threshold that trips
                                 "cooling_off" (COOLING_OFF_DAYS), or None
        status                 - "stalled" | "cooling_off" | "on_pace" |
                                 "never_engaged" | "new" | "no_activity"
    """
    if as_of is None:
        as_of = date.today()
    elif isinstance(as_of, datetime):
        as_of = as_of.date()

    engagement_days = _engagement_days(records)
    if not engagement_days:
        return {
            "typical_gap_days": None,
            "days_since_last_touch": None,
            "last_touch_date": None,
            "threshold_days": None,
            "cooling_threshold_days": None,
            "status": "no_activity",
        }

    last_touch = engagement_days[-1]
    days_since_last_touch = (as_of - last_touch).days
    typical_gap_days = None

    if len(engagement_days) < MIN_ENGAGEMENT_DAYS:
        # No established relationship yet -- "new" if there's still time
        # left in one normal touch cycle, "never_engaged" past that. No
        # further escalation past this: a lead touched once, years ago,
        # just stays "never_engaged" rather than a separate tier, so
        # sorting (see tracker._urgency_sort_key) is what keeps truly
        # ancient ones from crowding out ones that just crossed the line.
        status = "new" if days_since_last_touch <= NEW_LEAD_GRACE_DAYS else "never_engaged"
    else:
        gaps = [(engagement_days[i + 1] - engagement_days[i]).days for i in range(len(engagement_days) - 1)]
        typical_gap_days = statistics.median(gaps)

        if days_since_last_touch > STALLED_DAYS:
            status = "stalled"
        elif days_since_last_touch > COOLING_OFF_DAYS:
            status = "cooling_off"
        else:
            status = "on_pace"

    return {
        "typical_gap_days": typical_gap_days,
        "days_since_last_touch": days_since_last_touch,
        "last_touch_date": last_touch.isoformat(),
        "threshold_days": STALLED_DAYS,
        "cooling_threshold_days": COOLING_OFF_DAYS,
        "status": status,
    }


def format_staleness_summary(assessment, account_name=None):
    label = f"{account_name}: " if account_name else ""

    if assessment["status"] == "no_activity":
        return f"{label}no dated activity found."

    if assessment["status"] == "new":
        return (
            f"{label}too new to establish a normal rhythm yet "
            f"(last touch {assessment['days_since_last_touch']} days ago) — NEW."
        )

    if assessment["status"] == "never_engaged":
        return (
            f"{label}no real conversation established yet "
            f"(last touch {assessment['days_since_last_touch']} days ago) — NEVER ENGAGED."
        )

    flag = {"stalled": "STALLED", "cooling_off": "COOLING OFF"}.get(assessment["status"], "ON PACE")
    gap_note = f"typical gap {assessment['typical_gap_days']:.1f} days | " if assessment["typical_gap_days"] else ""
    return (
        f"{label}{gap_note}last touch {assessment['days_since_last_touch']} days ago "
        f"(threshold {assessment['threshold_days']} days) | {flag}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mhtml_path", help="Path to the Salesforce .mhtml export")
    parser.add_argument("--account-name", help="Label to print alongside the summary")
    args = parser.parse_args()

    html = extract_html_from_mhtml(args.mhtml_path)
    records = filter_and_sort_activities(parse_activities(html))
    assessment = assess_staleness(records)
    print(format_staleness_summary(assessment, args.account_name))


if __name__ == "__main__":
    main()
