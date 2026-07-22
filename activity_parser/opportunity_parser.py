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

import openpyxl

CLOSED_STAGES = {"Closed Won", "Closed Lost"}

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
    Tries an exact match first, then a normalized match, then a normalized
    prefix match (in either direction) — but only commits to the prefix
    match if it's unambiguous (exactly one candidate); otherwise returns
    None rather than risk matching the wrong company."""
    if account_name in account_status:
        return account_status[account_name]

    target = _normalize_company_name(account_name)
    if not target:
        return None

    exact_normalized = [name for name in account_status if _normalize_company_name(name) == target]
    if len(exact_normalized) == 1:
        return account_status[exact_normalized[0]]

    prefix_matches = [
        name
        for name in account_status
        if (norm := _normalize_company_name(name)) and (norm.startswith(target) or target.startswith(norm))
    ]
    if len(prefix_matches) == 1:
        return account_status[prefix_matches[0]]

    return None  # no match, or ambiguous — don't guess


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
    close_date, created_date, type} dicts, one per opportunity row."""
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
            }
        )

    return records


def build_account_status(records):
    """Returns {account_name: {"has_open_opportunity", "has_closed_won",
    "stages", "opportunity_count"}}. An account not present as a key here
    simply wasn't covered by whatever Opportunity export this came from —
    callers should treat that as "unknown," not "no opportunities."""
    by_account = {}
    for r in records:
        by_account.setdefault(r["account_name"], []).append(r)

    status = {}
    for account, opps in by_account.items():
        stages = [o["stage"] for o in opps if o["stage"]]
        status[account] = {
            "has_open_opportunity": any(s not in CLOSED_STAGES for s in stages),
            "has_closed_won": any(s == "Closed Won" for s in stages),
            "stages": stages,
            "opportunity_count": len(opps),
        }
    return status


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
