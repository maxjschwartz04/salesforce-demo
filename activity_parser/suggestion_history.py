"""
Gives the tracker a memory across runs, specifically so it can escalate a
"stalled" account's suggested email instead of recommending the same first
re-approach forever.

Why this has to be a separate persisted file rather than derived from
Salesforce activity data: staleness.py's "stalled" status comes from days
since the last LOGGED activity of any kind, rep-sent outreach included. If
a rep sends and logs the re-approach email this tool suggests, that very
touch resets the clock -- the account stops looking stalled at all until
enough silence passes again. So there's no way to tell "we already tried
Script #1 and got silence" apart from "we've never tried anything" purely
from the Salesforce export; the evidence erases itself the moment someone
acts on it. This file is this tool's own record of what it already
suggested, kept independently of that.

Model: one entry per account, {status, attempt_count}. Each run, every
tracked account gets recorded via record_attempt() based on its CURRENT
actionable_status:
  - Not "stalled" this run -> reset to 0. Either it was never stalled, or
    it came back to a healthy cadence -- either way, a future stall starts
    a fresh escalation, not a continuation of an old one.
  - "Stalled" this run, and it was ALSO "stalled" the last time this file
    was updated -> increment. Nothing resolved it in between, so this is
    another cycle of the same unresolved silence.
  - "Stalled" this run, but wasn't last time -> 1. A new stall episode.

Usage (see tracker.py's --suggestion-history):
    history = load_history(path)
    for row in rows:
        row["stalled_attempt_count"] = record_attempt(history, row["account"], row["actionable_status"])
    save_history(path, history)
"""

import json
import os


def load_history(path):
    """Returns {} if the file doesn't exist yet (first run)."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_history(path, history):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def record_attempt(history, account, status):
    """Mutates `history` in place for this account and returns the attempt
    count to use for THIS run's suggestion (0 if not currently stalled)."""
    previous = history.get(account, {})

    if status != "stalled":
        attempt_count = 0
    elif previous.get("status") == "stalled":
        attempt_count = previous.get("attempt_count", 0) + 1
    else:
        attempt_count = 1

    history[account] = {"status": status, "attempt_count": attempt_count}
    return attempt_count
