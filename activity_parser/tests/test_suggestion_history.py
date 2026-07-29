import json
from datetime import date

from suggestion_history import load_history, record_suggestion, resolve_attempt_count, save_history

EMAIL = {"id": "slow_track_reapproach", "subject": "AgencyIQ Updates – time to connect?"}


def activity(subject, last_modified_date):
    return {"subject": subject, "last_modified_date": last_modified_date}


class TestResolveAttemptCount:
    def test_first_time_stalled_is_attempt_one(self):
        assert resolve_attempt_count({}, "Acme", "stalled", []) == 1

    def test_non_stalled_status_is_zero(self):
        history = {"Acme": {"status": "stalled", "attempt_count": 2, "last_suggested_subject": "X", "suggested_as_of": "2026-01-01"}}
        assert resolve_attempt_count(history, "Acme", "on_pace", []) == 0

    def test_still_stalled_with_no_matching_activity_stays_at_same_count(self):
        # We suggested something last time but nothing in the export shows
        # it was ever sent -- don't pretend a second attempt happened.
        history = {
            "Acme": {
                "status": "stalled",
                "attempt_count": 1,
                "last_suggested_subject": EMAIL["subject"],
                "suggested_as_of": "2026-01-01",
            }
        }
        records = [activity("Email: unrelated check-in", "1/15/2026, 9:00 AM")]
        assert resolve_attempt_count(history, "Acme", "stalled", records) == 1

    def test_still_stalled_with_matching_activity_after_cutoff_increments(self):
        history = {
            "Acme": {
                "status": "stalled",
                "attempt_count": 1,
                "last_suggested_subject": EMAIL["subject"],
                "suggested_as_of": "2026-01-01",
            }
        }
        records = [activity(f"Email: {EMAIL['subject']}", "1/15/2026, 9:00 AM")]
        assert resolve_attempt_count(history, "Acme", "stalled", records) == 2

    def test_matching_activity_before_cutoff_does_not_count(self):
        # A historical send of the same subject line from BEFORE this
        # suggestion was made isn't evidence of THIS suggestion going out.
        history = {
            "Acme": {
                "status": "stalled",
                "attempt_count": 1,
                "last_suggested_subject": EMAIL["subject"],
                "suggested_as_of": "2026-01-15",
            }
        }
        records = [activity(f"Email: {EMAIL['subject']}", "1/10/2026, 9:00 AM")]
        assert resolve_attempt_count(history, "Acme", "stalled", records) == 1

    def test_matching_activity_on_cutoff_day_itself_does_not_count(self):
        history = {
            "Acme": {
                "status": "stalled",
                "attempt_count": 1,
                "last_suggested_subject": EMAIL["subject"],
                "suggested_as_of": "2026-01-15",
            }
        }
        records = [activity(f"Email: {EMAIL['subject']}", "1/15/2026, 9:00 AM")]
        assert resolve_attempt_count(history, "Acme", "stalled", records) == 1

    def test_unrelated_activity_after_cutoff_does_not_count_as_a_match(self):
        history = {
            "Acme": {
                "status": "stalled",
                "attempt_count": 1,
                "last_suggested_subject": EMAIL["subject"],
                "suggested_as_of": "2026-01-01",
            }
        }
        records = [activity("Email: Nick, reaching out from POLITICO Pro", "1/15/2026, 9:00 AM")]
        assert resolve_attempt_count(history, "Acme", "stalled", records) == 1

    def test_relapsing_into_stalled_after_a_reset_starts_over_at_one(self):
        history = {"Acme": {"status": "on_pace", "attempt_count": 0}}
        assert resolve_attempt_count(history, "Acme", "stalled", []) == 1

    def test_missing_last_suggested_subject_does_not_crash_or_escalate(self):
        history = {"Acme": {"status": "stalled", "attempt_count": 1}}
        records = [activity(f"Email: {EMAIL['subject']}", "1/15/2026, 9:00 AM")]
        assert resolve_attempt_count(history, "Acme", "stalled", records) == 1

    def test_accounts_are_tracked_independently(self):
        history = {
            "Acme": {
                "status": "stalled",
                "attempt_count": 2,
                "last_suggested_subject": EMAIL["subject"],
                "suggested_as_of": "2026-01-01",
            }
        }
        assert resolve_attempt_count(history, "Beta Corp", "stalled", []) == 1


class TestRecordSuggestion:
    def test_records_subject_and_as_of_for_stalled_account(self):
        history = {}
        record_suggestion(history, "Acme", "stalled", 1, EMAIL, as_of=date(2026, 1, 15))
        assert history["Acme"] == {
            "status": "stalled",
            "attempt_count": 1,
            "last_suggested_subject": EMAIL["subject"],
            "suggested_as_of": "2026-01-15",
        }

    def test_non_stalled_status_resets_and_drops_subject(self):
        history = {
            "Acme": {
                "status": "stalled",
                "attempt_count": 2,
                "last_suggested_subject": EMAIL["subject"],
                "suggested_as_of": "2026-01-01",
            }
        }
        record_suggestion(history, "Acme", "on_pace", 0, None)
        assert history["Acme"] == {"status": "on_pace", "attempt_count": 0}

    def test_stalled_with_no_suggested_email_resets(self):
        # Shouldn't happen in practice (stalled always gets a suggestion),
        # but stay safe rather than persist a subject that doesn't exist.
        history = {}
        record_suggestion(history, "Acme", "stalled", 1, None)
        assert history["Acme"] == {"status": "stalled", "attempt_count": 0}

    def test_full_round_trip_resolve_then_record_then_resolve_again(self):
        history = {}
        count1 = resolve_attempt_count(history, "Acme", "stalled", [])
        assert count1 == 1
        record_suggestion(history, "Acme", "stalled", count1, EMAIL, as_of=date(2026, 1, 1))

        # No evidence it was sent yet -- second run should NOT escalate.
        count2 = resolve_attempt_count(history, "Acme", "stalled", [])
        assert count2 == 1
        record_suggestion(history, "Acme", "stalled", count2, EMAIL, as_of=date(2026, 1, 1))

        # Now a matching send shows up in the export.
        records = [activity(f"Email: {EMAIL['subject']}", "1/20/2026, 9:00 AM")]
        count3 = resolve_attempt_count(history, "Acme", "stalled", records)
        assert count3 == 2


class TestLoadSaveHistory:
    def test_load_missing_file_returns_empty_dict(self, tmp_path):
        assert load_history(str(tmp_path / "nope.json")) == {}

    def test_load_none_path_returns_empty_dict(self):
        assert load_history(None) == {}

    def test_save_then_load_round_trips(self, tmp_path):
        path = str(tmp_path / "history.json")
        history = {"Acme": {"status": "stalled", "attempt_count": 2}}
        save_history(path, history)
        assert load_history(path) == history

    def test_saved_file_is_readable_plain_json(self, tmp_path):
        path = str(tmp_path / "history.json")
        save_history(path, {"Acme": {"status": "stalled", "attempt_count": 1}})
        with open(path, encoding="utf-8") as f:
            assert json.load(f) == {"Acme": {"status": "stalled", "attempt_count": 1}}
