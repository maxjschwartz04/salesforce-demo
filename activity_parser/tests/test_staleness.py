from datetime import date

from staleness import assess_staleness, format_staleness_summary


def record(last_modified_date):
    return {"last_modified_date": last_modified_date}


class TestAssessStaleness:
    def test_no_activity(self):
        result = assess_staleness([], as_of=date(2026, 1, 1))
        assert result["status"] == "no_activity"
        assert result["typical_gap_days"] is None

    def test_no_activity_when_all_dates_unparseable(self):
        result = assess_staleness([record(None), record("garbage")], as_of=date(2026, 1, 1))
        assert result["status"] == "no_activity"

    def test_insufficient_history_below_minimum_engagement_days(self):
        records = [record("1/1/2026, 12:00 PM"), record("1/2/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 1, 3))
        assert result["status"] == "insufficient_history"
        assert result["typical_gap_days"] is None
        assert result["days_since_last_touch"] == 1

    def test_on_pace_when_silence_within_threshold(self):
        # Touches every ~5 days -> typical gap 5, threshold 15. 3 days since
        # last touch is well within that.
        records = [
            record("1/1/2026, 12:00 PM"),
            record("1/6/2026, 12:00 PM"),
            record("1/11/2026, 12:00 PM"),
        ]
        result = assess_staleness(records, as_of=date(2026, 1, 14))
        assert result["status"] == "on_pace"
        assert result["typical_gap_days"] == 5.0
        assert result["threshold_days"] == 15.0

    def test_stalled_when_silence_exceeds_threshold(self):
        records = [
            record("1/1/2026, 12:00 PM"),
            record("1/6/2026, 12:00 PM"),
            record("1/11/2026, 12:00 PM"),
        ]
        # threshold is 15 days; put "today" 20 days past last touch
        result = assess_staleness(records, as_of=date(2026, 1, 31))
        assert result["status"] == "stalled"
        assert result["days_since_last_touch"] == 20

    def test_same_day_bursts_do_not_crush_median(self):
        # Regression: several records logged minutes apart on the same day
        # must collapse to ONE engagement day, not create near-zero gaps
        # that make the median (and therefore "stalled" threshold) tiny.
        records = [
            record("1/1/2026, 9:00 AM"),
            record("1/1/2026, 9:05 AM"),
            record("1/1/2026, 9:10 AM"),
            record("1/11/2026, 9:00 AM"),
            record("1/21/2026, 9:00 AM"),
        ]
        result = assess_staleness(records, as_of=date(2026, 1, 24))
        assert result["typical_gap_days"] == 10.0
        assert result["status"] == "on_pace"  # 3 days since last touch, threshold 30

    def test_as_of_accepts_datetime(self):
        from datetime import datetime

        records = [record("1/1/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=datetime(2026, 1, 5, 8, 30))
        assert result["last_touch_date"] == "2026-01-01"


class TestFormatStalenessSummary:
    def test_no_activity_message(self):
        result = {"status": "no_activity"}
        assert "no dated activity" in format_staleness_summary(result)

    def test_insufficient_history_message(self):
        result = {"status": "insufficient_history", "days_since_last_touch": 4}
        assert "not enough history" in format_staleness_summary(result)

    def test_stalled_includes_account_name_and_flag(self):
        result = {
            "status": "stalled",
            "typical_gap_days": 10.0,
            "days_since_last_touch": 100,
            "threshold_days": 30.0,
        }
        summary = format_staleness_summary(result, account_name="McKee")
        assert summary.startswith("McKee:")
        assert "STALLED" in summary

    def test_on_pace_flag(self):
        result = {
            "status": "on_pace",
            "typical_gap_days": 5.0,
            "days_since_last_touch": 2,
            "threshold_days": 15.0,
        }
        assert "ON PACE" in format_staleness_summary(result)
