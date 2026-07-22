"""
The "in the meantime" engagement tracker: runs the full pipeline (parse →
filter/sort → staleness → revival-library matching) across a BATCH of live
prospect accounts at once, and produces one consolidated status report —
stalled accounts first, ranked by how far past their own normal rhythm they
are.

This does not remove the manual step of exporting each account's Activity
History as .mhtml — that still has to happen until real Salesforce API
access is in place (see salesforce_api_access_request.md). What this adds is
not having to run suggestions.py one file at a time and stitch the results
together by hand.

Usage:
    python tracker.py "McKee=mckee.mhtml" "Noom=noom.mhtml" \\
        --library library.json --narrative-doc master.docx --nurture-senders "Anastasiia Romanova" "Noah Hess"
"""

import argparse
import json
import sys

from opportunity_parser import find_account_status
from parser import extract_html_from_mhtml, filter_and_sort_activities, parse_activities, parse_last_modified_date
from suggestions import RAW_EXPORT_NAME_ALIASES, format_suggestions_summary, suggest_reengagement_examples

# How far back from an account's most recent activity to look when checking
# whether a real rep (vs. a nurture/marketing sender) has been in touch.
# Arbitrary but reasonable: about a typical outreach cycle.
NURTURE_LOOKBACK_TOUCHES = 5

# "closed_not_actionable" sorts last: pure gap math said "stalled," but a
# cross-check against real Opportunity data confirmed the account has no
# open deal — it's quiet because it's over, not because it needs a rep.
STATUS_SORT_PRIORITY = {"stalled": 0, "on_pace": 1, "insufficient_history": 2, "no_activity": 3, "closed_not_actionable": 4}


def _actionable_status(staleness_status, opportunity_status):
    """staleness_status is the pure gap-math verdict from assess_staleness —
    left untouched for auditability. This derives what a rep should actually
    see: a "stalled" account whose only known Opportunities are all closed
    isn't something to act on, regardless of how the gap math reads."""
    if staleness_status == "stalled" and opportunity_status is not None and not opportunity_status["has_open_opportunity"]:
        return "closed_not_actionable"
    return staleness_status


def _urgency_sort_key(row):
    ratio = row["result"].get("live_gap_ratio") or 0
    return (STATUS_SORT_PRIORITY.get(row["actionable_status"], 5), -ratio)


def check_recent_sender_mix(records, nurture_senders):
    """Looks at the most recent handful of touches on an account and reports
    whether any of them came from someone NOT on the nurture_senders list —
    i.e. whether a real rep has personally touched this account recently, or
    whether it's been nurture/marketing sends only.

    nurture_senders: names known to be non-rep roles (newsletter/webinar
    sends, research team, etc.) — NOT inferred automatically. This list is
    only as good as what's been explicitly confirmed; an empty or incomplete
    list means this check has nothing to say, and says so rather than
    guessing.

    Returns None if there's no "Assigned To" data to check, or a dict with
    recent_senders / had_non_nurture_contact / checked_touch_count.
    """
    if not nurture_senders:
        return None

    dated = []
    for r in records:
        dt = parse_last_modified_date(r.get("last_modified_date"))
        if dt is not None and r.get("assigned_to"):
            dated.append((dt, r["assigned_to"]))
    if not dated:
        return None

    dated.sort(key=lambda x: x[0])
    recent = dated[-NURTURE_LOOKBACK_TOUCHES:]
    recent_senders = [name for _, name in recent]
    nurture_set = {n.lower() for n in nurture_senders}
    had_non_nurture_contact = any(name.lower() not in nurture_set for name in recent_senders)

    return {
        "recent_senders": recent_senders,
        "had_non_nurture_contact": had_non_nurture_contact,
        "checked_touch_count": len(recent),
    }


def run_tracker(
    account_exports, revival_library, lessons_by_account=None, top_n=3, as_of=None, nurture_senders=None, account_status=None
):
    """account_exports: iterable of (account_name, mhtml_path) for LIVE
    accounts (not closed-won — this is the thing being tracked, not the
    reference library). account_status: optional {account_name: {...}} from
    opportunity_parser.build_account_status — used to catch "stalled by pure
    gap math, but actually already closed" false positives. Returns a list
    of row dicts, sorted most-urgent-and-actionable-first; accounts confirmed
    already closed sort last regardless of how stale their activity looks."""
    account_status = account_status or {}
    rows = []
    for account_name, path in account_exports:
        html = extract_html_from_mhtml(path)
        records = filter_and_sort_activities(parse_activities(html))
        result = suggest_reengagement_examples(
            records, revival_library, as_of=as_of, top_n=top_n, lessons_by_account=lessons_by_account
        )
        opportunity_status = find_account_status(account_name, account_status)
        actionable_status = _actionable_status(result["staleness"]["status"], opportunity_status)
        sender_mix = check_recent_sender_mix(records, nurture_senders) if actionable_status == "stalled" else None
        rows.append(
            {
                "account": account_name,
                "result": result,
                "sender_mix": sender_mix,
                "opportunity_status": opportunity_status,
                "actionable_status": actionable_status,
            }
        )

    rows.sort(key=_urgency_sort_key)
    return rows


