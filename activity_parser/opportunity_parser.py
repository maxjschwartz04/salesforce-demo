"""
Parses a Salesforce Opportunity report export (.xlsx) into an account-level
open/closed status map — so the tracker can tell "a live deal gone quiet"
apart from "a deal that's already Closed Won or Closed Lost, and is
naturally quiet because it's over." Confirmed necessary against a real
501-account staleness scan: at least one account flagged "stalled" by pure
gap math turned out to already be closed-won.

Usage:
    python opportunity_parser.py opportunities.xlsx -o account_status.json
"""

import argparse
import json
import re
import sys
from datetime import date, datetime

import openpyxl

CLOSED_STAGES = {"Closed Won", "Closed Lost"}

# Account names sometimes carry their own status flag, e.g. "ACQUIRED - Clif
# Bar" — not a win-back candidate at all if the company doesn't exist as an
# independent entity anymore.
DEFUNCT_ACCOUNT_PATTERN = re.compile(r"acquired|defunct|merged|out of business|bankrupt|dissolved", re.IGNORECASE)


def _parse_close_date(record):
    try:
        return datetime.strptime(record["close_date"], "%m/%d/%Y")
    except (ValueError, TypeError):
        return None

# The same company shows up under different labels across sources we don't
# control — "Celldex Therapeutics" vs "Celldex Therapeutics, Inc.", "McKee"
# (a short label someone typed on a CLI) vs "McKee Foods Corporation" (the
# Opportunity export's own name). A hardcoded alias table doesn't scale —
# this normalizes both sides and falls back to a prefix match, so lookups
# work without needing a new alias entry every time a new source disagrees
# on how to spell a company's name.
_CORPORATE_SUFFIXES = (" incorporated", " corporation", " corp", " inc", " llc", " ltd", " company", " co")


def _normalize_company_name(name):
    if not name:
        return ""
    normalized = re.sub(r"[,.]", "", name.lower().strip())
    for suffix in _CORPORATE_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
    return normalized


def find_account_status(account_name, account_status):
    """Looks up account_name in the {account_name: status} map from
    build_account_status, tolerating naming differences between sources.
    Tries an exact match first, then falls back to a single combined pool of
    normalized-exact and normalized-prefix matches — only committing to a
    match if that WHOLE pool has exactly one candidate.

    Checking normalized-exact and prefix as separate tiers (exact first,
    only falling back to prefix if exact found nothing) would let a
    normalized-exact hit short-circuit before ever noticing that a
    DIFFERENT real company also matches via prefix — e.g. "Acme" normalizes
    to an exact match for "Acme Corporation" (suffix-stripped), which would
    return confidently even if "Acme Industries" also exists in the same
    data and is equally plausible. Pooling both tiers before checking
    ambiguity closes that gap."""
    if account_name in account_status:
        return account_status[account_name]

    target = _normalize_company_name(account_name)
    if not target:
        return None

    candidates = {
        name
        for name in account_status
        if (norm := _normalize_company_name(name)) and (norm == target or norm.startswith(target) or target.startswith(norm))
    }
    if len(candidates) == 1:
        return account_status[next(iter(candidates))]

    return None  # no match, or ambiguous — don't guess


def is_prospect(account_name, account_status):
    """True if this account is fair game for the new-business tracker —
    i.e. NOT an existing customer, and not a company that no longer exists
    independently. Explicit scope decision: once an account has ANY Closed
    Won opportunity on file, it's Account Management's account for good,
    even if it later has a separate new open deal — this tool is
    new-business only and doesn't compete with or duplicate AM's outreach.

    Also excludes accounts flagged acquired/defunct/merged in their own
    name (same DEFUNCT_ACCOUNT_PATTERN check list_winback_candidates already
    applies) — re-engaging a company that's already gone isn't a real
    prospect, regardless of how its Opportunity history reads.

    Accounts with no Opportunity data at all are treated as prospects, not
    excluded — no data isn't confirmation they're a customer, and wrongly
    dropping a real prospect is worse than including one account too many."""
    if DEFUNCT_ACCOUNT_PATTERN.search(account_name):
        return False
    status = find_account_status(account_name, account_status)
    return status is None or not status["has_closed_won"]


def _find_header(rows):
    """Report exports have a variable number of metadata rows before the
    real header — find it by content (must have both Account Name and
    Stage) rather than assuming a fixed row number."""
    for i, row in enumerate(rows):
        col = {str(v).strip(): j for j, v in enumerate(row) if v is not None}
        if "Account Name" in col and "Stage" in col:
            return i, col
    raise ValueError("Could not find a header row containing 'Account Name' and 'Stage'")


