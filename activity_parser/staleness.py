"""
Flags whether an account looks "stalled" — quiet for meaningfully longer than
its own normal outreach rhythm — from a parsed, filtered, chronologically
sorted activity list (see parser.py).

Usage:
    python staleness.py mckee.mhtml
    python staleness.py noom.mhtml --account-name Noom
"""

import argparse
import statistics
from datetime import date, datetime

from parser import extract_html_from_mhtml, filter_and_sort_activities, parse_activities, parse_last_modified_date

# Need at least this many distinct days of activity to trust a median gap.
# Below this, one or two touches don't tell you anything about "normal"
# rhythm, so we report "insufficient_history" rather than guess.
MIN_ENGAGEMENT_DAYS = 3

# How many multiples of the account's own typical gap the current silence
# has to exceed before we call it "stalled" rather than normal variance.
# Sales cadences wobble around their median (weekends, someone's on PTO, a
# prospect is slow to reply) so 2x alone is too trigger-happy — a single
# skipped week on a weekly cadence would already read as "stalled." 3x means
# the account has gone quiet for a full extra cycle beyond its own rhythm,
# which is a much stronger, less noisy signal that something changed.
STALLED_MULTIPLIER = 3

# Below the stalled threshold but still running longer than usual: a softer,
# earlier signal than "stalled" so an account doesn't jump straight from
# "on pace" to "needs attention" with no warning in between. 1.5x is closer
# to STALLED_MULTIPLIER than to on-pace on purpose — this is meant to flag
# "starting to drift," not "any silence at all."
COOLING_MULTIPLIER = 1.5

# Flat backstop, independent of the account's own rhythm: once total silence
# crosses this many days, flag it regardless of how slow-paced the account
# normally is. The multiplier-based thresholds above are all *relative* to
# the account's own typical gap, so a naturally slow-cadence account (e.g.
# one historically touched once a year) could go silent forever and never
# trip "stalled." This catches that case, and also doubles as a distinct
# "gone quiet a long time ago" signal within the stalled population, since
# "just went quiet last month" and "silent for two years" both landing in
# the same bucket isn't a useful distinction for a rep to act on.
DORMANT_DAYS = 365


def _engagement_days(records):
    """Collapse activity timestamps down to one entry per calendar day.

    Salesforce exports often log several activities within seconds/minutes
    of each other (an email plus its auto-logged send confirmation, bot
    logging, etc.). Left in, those near-duplicate timestamps crush the
    median gap toward ~0-1 days and make almost any silence look "stalled."
    Deduping to distinct days gives a median that actually reflects how
    often the rep engages, not how many records got logged per engagement.
    """
    dates = (parse_last_modified_date(r.get("last_modified_date")) for r in records)
    return sorted({d.date() for d in dates if d is not None})


def assess_staleness(records, as_of=None):
    """Compare an account's current silence to its own historical rhythm.

    records: a filtered, chronologically-sorted activity list (the output of
        parser.filter_and_sort_activities), or any list of activity dicts
        with a 'last_modified_date' field — order doesn't actually matter
        here since we sort internally.
    as_of: the date to treat as "today" (defaults to today's date). Accepts
        a date or datetime.

    Returns a dict with:
        typical_gap_days      - median days between engagement days, or None
                                 if there isn't enough history
        days_since_last_touch - whole days since the most recent activity
        last_touch_date       - ISO date of the most recent activity, or None
        threshold_days         - the silence threshold that trips "stalled", or None
        cooling_threshold_days - the (lower) silence threshold that trips
                                 "cooling_off", or None
        status                 - "dormant" | "stalled" | "cooling_off" | "on_pace" |
                                 "insufficient_history" | "no_activity"
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

    if len(engagement_days) < MIN_ENGAGEMENT_DAYS:
        # Not enough history to trust a median gap, but the flat DORMANT_DAYS
        # backstop doesn't depend on one — a sparsely-logged account that's
        # been silent over a year is still worth flagging as dormant rather
        # than left in an unresolved "insufficient_history" limbo forever.
        status = "dormant" if days_since_last_touch > DORMANT_DAYS else "insufficient_history"
        return {
            "typical_gap_days": None,
            "days_since_last_touch": days_since_last_touch,
            "last_touch_date": last_touch.isoformat(),
            "threshold_days": None,
            "cooling_threshold_days": None,
            "status": status,
        }

    gaps = [(engagement_days[i + 1] - engagement_days[i]).days for i in range(len(engagement_days) - 1)]
    typical_gap_days = statistics.median(gaps)
    threshold_days = typical_gap_days * STALLED_MULTIPLIER
    cooling_threshold_days = typical_gap_days * COOLING_MULTIPLIER

    if days_since_last_touch > DORMANT_DAYS:
        status = "dormant"
    elif days_since_last_touch > threshold_days:
        status = "stalled"
    elif days_since_last_touch > cooling_threshold_days:
        status = "cooling_off"
    else:
        status = "on_pace"

    return {
        "typical_gap_days": typical_gap_days,
        "days_since_last_touch": days_since_last_touch,
        "last_touch_date": last_touch.isoformat(),
        "threshold_days": threshold_days,
        "cooling_threshold_days": cooling_threshold_days,
        "status": status,
    }


def format_staleness_summary(assessment, account_name=None):
    label = f"{account_name}: " if account_name else ""

    if assessment["status"] == "no_activity":
        return f"{label}no dated activity found."

    if assessment["status"] == "insufficient_history":
        return (
            f"{label}not enough history to establish a normal rhythm "
            f"(last touch {assessment['days_since_last_touch']} days ago)."
        )

    if assessment["status"] == "dormant" and assessment["typical_gap_days"] is None:
        return (
            f"{label}not enough history to establish a normal rhythm, but silent for "
            f"{assessment['days_since_last_touch']} days ({DORMANT_DAYS}+ day backstop) — DORMANT."
        )

    flag = {"stalled": "STALLED", "cooling_off": "COOLING OFF", "dormant": "DORMANT"}.get(
        assessment["status"], "ON PACE"
    )
    return (
        f"{label}typical gap {assessment['typical_gap_days']:.1f} days | "
        f"last touch {assessment['days_since_last_touch']} days ago "
        f"(threshold {assessment['threshold_days']:.1f} days) | {flag}"
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