def format_tracker_report(rows):
    actionable_stalled = [r for r in rows if r["actionable_status"] == "stalled"]
    closed_not_actionable = [r for r in rows if r["actionable_status"] == "closed_not_actionable"]
    lines = [
        f"{len(actionable_stalled)} of {len(rows)} tracked accounts are stalled with an open deal.",
    ]
    if closed_not_actionable:
        lines.append(
            f"({len(closed_not_actionable)} more looked stalled by pure activity-gap math, but their only known "
            f"Opportunities are already closed — not shown as actionable below.)"
        )
    lines.append("")

    for row in rows:
        if row["actionable_status"] == "closed_not_actionable":
            stages = row["opportunity_status"]["stages"]
            lines.append(f"{row['account']}: stalled by activity gap, but Opportunity stage is {stages} — closed, not actionable.")
            lines.append("")
            continue

        lines.append(format_suggestions_summary(row["result"], row["account"]))
        if row["result"]["staleness"]["status"] == "stalled" and row["opportunity_status"] is None:
            lines.append("  Note: no Opportunity-stage data available for this account — not cross-checked against Salesforce.")

        sender_mix = row["sender_mix"]
        if sender_mix is not None:
            if sender_mix["had_non_nurture_contact"]:
                lines.append(
                    f"  Sender check: a contact not on the known nurture/marketing list touched this account "
                    f"within its last {sender_mix['checked_touch_count']} activities — recent silence isn't purely "
                    f"a nurture-only gap, based on that list. (List is only as complete as what's been confirmed — "
                    f"see --nurture-senders.)"
                )
            else:
                lines.append(
                    f"  Sender check: the last {sender_mix['checked_touch_count']} activities were all from "
                    f"{sorted(set(sender_mix['recent_senders']))}, currently on the known nurture/marketing list "
                    f"(not automatically inferred — confirm this list reflects reality before trusting this). If "
                    f"accurate: per the closed-won master doc, nurture sends alone rarely revived a stalled deal — "
                    f"it took a rep's direct personal contact on similar accounts."
                )
        lines.append("")

    return "\n".join(lines).rstrip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accounts", nargs="+", metavar="NAME=PATH", help="Live accounts to check, as NAME=path/to/export.mhtml")
    parser.add_argument("--library", required=True, help="Path to a revival library JSON file (from revival_library.py)")
    parser.add_argument("--narrative-doc", help="Optional path to the closed-won master .docx, for curator notes")
    parser.add_argument(
        "--opportunity-status",
        help="Optional path to an Opportunity report export (.xlsx) — used to catch 'stalled by gap math, "
        "actually already closed' false positives",
    )
    parser.add_argument(
        "--nurture-senders",
        nargs="*",
        default=[],
        metavar="NAME",
        help="Names known to be non-rep senders (newsletter/webinar/research roles), not inferred automatically",
    )
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("-o", "--output", help="Write JSON to this file instead of printing the text report")
    args = parser.parse_args()

    with open(args.library, encoding="utf-8") as f:
        revival_library = json.load(f)

    lessons_by_account = {}
    if args.narrative_doc:
        from narrative_parser import extract_lessons

        for lesson in extract_lessons(args.narrative_doc):
            lessons_by_account.setdefault(lesson["account"], []).append(lesson["text"])
        for raw_label, narrative_label in RAW_EXPORT_NAME_ALIASES.items():
            if narrative_label in lessons_by_account:
                lessons_by_account[raw_label] = lessons_by_account[narrative_label]

    account_status = {}
    if args.opportunity_status:
        from opportunity_parser import build_account_status, parse_opportunities_report

        account_status = build_account_status(parse_opportunities_report(args.opportunity_status))

    account_exports = []
    for spec in args.accounts:
        if "=" not in spec:
            parser.error(f"expected NAME=PATH, got: {spec}")
        name, path = spec.split("=", 1)
        account_exports.append((name, path))

    rows = run_tracker(
        account_exports,
        revival_library,
        lessons_by_account=lessons_by_account,
        top_n=args.top_n,
        nurture_senders=args.nurture_senders,
        account_status=account_status,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    else:
        print(format_tracker_report(rows))


if __name__ == "__main__":
    sys.exit(main())