def parse_opportunities_report(path):
    """Returns a flat list of {account_name, opportunity_name, owner, stage,
    close_date, created_date, type, next_step, amount, expected_revenue}
    dicts, one per opportunity row. next_step is the rep's own free-text
    plan for that opportunity — real human judgment already in the data,
    not something we generate. amount/expected_revenue are deal-specific
    dollar figures (NOT the same thing as an Account's firmographic annual
    revenue, which lives on a different object and isn't pulled here)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))

    header_idx, col = _find_header(rows)

    def get(row, name):
        idx = col.get(name)
        return row[idx] if idx is not None else None

    records = []
    for row in rows[header_idx + 1 :]:
        account = get(row, "Account Name")
        stage = get(row, "Stage")
        if account is None:
            continue  # blank row, or a footer/subtotal line with no account

        records.append(
            {
                "account_name": account,
                "opportunity_name": get(row, "Opportunity Name"),
                "owner": get(row, "Opportunity Owner"),
                "stage": stage,
                "close_date": get(row, "Close Date"),
                "created_date": get(row, "Created Date"),
                "type": get(row, "Type"),
                "next_step": get(row, "Next Step") or None,
                "amount": get(row, "Amount"),
                "expected_revenue": get(row, "Expected Revenue"),
            }
        )

    return records


def build_account_status(records):
    """Returns {account_name: {"has_open_opportunity", "has_closed_won",
    "stages", "opportunity_count", "open_next_steps"}}. An account not
    present as a key here simply wasn't covered by whatever Opportunity
    export this came from — callers should treat that as "unknown," not "no
    opportunities."

    open_next_steps is the rep's own free-text plan for each currently-open
    opportunity on the account (empty list if there isn't one, or the
    account has none open) — surfaced as-is, not summarized or rewritten.

    open_amount is the dollar Amount of the open opportunity (None if there
    isn't one, or the export didn't have an Amount for it) — deal-specific,
    not the same thing as an Account's firmographic annual revenue."""
    by_account = {}
    for r in records:
        by_account.setdefault(r["account_name"], []).append(r)

    status = {}
    for account, opps in by_account.items():
        stages = [o["stage"] for o in opps if o["stage"]]
        open_opps = [o for o in opps if o["stage"] and o["stage"] not in CLOSED_STAGES]
        open_amount = next((o["amount"] for o in open_opps if o.get("amount")), None)
        status[account] = {
            "has_open_opportunity": any(s not in CLOSED_STAGES for s in stages),
            "has_closed_won": any(s == "Closed Won" for s in stages),
            "stages": stages,
            "opportunity_count": len(opps),
            "open_next_steps": [o["next_step"] for o in open_opps if o["next_step"]],
            "open_amount": open_amount,
        }
    return status


def list_winback_candidates(records, as_of=None):
    """Every account whose MOST RECENT Opportunity (by close date) is Closed
    Lost — a candidate list for a human-led win-back conversation, NOT a
    scored or drafted recommendation.

    Deliberately facts-only: account, the lost opportunity, how long ago,
    and deal size. No revival-library matching, no suggested messaging. A
    win-back needs to know WHY a deal was lost and to whom — this data
    can't tell us that, so anything beyond the raw facts would risk
    dressing up generic advice as insight on a situation that specifically
    isn't generic.

    Sorted MOST-RECENT-loss-first, not longest-quiet-first — unlike a live
    stalled deal (where longer silence is more urgent), a loss from 2016 is
    stale precedent, not something worth acting on; a recent loss is more
    likely to still have relevant, current context (the buyer, the budget,
    the reason it fell through). Accounts flagged as acquired/defunct in
    their own name are excluded outright — not a real candidate.
    """
    if as_of is None:
        as_of = date.today()

    by_account = {}
    for r in records:
        by_account.setdefault(r["account_name"], []).append(r)

    candidates = []
    for account, opps in by_account.items():
        if DEFUNCT_ACCOUNT_PATTERN.search(account):
            continue

        dated = [(_parse_close_date(o), o) for o in opps]
        dated = sorted(((d, o) for d, o in dated if d is not None), key=lambda x: x[0])
        if not dated:
            continue

        most_recent_date, most_recent_opp = dated[-1]
        if most_recent_opp["stage"] != "Closed Lost":
            continue

        candidates.append(
            {
                "account": account,
                "opportunity_name": most_recent_opp["opportunity_name"],
                "owner": most_recent_opp["owner"],
                "close_date": most_recent_opp["close_date"],
                "days_since_loss": (as_of - most_recent_date.date()).days,
            }
        )

    candidates.sort(key=lambda c: c["days_since_loss"])
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_path", help="Path to the Opportunity report export (.xlsx)")
    parser.add_argument("-o", "--output", help="Write JSON to this file instead of stdout")
    args = parser.parse_args()

    records = parse_opportunities_report(args.report_path)
    status = build_account_status(records)
    print(f"parsed {len(records)} opportunities across {len(status)} accounts", file=sys.stderr)

    output = json.dumps(status, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    sys.exit(main())
