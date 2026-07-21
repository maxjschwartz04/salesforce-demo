"""
Builds a "revival pattern" library from CLOSED-WON accounts: moments where an
account went quiet for meaningfully longer than its own typical rhythm, then
came back to life, plus what re-engagement email triggered it and how fast
the next response came.

Deliberate scope decision (explicit, not inferred): this library is built
ONLY from closed-won accounts. A closed-won account's revival is proof the
re-engagement actually led somewhere; a currently-healthy live account's
"revival" is only a hint since the deal hasn't closed yet. Mixing the two
would blur that signal, so live/open accounts should not be passed in here.
If that's ever revisited, do it as an explicit opt-in (e.g. a `source`
label on each entry) rather than silently pooling both.

Usage:
    python revival_library.py "Geron=geron.mhtml" "LEO Pharma=leo_pharma.mhtml" -o library.json
"""

import argparse
import json
import re
import statistics
import sys

from parser import extract_html_from_mhtml, filter_and_sort_activities, parse_activities, parse_last_modified_date
from staleness import MIN_ENGAGEMENT_DAYS, STALLED_MULTIPLIER

EXCERPT_LENGTH = 220

# Billing/AR emails ("First Reminder: Politico Overdue Invoice SIN048316")
# get logged as activities and can land right after a long gap purely by
# accounting coincidence — that's not a rep re-engaging, so it shouldn't
# qualify as a revival example.
BILLING_NOISE_PATTERN = re.compile(r"\binvoic\w*\b|\boverdue\b", re.IGNORECASE)


def _excerpt(record):
    """A short, readable snippet of what the re-engagement email actually said."""
    comments = record.get("comments")
    if not comments:
        return None
    email = comments.get("email")
    text = (email.get("body") if email else None) or comments.get("raw_text")
    if not text:
        return None
    text = " ".join(text.split())
    if len(text) <= EXCERPT_LENGTH:
        return text
    return text[:EXCERPT_LENGTH].rsplit(" ", 1)[0] + "…"


def find_revival_moments(records, multiplier=STALLED_MULTIPLIER, min_engagement_days=MIN_ENGAGEMENT_DAYS):
    """Find every point in one account's history where a gap notably larger
    than its own typical rhythm (same threshold as staleness.assess_staleness)
    was followed by a resumed response.

    records: a filtered activity list for ONE account (order doesn't matter,
        sorted internally).

    A gap only counts as a "revival" if:
      - the first activity that breaks the silence is an actual logged
        email (has nested To/Subject/Body), not an internal task note like
        "talk to Lily // reapproach" or a bare call log — those aren't
        something we can hand back as "the email that worked"
      - that email isn't a billing/invoice notice — those get logged as
        activities too but aren't a rep's re-engagement tactic
      - there's a later activity to measure a response against — a
        re-engagement email that got no reply at all isn't evidence of
        anything working, so it's excluded rather than reported with a
        missing/undefined response time
    """
    dated = []
    for r in records:
        dt = parse_last_modified_date(r.get("last_modified_date"))
        if dt is not None:
            dated.append((dt, r))
    dated.sort(key=lambda x: x[0])

    if len(dated) < 2:
        return []

    engagement_days = sorted({dt.date() for dt, _ in dated})
    if len(engagement_days) < min_engagement_days:
        return []

    gaps = [(engagement_days[i + 1] - engagement_days[i]).days for i in range(len(engagement_days) - 1)]
    typical_gap_days = statistics.median(gaps)
    threshold_days = typical_gap_days * multiplier

    day_to_first_index = {}
    for idx, (dt, _) in enumerate(dated):
        d = dt.date()
        if d not in day_to_first_index:
            day_to_first_index[d] = idx

    moments = []
    for i in range(len(engagement_days) - 1):
        day_before, day_after = engagement_days[i], engagement_days[i + 1]
        gap_days = (day_after - day_before).days
        if gap_days <= threshold_days:
            continue

        revival_index = day_to_first_index[day_after]
        revival_dt, revival_record = dated[revival_index]

        comments = revival_record.get("comments")
        if not comments or not comments.get("email"):
            continue  # silence was broken by a task/call/note, not an email we can extract

        if BILLING_NOISE_PATTERN.search(revival_record.get("subject") or ""):
            continue  # silence was broken by an invoice/AR notice, not a sales re-engagement

        if revival_index + 1 >= len(dated):
            continue  # re-engagement got no follow-up at all — not a proven revival

        next_dt, next_record = dated[revival_index + 1]

        moments.append(
            {
                "gap_days": gap_days,
                "typical_gap_days": typical_gap_days,
                "gap_start_date": day_before.isoformat(),
                "gap_end_date": day_after.isoformat(),
                "revival_date": revival_dt.isoformat(),
                "revival_subject": revival_record.get("subject"),
                "revival_excerpt": _excerpt(revival_record),
                "next_response_date": next_dt.isoformat(),
                "next_response_subject": next_record.get("subject"),
                "days_to_next_response": round((next_dt - revival_dt).total_seconds() / 86400, 2),
            }
        )

    return moments


def build_revival_library(account_exports):
    """account_exports: iterable of (account_name, mhtml_path) for CLOSED-WON
    accounts only (see module docstring). Returns a flat list of revival
    moments across all accounts, sorted chronologically by revival date."""
    library = []
    for account_name, path in account_exports:
        html = extract_html_from_mhtml(path)
        records = filter_and_sort_activities(parse_activities(html))
        for moment in find_revival_moments(records):
            moment["account"] = account_name
            library.append(moment)

    library.sort(key=lambda m: m["revival_date"])
    return library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "accounts",
        nargs="+",
        metavar="NAME=PATH",
        help="One or more closed-won accounts as NAME=path/to/export.mhtml",
    )
    parser.add_argument("-o", "--output", help="Write JSON to this file instead of stdout")
    args = parser.parse_args()

    account_exports = []
    for spec in args.accounts:
        if "=" not in spec:
            parser.error(f"expected NAME=PATH, got: {spec}")
        name, path = spec.split("=", 1)
        account_exports.append((name, path))

    library = build_revival_library(account_exports)
    output = json.dumps(library, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    sys.exit(main())
