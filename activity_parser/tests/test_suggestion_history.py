import json

from suggestion_history import load_history, record_attempt, save_history


class TestRecordAttempt:
    def test_first_time_stalled_is_attempt_one(self):
        history = {}
        assert record_attempt(history, "Acme", "stalled") == 1
        assert history["Acme"] == {"status": "stalled", "attempt_count": 1}

    def test_still_stalled_next_run_increments(self):
        history = {"Acme": {"status": "stalled", "attempt_count": 1}}
        assert record_attempt(history, "Acme", "stalled") == 2

    def test_repeated_calls_keep_incrementing(self):
        history = {}
        for expected in (1, 2, 3, 4):
            assert record_attempt(history, "Acme", "stalled") == expected

    def test_non_stalled_status_resets_to_zero(self):
        history = {"Acme": {"status": "stalled", "attempt_count": 2}}
        assert record_attempt(history, "Acme", "on_pace") == 0
        assert history["Acme"]["attempt_count"] == 0

    def test_relapsing_into_stalled_after_a_reset_starts_over_at_one(self):
        history = {}
        record_attempt(history, "Acme", "stalled")
        record_attempt(history, "Acme", "stalled")
        record_attempt(history, "Acme", "on_pace")  # genuinely came back
        assert record_attempt(history, "Acme", "stalled") == 1

    def test_unknown_account_with_non_stalled_status_is_zero(self):
        history = {}
        assert record_attempt(history, "Brand New Co", "cooling_off") == 0

    def test_accounts_are_tracked_independently(self):
        history = {}
        record_attempt(history, "Acme", "stalled")
        record_attempt(history, "Acme", "stalled")
        assert record_attempt(history, "Beta Corp", "stalled") == 1
        assert history["Acme"]["attempt_count"] == 2


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
