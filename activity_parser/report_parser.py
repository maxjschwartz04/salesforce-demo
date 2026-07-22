"""
Parses a Salesforce Report export (Lightning "Export" -> Details Only,
saved as .xls but actually an HTML table) into the same record shape
parser.py produces from an .mhtml Activity History export — so the SAME
downstream functions (filter_and_sort_activities, staleness.assess_staleness,
tracker.run_tracker) work unchanged regardless of which pipeline the data
came from.

IMPORTANT DIFFERENCES from the .mhtml pipeline, confirmed against a real
898-row AgencyIQ-scoped export before building this:

- One file covers MANY accounts at once (this export: 501 distinct
  accounts), not one file per account — group_by_account() splits it.
- "Full Comments" is a short rep-typed note ("Initial meeting", "Demo
  Request"), NOT the full email body/To/CC/BCC/Subject structure the
  .mhtml Comments field has. comments["email"] is always None here as a
  result — records from this source will never qualify as a
  revival_library "revival" (find_revival_moments requires a real logged
  email), by design. This source is for STALENESS tracking at scale, not
  for growing the revival library's content.
- Status and Task were blank/constant (0) across every row in a live
  898-row export — not used for this record type in this org. Don't rely
  on them.
- No time-of-day, only a date — same synthetic-noon-timestamp approach as
  narrative_parser.py, for the same reason (need SOME timestamp for the
  shared parsing/sorting code, ties break in original row order).

Usage:
    python report_parser.py report.xls -o accounts.json
"""

import argparse
import json
import sys

from bs4 import BeautifulSoup

FIELD_MAP_NOTE = "See module docstring for what's reliably populated in this format."


def _to_bool(value):
    return value.strip() not in ("", "0", "false", "False")


def parse_report_export(path):
    """Returns a flat list of records, one per row, in the same shape as
    parser.parse_activities(), plus two extra keys this source has that the
    .mhtml pipeline doesn't: 'opportunity' and 'contact_email'."""
    with open(path, "r", encoding="ISO-8859-1") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError(f"No table found in report export: {path}")

    rows = table.find_all("tr")
    headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]
    idx = {h: i for i, h in enumerate(headers)}

    required = ["Date", "Company / Account", "Subject", "Assigned", "Last Modified Date", "Full Comments"]
    missing = [h for h in required if h not in idx]
    if missing:
        raise ValueError(f"Report export is missing expected column(s): {missing}")

    records = []
    for tr in rows[1:]:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) != len(headers):
            continue  # malformed row, skip rather than misalign fields

        get = lambda name: cells[idx[name]].strip() or None  # noqa: E731

        primary_name = get("Contact") or get("Lead")
        last_modified_raw = get("Last Modified Date")
        last_modified = f"{last_modified_raw}, 12:00 PM" if last_modified_raw else None
        comments_text = get("Full Comments")

        records.append(
            {
                "subject": get("Subject"),
                "primary_name": primary_name,
                "related_to": get("Company / Account"),
                "stage": get("Status"),
                "task": _to_bool(cells[idx["Task"]]) if "Task" in idx else None,
                "due_date": get("Date"),
                "assigned_to": get("Assigned"),
                "last_modified_date": last_modified,
                "comments": {"raw_text": comments_text, "email": None} if comments_text else None,
                "opportunity": get("Opportunity") if "Opportunity" in idx else None,
                "contact_email": get("Email") if "Email" in idx else None,
            }
        )

    return records


def group_by_account(records):
    """Splits a flat record list into {account_name: [records]}. Records
    with no Company/Account value are dropped (can't be tracked without
    knowing which account they belong to)."""
    grouped = {}
    for record in records:
        account = record.get("related_to")
        if not account:
            continue
        grouped.setdefault(account, []).append(record)
    return grouped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_path", help="Path to the Salesforce report export (.xls, actually HTML)")
    parser.add_argument("-o", "--output", help="Write JSON to this file instead of stdout")
    args = parser.parse_args()

    records = parse_report_export(args.report_path)
    grouped = group_by_account(records)
    print(f"parsed {len(records)} rows across {len(grouped)} accounts", file=sys.stderr)

    output = json.dumps(grouped, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    sys.exit(main())
