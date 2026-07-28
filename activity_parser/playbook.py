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

suggest_next_step() is a smaller, one-sentence version of the same idea:
the rep's own Next Step note is a snapshot from whenever they last touched
the account, so showing it alone can read as current advice when it's
actually stale. This pairs it with the closest closed-won precedent using
a fixed, editable sentence template (see NEXT_STEP_TEMPLATES) — never
generated prose. next_step_display() decides, per account, whether the
raw note is still trustworthy on its own (on_pace) or should be shown as
the blended sentence instead (cooling_off/stalled) — not both, since the
blended sentence already quotes the raw note verbatim.

Usage:
    from playbook import match_plays, compose_starting_draft, suggest_next_step, next_step_display
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



# Fill-in-the-blank sentence shapes, not generated prose -- same "your team
# edits this, not a model" principle as PLAYS above. Reads as a suggestion,
# not a citation -- no account names or subject lines named in the sentence
# itself (that's what made earlier drafts read like a footnote explaining
# where the suggestion came from rather than just making the suggestion).
# Which shape gets used depends on which real fields actually exist for
# this account; a blank with nothing real to put in it just isn't filled
# in, never invented.
NEXT_STEP_TEMPLATES = {
    "next_step_and_precedent": (
        "{next_step} — similarly quiet accounts have come back {response_time_phrase} once someone reached out directly."
    ),
    "next_step_only": "{next_step}",
    "precedent_only": ("Reach out directly — similarly quiet accounts have come back {response_time_phrase} once someone did."),
}


def _response_time_phrase(days):
    """Turns a raw response-time number into a phrase that reads naturally
    at any value -- "within about 6 days" is fine, but the raw number
    reads oddly at the extremes real data actually has: same-day replies
    (0.0, and these are common -- roughly a third of real precedents in
    this library) and long fractional gaps (e.g. 104.21) that don't need
    two decimal places to make the point."""
    if days is None:
        return "eventually"
    if days < 1:
        return "the same day"
    if days < 1.5:
        return "within a day"
    return f"within about {round(days)} days"


def suggest_next_step(row):
    """A one-sentence, template-filled suggestion that leads with the rep's
    own last logged plan and, where a closed-won precedent exists, folds in
    its real response-time as a plain suggestion — not a citation, so the
    sentence doesn't name which account or email it came from.

    Deliberately NOT generated prose: only the fixed sentence shapes in
    NEXT_STEP_TEMPLATES are used, and every blank is a real field pulled
    from this account's own data. Returns None if there's neither a next
    step nor a precedent to build from — never fabricates a sentence to
    fill the gap."""
    opp_status = row.get("opportunity_status") or {}
    next_step = (opp_status.get("open_next_steps") or [None])[0]

    examples = row.get("examples") or []
    precedent = examples[0] if examples else None

    if next_step and precedent:
        return NEXT_STEP_TEMPLATES["next_step_and_precedent"].format(
            next_step=next_step,
            response_time_phrase=_response_time_phrase(precedent.get("days_to_next_response")),
        )
    if next_step:
        return NEXT_STEP_TEMPLATES["next_step_only"].format(next_step=next_step)
    if precedent:
        return NEXT_STEP_TEMPLATES["precedent_only"].format(
            response_time_phrase=_response_time_phrase(precedent.get("days_to_next_response")),
        )
    return None


def next_step_display(row):
    """Decides which next-step material is actually worth showing, based on
    how stale the rep's own note is likely to be:

      - "on_pace": the account is being touched on its own normal rhythm,
        so the rep's raw note is still probably current — show it as-is.
      - "cooling_off" / "stalled" / "dormant": the note is a snapshot from
        whenever the account was last touched, which by definition is
        longer ago than normal — show the blended one-sentence version
        instead. That sentence already quotes the raw note verbatim, so
        showing both would just repeat the same text twice.
      - anything else: no next-step material to show.

    Returns {"mode": "raw" | "blended" | "none", "text": str | None}."""
    status = row.get("actionable_status")
    opp_status = row.get("opportunity_status") or {}
    next_step = (opp_status.get("open_next_steps") or [None])[0]

    if status == "on_pace":
        return {"mode": "raw", "text": next_step} if next_step else {"mode": "none", "text": None}

    if status in ("cooling_off", "stalled", "dormant"):
        blended = suggest_next_step(row)
        return {"mode": "blended", "text": blended} if blended else {"mode": "none", "text": None}

    return {"mode": "none", "text": None}


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
