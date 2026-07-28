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
just the action to take (the rep's own logged plan, or "Reach out
directly" if a precedent exists but there's no logged plan) — never
generated prose (see NEXT_STEP_TEMPLATES). It deliberately does NOT cite
the precedent's response time inline; that comparison already has its own
dedicated spot elsewhere on the same screen (the closest revival
example's account/subject/response-time), so repeating it here would just
say the same thing twice. next_step_display() decides, per account, which
of three things to show: the raw note as-is where it's still trustworthy
(on_pace, and never_engaged if a plan happens to exist), the blended
sentence above where a relationship went quiet (cooling_off/stalled/
dormant), or a distinct first-outreach prompt where there was never a
relationship to begin with (never_engaged with no logged plan) — never
more than one of the three, since the blended sentence already quotes the
raw note verbatim.

Usage:
    from playbook import match_plays, compose_starting_draft, suggest_next_step, next_step_display
"""

from datetime import datetime

from campaign_parser import parse_date_group_start

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
#
# Deliberately doesn't cite the precedent's response time here anymore --
# that comparison already lives in its own dedicated place (the "Closest
# Revival Precedent" block / format_suggestions_summary's examples list),
# so repeating "in one comparable case, that got a reply in 6 days" here
# was just saying the same thing twice in two different spots on the same
# screen. This is the ACTION, full stop; the evidence for it is shown
# separately, once.
NEXT_STEP_TEMPLATES = {
    "next_step_only": "{next_step}",
    "precedent_only": "Reach out directly.",
}

# Appended (not blended in as a fill-in blank) when real Campaign Member
# data shows this account attended a webinar, opened a newsletter, etc.
# more recently than its last logged sales activity -- i.e. they've gone
# quiet on direct conversation but haven't disengaged from the brand
# entirely. Deliberately doesn't change the staleness status itself (see
# staleness.py / campaign_parser.py module docstrings: sales-conversation
# gaps and marketing engagement are kept as separate signals on purpose,
# since marketing engagement alone isn't proof the sales relationship is
# active) -- this only adjusts the TONE of the suggestion for accounts
# that are warmer than a total absence of any engagement.
#
# "is likely to land" was a prediction this data can't back up -- a
# webinar RSVP says they haven't tuned out entirely, not that a personal
# note will work. Recommend the action, don't promise the outcome.
STILL_MARKETING_ENGAGED_CLAUSE = (
    " They've kept engaging with your webinars and emails, though — worth a personal note instead of another automated touch."
)

# For "never_engaged" accounts (see staleness.py's NEW_LEAD_GRACE_DAYS) with
# no logged rep plan to fall back on. Deliberately NOT "Reach out directly"
# (the precedent_only phrasing above) -- that implies a relationship that
# went quiet, which isn't what happened here. There's also no revival
# precedent to speak of: suggest_reengagement_examples only builds examples
# for "stalled"/"dormant," so this account never gets any.
FIRST_OUTREACH_MESSAGE = "No real conversation on file yet — worth a first outreach."


def _still_marketing_engaged(row):
    """True if this account has a real Campaign Member touch more recent
    than its last logged sales activity. row needs 'recent_engagements'
    (from campaign_parser.get_recent_engagements) and 'staleness' (from
    staleness.assess_staleness, for last_touch_date) to say anything --
    returns False rather than guessing if either is missing."""
    engagements = row.get("recent_engagements") or []
    last_touch_raw = (row.get("staleness") or {}).get("last_touch_date")
    if not engagements or not last_touch_raw:
        return False
    last_touch = datetime.strptime(last_touch_raw, "%Y-%m-%d")
    engagement_dates = [d for d in (parse_date_group_start(e.get("date_group")) for e in engagements) if d is not None]
    return bool(engagement_dates) and max(engagement_dates) > last_touch


def suggest_next_step(row):
    """A short, direct action -- the rep's own last logged plan if there is
    one, or "Reach out directly" if a closed-won precedent exists but
    there's no logged plan to lean on. Deliberately just the action: the
    evidence for it (the closest revival precedent's account, subject, and
    response time) is shown in its own dedicated place elsewhere on the
    same screen, not repeated here as a citation tacked onto the
    suggestion.

    Deliberately NOT generated prose: only the fixed sentence shapes in
    NEXT_STEP_TEMPLATES are used. Returns None if there's neither a next
    step nor a precedent to build from — never fabricates a sentence to
    fill the gap.

    If real Campaign Member data shows this account engaging with
    webinars/newsletters more recently than its last logged sales touch
    (see _still_marketing_engaged), STILL_MARKETING_ENGAGED_CLAUSE is
    appended — the account is warmer than one with zero engagement of any
    kind, so the suggestion says so. This never changes the staleness
    status itself, and never appears on its own with nothing else real to
    say."""
    opp_status = row.get("opportunity_status") or {}
    next_step = (opp_status.get("open_next_steps") or [None])[0]

    has_precedent = bool(row.get("examples"))

    if next_step:
        sentence = NEXT_STEP_TEMPLATES["next_step_only"].format(next_step=next_step)
    elif has_precedent:
        sentence = NEXT_STEP_TEMPLATES["precedent_only"]
    else:
        return None

    if _still_marketing_engaged(row):
        sentence += STILL_MARKETING_ENGAGED_CLAUSE
    return sentence


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
      - "never_engaged": no established relationship to judge a note's
        staleness against, so a logged plan (rare, but possible) is shown
        as-is like on_pace. With no logged plan, show FIRST_OUTREACH_MESSAGE
        instead of the blended precedent-based sentence — there's no
        precedent for a lead that's never had a real second touch.
      - anything else: no next-step material to show.

    Returns {"mode": "raw" | "blended" | "first_outreach" | "none", "text": str | None}."""
    status = row.get("actionable_status")
    opp_status = row.get("opportunity_status") or {}
    next_step = (opp_status.get("open_next_steps") or [None])[0]

    if status == "on_pace":
        return {"mode": "raw", "text": next_step} if next_step else {"mode": "none", "text": None}

    if status == "never_engaged":
        if next_step:
            return {"mode": "raw", "text": next_step}
        return {"mode": "first_outreach", "text": FIRST_OUTREACH_MESSAGE}

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
