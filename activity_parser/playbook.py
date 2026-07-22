"""
A CUSTOMIZABLE, EDITABLE set of "plays" derived from the closed-won master
doc's own curator lessons — not a scored recommender. See extract_lessons()
in narrative_parser.py for where these came from.

Two design choices, both deliberate:

1. PLAYS is a plain list you edit directly, not a model making judgment
   calls. Each play has a `trigger` (a function that checks the account's
   own data — no guessing) and `guidance` (a fact + a suggestion to
   *consider*, not an instruction). Add, remove, or reword plays here as
   your team learns more — that's what "customizable" should mean: you
   control the playbook, not a black box.

2. Only ONE of the two patterns found in the master doc is auto-triggered
   (dormant-nurture-vs-personal-touch — check_recent_sender_mix already
   gives us that signal from real data). The other (personnel/role-change
   outreach) can't be detected from Salesforce data at all — it needs
   LinkedIn/news, which we don't have. That play is included as a
   standing REMINDER to manually check, not a fake detection. Don't
   "solve" this by making up a trigger for it; leave it honest.

compose_starting_draft() assembles a draft from REAL material — the
closest revival example's actual excerpt, the rep's own Next Step note —
never generated prose making a new claim. It's explicitly labeled a
starting point for a human to edit, not a finished message, and there is
no send capability anywhere in this codebase.

Usage:
    from playbook import match_plays, compose_starting_draft
"""

PLAYS = [
    {
        "id": "dormant_nurture_needs_personal_touch",
        "name": "Dormant nurture -> personal touch",
        "source": (
            "Closed-won master doc: named across 7+ accounts (Eurofins, AVEO, Arcturus, "
            "BridgeBio, Amicus, Mereo, Biohaven) — automated newsletter/webinar sends ran "
            "for months with no response; the deal moved only once the rep personally "
            "reached out."
        ),
        "trigger": lambda row: bool(row.get("sender_mix")) and row["sender_mix"]["had_non_nurture_contact"] is False,
        "guidance": (
            "Recent touches on this account were all from the known nurture/marketing list, "
            "not a named rep. In similar accounts, automated sends alone didn't restart the "
            "relationship — a personal note did."
        ),
    },
    {
        "id": "personnel_change_check",
        "name": "Personnel/role-change check (manual — not detectable from this data)",
        "source": (
            'Closed-won master doc: Casey Miles\' own note on Mammoth Biosciences calls this '
            '"a pattern seen on a few Casey Miles accounts," not incidental.'
        ),
        "trigger": lambda row: True,  # always shown as a reminder, never auto-detected
        "guidance": (
            "Worth a quick LinkedIn/news check on this account's contact before reaching "
            "out — a promotion or role change has been a deliberate, effective re-engagement "
            "hook on other accounts. This tool has no way to detect that itself."
        ),
        "always_manual": True,
    },
]


def match_plays(row):
    """row: a tracker.py row dict (needs 'sender_mix' if present). Returns
    the subset of PLAYS whose trigger fires for this account — always
    includes the manual-check play, since it's a reminder, not a detection."""
    return [play for play in PLAYS if play["trigger"](row)]


def compose_starting_draft(row):
    """Assembles a starting draft from REAL material already surfaced for
    this account — the closest revival example's actual excerpt and/or the
    rep's own Next Step note. Returns None if there's nothing real to draw
    from (never fabricates content to fill the gap).

    This is explicitly a starting point, not a finished message — every
    section is labeled with where it came from so a rep edits knowing
    exactly what's real and what's a placeholder.
    """
    sections = []

    opp_status = row.get("opportunity_status")
    if opp_status and opp_status.get("open_next_steps"):
        sections.append(
            "[Your team's own last plan for this account — start here if it's still relevant]\n"
            + opp_status["open_next_steps"][0]
        )

    examples = row.get("examples") or []
    if examples:
        best = examples[0]
        sections.append(
            f"[Adapted from a real re-engagement on {best['account']} ({best['source']}) — "
            f"edit before sending, this is someone else's deal, not this one]\n"
            f'Subject inspiration: "{best["revival_subject"]}"\n'
            f"{best.get('revival_excerpt') or '(no excerpt available)'}"
        )

    plays = match_plays(row)
    for play in plays:
        sections.append(f"[Play: {play['name']}]\n{play['guidance']}")

    if not sections:
        return None

    return {
        "draft_sections": sections,
        "plays_applied": [p["id"] for p in plays],
        "note": "This is a starting point assembled from real account history, not a generated message — read every bracketed section before sending anything.",
    }
