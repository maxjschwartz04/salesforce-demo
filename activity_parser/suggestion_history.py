"""
Gives the tracker a memory across runs, specifically so it can escalate a
"stalled" account's suggested email instead of recommending the same first
re-approach forever -- and only escalate when there's real evidence the
previous suggestion actually went out, not just because enough time passed.

Why this has to be a separate persisted file rather than derived from
Salesforce activity data: staleness.py's "stalled" status comes from days
since the last LOGGED activity of any kind, rep-sent outreach included. If
a rep sends and logs the re-approach email this tool suggests, that very
touch resets the clock -- the account stops looking stalled at all until
enough silence passes again. So there's no way to tell "we already tried
Script #1 and got silence" apart from "we've never tried anything" purely
from the CURRENT snapshot of Salesforce data; the evidence erases itself
the moment someone acts on it. This file is this tool's own record of what
it already suggested, kept independently of that.

Confirming a send, not just guessing from timing: an account coming back
"stalled" on a later run doesn't by itself prove the last suggestion was
sent and ignored -- it's equally consistent with "nobody ever sent it, and
time just kept passing." Salesforce's own activity export actually
captures enough to tell these apart: every logged email's real subject
line and body text (see parser.py's "subject" and "comments.raw_text"
fields) survive in the export, so if the rep sent and logged the exact
email this tool suggested, its subject line shows up verbatim in a later
activity record. So escalation here requires finding a LOGGED activity,
dated after the suggestion was made, whose subject contains the previously
suggested email's subject line -- not just "still stalled." Absent that
match, this keeps re-suggesting the same email rather than pretending a
follow-up makes sense to something that (as far as the data shows) was
never sent.

Model: one entry per account, {status, attempt_count,
last_suggested_subject, suggested_as_of}. Two-step per run (see
tracker.py's --suggestion-history):
  1. resolve_attempt_count(...) -- BEFORE picking this run's suggestion --
     decides the attempt count using only what was recorded last time:
       - Not "stalled" this run -> 0. Either it was never stalled, or it
         came back to a healthy cadence -- either way, a future stall
         starts a fresh escalation, not a continuation of an old one.
       - "Stalled" this run, wasn't last time -> 1. A new stall episode.
       - "Stalled" both times, and a logged activity dated after the
         previous suggestion matches its subject line -> increment. Real
         evidence the last suggestion went out and still got silence.
       - "Stalled" both times, no matching activity found -> stay at the
         same count. Nothing confirms the last suggestion was ever sent,
         so this isn't a new attempt -- it's the same one, still pending.
  2. record_suggestion(...) -- AFTER picking this run's suggestion --
     persists what was just suggested (subject line, "as of" date) so the
     NEXT run can look for evidence it was sent.

Usage:
    history = load_history(path)
    for row in rows:
        attempt_count = resolve_attempt_count(
            history, row["account"], row["actionable_status"], records, as_of=as_of
        )
        row["stalled_attempt_count"] = attempt_count
        # ... row["suggested_email"] = suggest_email_template(row) ...
        record_suggestion(
            history, row["account"], row["actionable_status"], attempt_count, row["suggested_email"], as_of=as_of
        )
    save_history(path, history)
"""

import json
import os
from datetime import date, datetime

from parser import parse_last_modified_date


def load_history(path):
    """Returns {} if the file doesn't exist yet (first run)."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_history(path, history):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _normalize_as_of(as_of):
    if as_of is None:
        return date.today()
    if isinstance(as_of, datetime):
        return as_of.date()
    return as_of


def _sent_since_last_suggestion(previous, records, as_of):
    """True if some logged activity, dated strictly after the day the
    previous suggestion was made, has a subject line containing that
    suggestion's real subject text -- i.e. real evidence it was sent."""
    subject = previous.get("last_suggested_subject")
    suggested_as_of_raw = previous.get("suggested_as_of")
    if not subject or not suggested_as_of_raw:
        return False
    cutoff = date.fromisoformat(suggested_as_of_raw)
    subject_lower = subject.lower()
    for record in records:
        activity_dt = parse_last_modified_date(record.get("last_modified_date"))
        if activity_dt is None or activity_dt.date() <= cutoff:
            continue
        if subject_lower in (record.get("subject") or "").lower():
            return True
    return False


def resolve_attempt_count(history, account, status, records, as_of=None):
    """Call BEFORE suggest_email_template -- decides the attempt count to
    use for THIS run's suggestion, based only on what was recorded as of
    the last run (does not mutate `history`; see record_suggestion for
    that)."""
    if status != "stalled":
        return 0

    previous = history.get(account)
    if previous is None or previous.get("status") != "stalled":
        return 1

    if _sent_since_last_suggestion(previous, records, _normalize_as_of(as_of)):
        return previous.get("attempt_count", 0) + 1
    return previous.get("attempt_count", 1)


def record_suggestion(history, account, status, attempt_count, suggested_email, as_of=None):
    """Call AFTER suggest_email_template -- persists what was just
    suggested so a LATER run can check whether it was actually sent.
    attempt_count: the value resolve_attempt_count returned for this row
    THIS run (not re-derived from history, which still holds last run's
    state at this point). suggested_email: the {id, subject, ...} dict
    suggest_email_template returned for this row this run (or None)."""
    if status != "stalled" or suggested_email is None:
        history[account] = {"status": status, "attempt_count": 0}
        return

    history[account] = {
        "status": status,
        "attempt_count": attempt_count,
        "last_suggested_subject": suggested_email["subject"],
        "suggested_as_of": _normalize_as_of(as_of).isoformat(),
    }
