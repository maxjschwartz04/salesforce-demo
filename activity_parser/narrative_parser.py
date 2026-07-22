"""
Ingests the curated "Closed-Won Deal Email Activity — Master Document" .docx
format and feeds it through the SAME revival-detection math as the raw
mhtml pipeline (revival_library.find_revival_moments), so the two sources
produce directly comparable output shapes.

IMPORTANT CAVEAT, not fixable by parsing harder: this document is a
human-curated narrative, not a raw Salesforce export. It's organized into
hand-picked sections ("Trial kickoff", "Pricing & contract sequence") and
explicitly omits/abridges some touches for length. That means the "typical
gap" computed from it reflects gaps in what got written up, not necessarily
gaps in actual customer silence — likely a sparser, coarser rhythm than the
account's true touch history. Every moment built from this source is tagged
"source": "curated_narrative" (vs. "raw_export" for the mhtml pipeline) so
that reliability difference travels with the data rather than getting lost.

The document's own "⚠" annotations are never parsed as touches (they'd
corrupt the gap math if they were), but extract_lessons() pulls them out as
a SEPARATE layer: human judgment from the reps who ran these deals about
*why* a gap broke, which is a stronger signal than anything derived from
keyword-matching subject lines. Most of these annotations (~85% in the
first version of this doc) turn out to be a repetitive data-quality caveat
("export only captured corrupted HTML for this entry") rather than actual
insight — extract_lessons() filters those out and returns only the ones
that describe what actually happened in the deal.

Usage:
    python narrative_parser.py master_doc.docx --exclude "Celldex Therapeutics, Inc." "GSK" -o narrative_library.json
"""

import argparse
import json
import re
import sys
from datetime import datetime

import docx

from revival_library import find_revival_moments

TOUCH_LINE_PATTERN = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\s*[—-]\s*(.+)$")
SUBJECT_PATTERN = re.compile(r'"([^"]+)"')
SECTION_DIVIDER_PATTERN = re.compile(r"^-{2,}.*-{2,}$")
ACCOUNT_HEADING_NUMBER_PATTERN = re.compile(r"^\d+\.\s*")

# Annotation categories that aren't a "lesson" about what worked — a data
# export flaw or a scene-setting aside isn't judgment about the deal.
_BOILERPLATE_ANNOTATION_PATTERNS = [
    re.compile(r"corrupted|export only captured", re.IGNORECASE),
    re.compile(r"no significant time gap|continuously documented", re.IGNORECASE),
    re.compile(r"^⚠\s*first account under", re.IGNORECASE),
]


def _is_boilerplate_annotation(text):
    return any(p.search(text) for p in _BOILERPLATE_ANNOTATION_PATTERNS)

# The doc's own placeholder for content it deliberately left out ("...not
# reproduced here to reduce document length..."). That's not real body
# text — surfacing it as an "excerpt" would look like genuine email content
# to anyone reading the library, so it gets treated as no body at all.
REDACTED_BODY_PATTERN = re.compile(r"not reproduced here", re.IGNORECASE)


def parse_narrative_docx(path):
    """Returns {account_name: [touch, ...]}, each touch a dict with
    date/subject/body_lines/sequence, in document (chronological) order."""
    doc = docx.Document(path)

    accounts = {}
    current_account = None
    current_touch = None
    sequence = 0

    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = paragraph.style.name if paragraph.style else None

        if style == "Heading 1":
            continue  # rep name — not needed to group by account

        if style == "Heading 2":
            current_account = ACCOUNT_HEADING_NUMBER_PATTERN.sub("", text).strip()
            accounts.setdefault(current_account, [])
            current_touch = None
            continue

        if current_account is None:
            continue  # front matter before the first account heading

        if text.startswith("⚠"):
            continue  # human annotation/commentary, not a data row
        if SECTION_DIVIDER_PATTERN.match(text):
            current_touch = None
            continue
        if text.startswith("Opportunity:"):
            continue  # account metadata line, not a touch

        touch_match = TOUCH_LINE_PATTERN.match(text)
        if touch_match:
            date_str, remainder = touch_match.groups()
            try:
                touch_date = datetime.strptime(date_str, "%m/%d/%Y").date()
            except ValueError:
                current_touch = None
                continue
            subject_match = SUBJECT_PATTERN.search(remainder)
            sequence += 1
            current_touch = {
                "date": touch_date,
                "subject": subject_match.group(1) if subject_match else remainder,
                "body_lines": [],
                "sequence": sequence,
            }
            accounts[current_account].append(current_touch)
            continue

        if current_touch is not None:
            current_touch["body_lines"].append(text)

    return accounts


def extract_lessons(path):
    """Pulls the document's "⚠" annotations that describe actual deal
    judgment (a notable gap and what broke it, or a qualitative read on the
    deal's shape), filtering out the boilerplate data-quality caveats and
    scene-setting asides that make up most of them.

    Returns [{"account": str, "text": str}, ...] in document order. An
    account can have more than one lesson (e.g. a second, later expansion
    deal logged under the same company name)."""
    doc = docx.Document(path)

    current_account = None
    lessons = []
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = paragraph.style.name if paragraph.style else None

        if style == "Heading 2":
            current_account = ACCOUNT_HEADING_NUMBER_PATTERN.sub("", text).strip()
            continue

        if text.startswith("⚠") and current_account is not None and not _is_boilerplate_annotation(text):
            lessons.append({"account": current_account, "text": text.lstrip("⚠").strip()})

    return lessons


def _touch_to_record(touch):
    """Adapt a narrative touch into the minimal record shape
    revival_library.find_revival_moments expects. Narrative entries have no
    time-of-day, only a date, so same-day touches get an identical synthetic
    noon timestamp — Python's stable sort then preserves the document's own
    (chronological) ordering for ties, which is what determines "days to
    next response" precision for narrative-sourced moments."""
    body = " ".join(touch["body_lines"]).strip() or None
    if body and REDACTED_BODY_PATTERN.search(body):
        body = None
    return {
        "subject": touch["subject"],
        "last_modified_date": touch["date"].strftime("%m/%d/%Y") + ", 12:00 PM",
        "comments": {"raw_text": body, "email": {"body": body}},
    }


def build_revival_library_from_narrative(docx_path, exclude_accounts=None):
    """Returns (library, parsed_account_names). exclude_accounts should list
    the narrative's OWN account names exactly (see module usage) — company
    naming isn't consistent enough between this doc and other sources to
    match automatically."""
    exclude_accounts = set(exclude_accounts or [])
    accounts = parse_narrative_docx(docx_path)

    library = []
    for account_name, touches in accounts.items():
        if account_name in exclude_accounts:
            continue
        records = [_touch_to_record(t) for t in touches]
        for moment in find_revival_moments(records):
            moment["account"] = account_name
            moment["source"] = "curated_narrative"
            library.append(moment)

    library.sort(key=lambda m: m["revival_date"])
    return library, sorted(accounts.keys())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx_path", help="Path to the master narrative .docx")
    parser.add_argument(
        "--exclude", nargs="*", default=[], metavar="ACCOUNT_NAME", help="Narrative account name(s) to skip"
    )
    parser.add_argument("-o", "--output", help="Write JSON to this file instead of stdout")
    args = parser.parse_args()

    library, accounts = build_revival_library_from_narrative(args.docx_path, exclude_accounts=args.exclude)
    print(f"parsed {len(accounts)} accounts, excluded {len(args.exclude)}, found {len(library)} moments", file=sys.stderr)

    output = json.dumps(library, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    sys.exit(main())
