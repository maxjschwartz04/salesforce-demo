"""
Phase 4: given a live account's activity history, run the staleness check
(staleness.py) and, if it's stalled, surface the closest-matching examples
from the closed-won revival library (revival_library.py) — presented as
reference examples for a rep to consider, NOT a scored recommendation or a
guaranteed fix. See revival_library.py's docstring for why the library is
closed-won-only.

The library is still small (2 accounts as of this writing). Every result
this module returns carries that count so the caveat travels with the
output wherever it's displayed, rather than living only in a comment here.

Usage:
    python suggestions.py live_account.mhtml --library library.json
"""

import argparse
import json
import sys

from parser import extract_html_from_mhtml, filter_and_sort_activities, parse_activities
from staleness import assess_staleness, format_staleness_summary

DEFAULT_TOP_N = 3

# The 7 accounts we deliberately kept on raw-export data (revival_library.py)
# were labeled with whatever name was handed to that CLI, which doesn't
# always match the narrative doc's own heading text for the same company
# (e.g. "Kerry Inc." vs "Kerry, Inc."). Lesson lookup is exact-string, so
# without this alias map their real curator notes would silently never
# attach, even though the notes exist and are about the same company.
RAW_EXPORT_NAME_ALIASES = {
    "Celldex Therapeutics": "Celldex Therapeutics, Inc.",
    "Kerry Inc.": "Kerry, Inc.",
    "Geron": "Geron Corporation",
}

# Below this many closed-won accounts backing the library, flag it as a thin
# sample in the output. Not a hard cutoff — the analysis on Geron + LEO
# Pharma (2 accounts) suggested something like 8-10 before patterns are
# trustworthy, so that's the line used here; it's just a label, not a gate
# that blocks suggestions from showing.
SMALL_LIBRARY_THRESHOLD = 8


def _gap_ratio(gap_days, typical_gap_days):
    if not typical_gap_days:
        return None
    return gap_days / typical_gap_days


def suggest_reengagement_examples(records, revival_library, as_of=None, top_n=DEFAULT_TOP_N, lessons_by_account=None):
    """records: filtered, chronologically sorted activities for ONE live
    account. revival_library: the flat list of revival-moment dicts from
    revival_library.build_revival_library (or its JSON output, loaded back).
    lessons_by_account: optional {account_name: [lesson_text, ...]}, from
    narrative_parser.extract_lessons — a rep's own account-history judgment
    (from the closed-won master doc) surfaced alongside a matching example,
    not just the mechanically-derived stats.

    Runs the staleness check; if the account isn't stalled or dormant,
    returns that status with no examples (there's nothing to suggest
    re-engaging about). If it is, ranks every library moment by how closely
    its gap-vs-typical-rhythm ratio matches the live account's own ratio, and
    returns the top `top_n` closest matches. ("dormant" is silence past the
    flat DORMANT_DAYS backstop, on top of "stalled" — see staleness.py — and
    gets examples too, since it needs re-engagement ideas at least as much.)
    """
    lessons_by_account = lessons_by_account or {}
    assessment = assess_staleness(records, as_of=as_of)
    accounts_in_library = sorted({m["account"] for m in revival_library if m.get("account")})

    result = {
        "staleness": assessment,
        "library_account_count": len(accounts_in_library),
        "library_accounts": accounts_in_library,
        "library_is_small_sample": len(accounts_in_library) < SMALL_LIBRARY_THRESHOLD,
        "live_gap_ratio": None,
        "examples": [],
    }

    if assessment["status"] not in ("stalled", "dormant"):
        return result

    live_ratio = _gap_ratio(assessment["days_since_last_touch"], assessment["typical_gap_days"])
    if live_ratio is None:
        return result
    result["live_gap_ratio"] = round(live_ratio, 2)

    candidates = []
    for moment in revival_library:
        ratio = _gap_ratio(moment.get("gap_days"), moment.get("typical_gap_days"))
        if ratio is None:
            continue
        candidates.append((abs(ratio - live_ratio), ratio, moment))
    candidates.sort(key=lambda c: c[0])

    result["examples"] = [
        {
            "account": moment["account"],
            "source": moment.get("source", "unknown"),
            "gap_days": moment["gap_days"],
            "typical_gap_days": moment["typical_gap_days"],
            "gap_ratio": round(ratio, 2),
            "ratio_difference_from_live": round(diff, 2),
            "revival_subject": moment.get("revival_subject"),
            "revival_excerpt": moment.get("revival_excerpt"),
            "days_to_next_response": moment.get("days_to_next_response"),
            "curator_notes": lessons_by_account.get(moment["account"], []),
        }
        for diff, ratio, moment in candidates[:top_n]
    ]
    return result


# Source labels shown next to each example so the reader knows how solid the
# underlying data is — a raw Salesforce export vs. a human-curated narrative
# that may have omitted routine touches (see revival_library.py /
# narrative_parser.py docstrings for why that distinction matters).
SOURCE_LABELS = {
    "raw_export": "raw export",
    "curated_narrative": "curated narrative — gaps may be sparser than real activity",
}


def format_suggestions_summary(result, account_name=None):
    lines = [format_staleness_summary(result["staleness"], account_name)]

    if result["staleness"]["status"] not in ("stalled", "dormant"):
        return lines[0]

    n = result["library_account_count"]
    if result["library_is_small_sample"]:
        accounts = ", ".join(result["library_accounts"]) if result["library_accounts"] else "none"
        lines.append(
            f"NOTE: reference library is a small sample — only {n} closed-won "
            f"account(s) ({accounts}). Treat what follows as examples to "
            f"consider, not a validated playbook. Expand the library before "
            f"leaning on this."
        )
    else:
        lines.append(f"Reference library: {n} closed-won accounts.")

    if not result["examples"]:
        lines.append("No comparable revival examples found in the library.")
        return "\n".join(lines)

    lines.append(
        f"Closest-matching revival examples by silence-vs-normal-rhythm ratio "
        f"(this account is at {result['live_gap_ratio']}x its typical gap):"
    )
    for i, ex in enumerate(result["examples"], 1):
        source_label = SOURCE_LABELS.get(ex["source"], ex["source"])
        lines.append(
            f"  {i}. [{ex['account']} -- {source_label}] {ex['gap_ratio']}x typical gap "
            f"({ex['gap_days']}d silence vs their {ex['typical_gap_days']}d norm) "
            f"-- \"{ex['revival_subject']}\" (got a response in {ex['days_to_next_response']}d)"
        )
        if ex["revival_excerpt"]:
            lines.append(f"     \"{ex['revival_excerpt']}\"")
        for note in ex.get("curator_notes", []):
            lines.append(f"     Rep's own note on this deal: {note}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mhtml_path", help="Path to the live account's .mhtml export")
    parser.add_argument("--library", required=True, help="Path to a revival library JSON file (from revival_library.py)")
    parser.add_argument("--account-name", help="Label to print alongside the summary")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument(
        "--narrative-doc", help="Optional path to the closed-won master .docx, to surface curator notes alongside matches"
    )
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

    html = extract_html_from_mhtml(args.mhtml_path)
    records = filter_and_sort_activities(parse_activities(html))
    result = suggest_reengagement_examples(records, revival_library, top_n=args.top_n, lessons_by_account=lessons_by_account)
    print(format_suggestions_summary(result, args.account_name))


if __name__ == "__main__":
    sys.exit(main())
