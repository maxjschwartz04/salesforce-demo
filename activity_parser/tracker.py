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

from activity_feed import build_activity_feed
from campaign_parser import get_recent_engagements
from opportunity_parser import find_account_status, is_prospect
from parser import extract_html_from_mhtml, filter_and_sort_activities, parse_activities, parse_last_modified_date
from playbook import next_step_display
from suggestions import RAW_EXPORT_NAME_ALIASES, format_suggestions_summary, suggest_reengagement_examples

# How far back from an account's most recent activity to look when checking
# whether a real rep (vs. a nurture/marketing sender) has been in touch.
# Arbitrary but reasonable: about a typical outreach cycle.
NURTURE_LOOKBACK_TOUCHES = 5

# "closed_not_actionable" sorts last: pure gap math said "stalled,"
# "cooling_off," "dormant," or "never_engaged," but a cross-check against
# real Opportunity data confirmed the account has no open deal — it's quiet
# because it's over, not because it needs a rep. "dormant" (silent past the
# flat DORMANT_DAYS backstop — see staleness.py) sorts below "stalled" and
# "cooling_off": still worth a rep's attention, but a long-buried account is
# less urgent than one that only recently went quiet. "never_engaged" (never
# had a second touch at all — see staleness.py's NEW_LEAD_GRACE_DAYS) sorts
# below dormant: there's less evidence of real interest here than in an
# account that at least had a real relationship before it went quiet. "new"
# sorts below on_pace -- too fresh to have an opinion on, not a concern.
STATUS_SORT_PRIORITY = {
    "stalled": 0,
    "cooling_off": 1,
    "dormant": 2,
    "never_engaged": 3,
    "on_pace": 4,
    "new": 5,
    "no_activity": 6,
    "closed_not_actionable": 7,
}


def _actionable_status(staleness_status, opportunity_status):
    """staleness_status is the pure gap-math verdict from assess_staleness —
    left untouched for auditability. This derives what a rep should actually
    see: a "stalled," "cooling_off," "dormant," or "never_engaged" account
    whose only known Opportunities are all closed isn't something to act
    on, regardless of how the gap math reads."""
    if (
        staleness_status in ("stalled", "cooling_off", "dormant", "never_engaged")
        and opportunity_status is not None
        and not opportunity_status["has_open_opportunity"]
    ):
        return "closed_not_actionable"
    return staleness_status


def _urgency_sort_key(row):
    ratio = row["result"].get("live_gap_ratio") or 0
    return (STATUS_SORT_PRIORITY.get(row["actionable_status"], 5), -ratio)


def _format_engagement_lines(recent_engagements):
    """Marketing engagement is context ("still active elsewhere"), not a
    suggestion — no framing beyond the bare facts."""
    lines = []
    for e in recent_engagements:
        lines.append(
            f"  Marketing engagement ({e['date_group']}): {e['first_name']} {e['last_name']} — "
            f"{e['member_status']} on \"{e['campaign_name']}\""
        )
    return lines


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
    account_exports,
    revival_library,
    lessons_by_account=None,
    top_n=3,
    as_of=None,
    nurture_senders=None,
    account_status=None,
    campaign_by_company=None,
):
    """account_exports: iterable of (account_name, mhtml_path) for LIVE
    accounts (not closed-won — this is the thing being tracked, not the
    reference library). account_status: optional {account_name: {...}} from
    opportunity_parser.build_account_status — used to catch "stalled by pure
    gap math, but actually already closed" false positives, AND to skip
    existing customers entirely (see opportunity_parser.is_prospect — this
    tool is new-business only; Account Management owns outreach to accounts
    that have ever closed a deal). campaign_by_company: optional {company:
    [engagement, ...]} from campaign_parser.group_by_company — surfaced as
    recent marketing-engagement facts, exact-match only (see
    campaign_parser.get_recent_engagements for why). Returns a list of row
    dicts, sorted most-urgent-and-actionable-first; accounts confirmed
    already closed sort last regardless of how stale their activity looks.

    Each row also carries "staleness" and "examples" as top-level aliases
    of result["staleness"]/result["examples"] (same dicts, not copies) and
    a precomputed "next_step_display" (from playbook.next_step_display) --
    that's the flat shape playbook.py's functions expect, computed once
    here rather than re-derived by every caller."""
    account_status = account_status or {}
    campaign_by_company = campaign_by_company or {}
    rows = []
    for account_name, path in account_exports:
        if not is_prospect(account_name, account_status):
            continue  # existing customer -- Account Management's account, not new-business pipeline
        html = extract_html_from_mhtml(path)
        records = filter_and_sort_activities(parse_activities(html))
        result = suggest_reengagement_examples(
            records, revival_library, as_of=as_of, top_n=top_n, lessons_by_account=lessons_by_account
        )
        opportunity_status = find_account_status(account_name, account_status)
        actionable_status = _actionable_status(result["staleness"]["status"], opportunity_status)
        sender_mix = (
            check_recent_sender_mix(records, nurture_senders)
            if actionable_status in ("stalled", "dormant", "never_engaged")
            else None
        )
        recent_engagements = get_recent_engagements(account_name, campaign_by_company)
        row = {
            "account": account_name,
            "result": result,
            # Duplicated (not copied -- same dicts) at the top level rather
            # than nested under "result", because that's the flat shape
            # playbook.py's functions expect. Keeping "result" too so
            # nothing else in this file that already reads row["result"]
            # needs to change.
            "staleness": result["staleness"],
            "examples": result["examples"],
            "sender_mix": sender_mix,
            "opportunity_status": opportunity_status,
            "actionable_status": actionable_status,
            "recent_engagements": recent_engagements,
            "activity_feed": build_activity_feed(records),
        }
        row["next_step_display"] = next_step_display(row)
        rows.append(row)

    rows.sort(key=_urgency_sort_key)
    return rows


