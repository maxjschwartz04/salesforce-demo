"""
Parses a Salesforce Activity History export saved as a .mhtml page archive
into clean structured JSON, and flags stale prospects for sales re-engagement.

Usage:
    python parser.py export.mhtml                      # print all activities as JSON
    python parser.py export.mhtml --filter             # drop Pro noise, sort by date
    python parser.py export.mhtml --filter -o out.json  # write to a file
"""

import argparse
import email
import json
import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup

LABEL_KEY_MAP = {
    "Subject": "subject",
    "Primary Name": "primary_name",
    "Related To": "related_to",
    "Stage": "stage",
    "Task": "task",
    "Due Date": "due_date",
    "Assigned To": "assigned_to",
    "Last Modified Date": "last_modified_date",
    "Comments": "comments",
}

LAST_MODIFIED_FORMAT = "%m/%d/%Y, %I:%M %p"
DUE_DATE_FORMAT = "%m/%d/%Y"

# Salesforce's activity-log email fields ("To:", "CC:", etc.) always sit at the
# start of a line, one field per line. Matching them by exact line-start avoids
# false hits inside forwarded email chains quoted further down in the body.
EMAIL_FIELD_PATTERNS = {
    "to": re.compile(r"^To:[ \t]*(.*)$", re.MULTILINE),
    "cc": re.compile(r"^CC:[ \t]*(.*)$", re.MULTILINE),
    "bcc": re.compile(r"^BCC:[ \t]*(.*)$", re.MULTILINE),
    "attachment": re.compile(r"^Attachment:[ \t]*(.*)$", re.MULTILINE),
    "subject": re.compile(r"^Subject:[ \t]*(.*)$", re.MULTILINE),
}
EMAIL_BODY_PATTERN = re.compile(r"^Body:[ \t]*\n?(.*)\Z", re.MULTILINE | re.DOTALL)

# Matches the specific phrase "POLITICO Pro" (case-insensitive, tolerant of
# extra whitespace) rather than the bare word "Pro" — a prospect company or
# contact with "Pro" in its name should never get swept up as noise.
PRO_NOISE_PATTERN = re.compile(r"\bpolitico\s+pro\b", re.IGNORECASE)


def extract_html_from_mhtml(path):
    """Extract the raw HTML document out of a .mhtml MIME archive."""
    with open(path, "rb") as f:
        raw = f.read()

    msg = email.message_from_bytes(raw)
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")

    raise ValueError(f"No text/html part found in MHTML archive: {path}")


def _clean_text(value_div):
    text = value_div.get_text(" ", strip=True).replace("\xa0", " ").strip()
    return text or None


def _extract_task_value(value_div):
    checkbox = value_div.find("input", attrs={"type": "checkbox"})
    if checkbox is not None:
        return checkbox.has_attr("checked")
    return _clean_text(value_div)


def _text_with_line_breaks(value_div):
    """Render a value cell's text with <br> tags turned into real newlines,
    so multi-line comment fields (email headers, body) stay parseable."""
    for br in value_div.find_all("br"):
        br.replace_with("\n")
    return value_div.get_text().replace("\xa0", " ").strip()


def _parse_email_fields(text):
    """If a comments blob looks like a logged email (has a "To:" line), pull
    out the nested To/CC/BCC/Attachment/Subject/Body fields. Returns None if
    the comment isn't an email log (e.g. call notes, MQL webform data)."""
    to_match = EMAIL_FIELD_PATTERNS["to"].search(text)
    if not to_match:
        return None

    fields = {}
    for key, pattern in EMAIL_FIELD_PATTERNS.items():
        match = pattern.search(text)
        fields[key] = (match.group(1).strip() or None) if match else None

    body_match = EMAIL_BODY_PATTERN.search(text)
    fields["body"] = body_match.group(1).strip() if body_match else None

    return fields


def _extract_comments_value(value_div):
    text = _text_with_line_breaks(value_div)
    if not text:
        return None
    return {"raw_text": text, "email": _parse_email_fields(text)}


def parse_activities(html):
    """Parse the extracted HTML into a list of activity records, one dict per
    activity panel, in the order they appear in the export."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    for panel in soup.find_all("div", class_="slds-panel"):
        field_map = {}
        for label_div in panel.find_all("div", class_="slds-text-label"):
            label_text = label_div.get_text(strip=True)
            if not label_text:
                continue
            value_div = label_div.find_next_sibling("div", class_="slds-text-value")
            if value_div is not None:
                field_map[label_text] = value_div

        record = {}
        for label_text, key in LABEL_KEY_MAP.items():
            value_div = field_map.get(label_text)
            if value_div is None:
                record[key] = None
            elif key == "task":
                record[key] = _extract_task_value(value_div)
            elif key == "comments":
                record[key] = _extract_comments_value(value_div)
            else:
                record[key] = _clean_text(value_div)

        records.append(record)

    return records


def parse_last_modified_date(raw):
    """Parse a record's raw 'last_modified_date' string into a datetime, or
    None if it's missing/unparseable. Public so downstream tools (e.g. the
    staleness checker) can sort/diff activities without re-deriving the
    export's datetime format."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, LAST_MODIFIED_FORMAT)
    except ValueError:
        return None


def _is_pro_noise(record):
    subject = record.get("subject") or ""
    related_to = record.get("related_to") or ""
    return bool(PRO_NOISE_PATTERN.search(subject) or PRO_NOISE_PATTERN.search(related_to))


def filter_and_sort_activities(records):
    """Drop POLITICO Pro noise (subscription/renewal/access activities that
    aren't sales engagement) and return the rest sorted oldest -> newest by
    Last Modified Date. Records with an unparseable/missing date sort first."""
    sales_records = [r for r in records if not _is_pro_noise(r)]
    sales_records.sort(key=lambda r: parse_last_modified_date(r.get("last_modified_date")) or datetime.min)
    return sales_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mhtml_path", help="Path to the Salesforce .mhtml export")
    parser.add_argument("-o", "--output", help="Write JSON to this file instead of stdout")
    parser.add_argument(
        "--filter",
        action="store_true",
        help="Drop POLITICO Pro noise and sort chronologically by Last Modified Date",
    )
    args = parser.parse_args()

    html = extract_html_from_mhtml(args.mhtml_path)
    records = parse_activities(html)
    if args.filter:
        records = filter_and_sort_activities(records)

    output = json.dumps(records, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    sys.exit(main())