def format_tracker_report(rows):
    actionable_stalled = [r for r in rows if r["actionable_status"] == "stalled"]
    actionable_dormant = [r for r in rows if r["actionable_status"] == "dormant"]
    actionable_never_engaged = [r for r in rows if r["actionable_status"] == "never_engaged"]
    closed_not_actionable = [r for r in rows if r["actionable_status"] == "closed_not_actionable"]
    lines = [
        f"{len(actionable_stalled)} of {len(rows)} tracked accounts are stalled with an open deal.",
    ]
    if actionable_dormant:
        lines.append(
            f"{len(actionable_dormant)} more have gone quiet for over a year (dormant) with an open deal — "
            f"still worth a look, but lower urgency than the recently-stalled accounts above."
        )
    if actionable_never_engaged:
        lines.append(
            f"{len(actionable_never_engaged)} more have never had a real second touch — no relationship to "
            f"re-engage, but worth a first outreach."
        )
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
            lines.extend(_format_engagement_lines(row["recent_engagements"]))
            lines.append("")
            continue

        lines.append(format_suggestions_summary(row["result"], row["account"]))
        if row["result"]["staleness"]["status"] in (
            "stalled",
            "dormant",
            "never_engaged",
        ) and row["opportunity_status"] is None:
            lines.append("  Note: no Opportunity-stage data available for this account — not cross-checked against Salesforce.")

        # on_pace (and never_engaged with a logged plan) show the rep's own
        # note as-is; cooling_off/stalled/dormant get the blended suggestion
        # instead (see playbook.next_step_display for why not both);
        # never_engaged with no logged plan gets a distinct first-outreach
        # prompt rather than either -- there's no precedent to lean on.
        next_step = row["next_step_display"]
        if next_step["mode"] == "raw":
            lines.append(f'  Rep\'s own last "Next Step" note on the open deal: "{next_step["text"]}"')
        elif next_step["mode"] == "blended":
            lines.append(f"  Suggested next step: {next_step['text']}")
        elif next_step["mode"] == "first_outreach":
            lines.append(f"  {next_step['text']}")

        lines.extend(_format_engagement_lines(row["recent_engagements"]))

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


def format_winback_section(candidates, top_n=15, campaign_by_company=None):
    """Deliberately bare — account, lost opportunity, how long ago, owner,
    and (if available) recent marketing engagement as a plain fact. No
    revival-library matches, no drafted messaging, no scoring. Per explicit
    direction: win-back needs case-by-case human judgment, not something
    that looks like a system recommendation."""
    campaign_by_company = campaign_by_company or {}
    lines = [
        f"{len(candidates)} accounts whose most recent Opportunity is Closed Lost "
        f"(sorted most-recent-loss-first; excludes accounts flagged acquired/defunct).",
        "Facts only, for a human to review case by case — no suggested messaging attached on purpose:",
        "",
    ]
    for c in candidates[:top_n]:
        lines.append(f"  {c['days_since_loss']:5d}d ago  {c['account']:45s} ({c['opportunity_name']}, owner: {c['owner']})")
        lines.extend(_format_engagement_lines(get_recent_engagements(c["account"], campaign_by_company, top_n=1)))
    if len(candidates) > top_n:
        lines.append(f"  ... and {len(candidates) - top_n} more")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accounts", nargs="+", metavar="NAME=PATH", help="Live accounts to check, as NAME=path/to/export.mhtml")
    parser.add_argument("--library", required=True, help="Path to a revival library JSON file (from revival_library.py)")
    parser.add_argument("--narrative-doc", help="Optional path to the closed-won master .docx, for curator notes")
    parser.add_argument(
        "--opportunity-status",
        help="Optional path to an Opportunity report export (.xlsx) — used to catch 'stalled by gap math, "
        "actually already closed' false positives, and to list win-back candidates (Closed Lost accounts)",
    )
    parser.add_argument("--top-winback", type=int, default=15, help="How many win-back candidates to print (default 15)")
    parser.add_argument(
        "--campaign-report", help="Optional path to a Campaign Member report export (.xlsx) — surfaces recent marketing engagement"
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
    winback_candidates = []
    if args.opportunity_status:
        from opportunity_parser import build_account_status, list_winback_candidates, parse_opportunities_report

        opportunity_records = parse_opportunities_report(args.opportunity_status)
        account_status = build_account_status(opportunity_records)
        winback_candidates = list_winback_candidates(opportunity_records)

    campaign_by_company = {}
    if args.campaign_report:
        from campaign_parser import group_by_company, parse_campaign_report

        campaign_by_company = group_by_company(parse_campaign_report(args.campaign_report))

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
        campaign_by_company=campaign_by_company,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"rows": rows, "winback_candidates": winback_candidates}, f, indent=2, ensure_ascii=False)
    else:
        print(format_tracker_report(rows))
        if winback_candidates:
            print()
            print("--- Win-back candidates (separate from the above — see note) ---")
            print(format_winback_section(winback_candidates, top_n=args.top_winback, campaign_by_company=campaign_by_company))


if __name__ == "__main__":
    sys.exit(main())
