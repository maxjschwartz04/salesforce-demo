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

    def test_new_when_recently_touched_below_minimum_engagement_days(self):
        # Too few engagement days to trust a median gap, but touched
        # recently -- too early to have an opinion, not a concern.
        records = [record("1/1/2026, 12:00 PM"), record("1/2/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 1, 3))
        assert result["status"] == "new"
        assert result["typical_gap_days"] is None
        assert result["days_since_last_touch"] == 1

    def test_new_at_exactly_the_grace_period_boundary(self):
        # Exactly NEW_LEAD_GRACE_DAYS (7) since the only touch -- still
        # "new," not yet "never_engaged" (strictly greater trips it).
        records = [record("1/1/2026, 12:00 PM"), record("1/2/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 1, 9))  # 7 days since 1/2
        assert result["days_since_last_touch"] == 7
        assert result["status"] == "new"

    def test_never_engaged_past_the_grace_period(self):
        # Silent longer than one normal follow-up cycle -- a real gap, but
        # not "stalled" (there was never a relationship here to go quiet
        # on). No ceiling anymore -- see test_never_engaged_has_no_ceiling.
        records = [record("1/1/2026, 12:00 PM"), record("1/2/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 1, 10))  # 8 days since 1/2
        assert result["days_since_last_touch"] == 8
        assert result["status"] == "never_engaged"

    def test_never_engaged_has_no_ceiling(self):
        # No "dormant" tier anymore (see staleness.py module docstring) --
        # a sparse account silent for years just stays "never_engaged"
        # rather than escalating to a separate status.
        records = [record("1/1/2024, 12:00 PM"), record("1/2/2024, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 1, 1))
        assert result["status"] == "never_engaged"
        assert result["typical_gap_days"] is None

    def test_on_pace_within_flat_cooling_off_threshold(self):
        # Flat thresholds now, not relative to this account's own rhythm --
        # a 3-day typical gap doesn't shrink the on-pace window.
        records = [
            record("1/1/2026, 12:00 PM"),
            record("1/6/2026, 12:00 PM"),
            record("1/11/2026, 12:00 PM"),
        ]
        result = assess_staleness(records, as_of=date(2026, 1, 20))  # 9 days since last touch
        assert result["status"] == "on_pace"
        assert result["typical_gap_days"] == 5.0
        assert result["threshold_days"] == 21
        assert result["cooling_threshold_days"] == 14

    def test_cooling_off_between_flat_thresholds(self):
        records = [
            record("1/1/2026, 12:00 PM"),
            record("1/6/2026, 12:00 PM"),
            record("1/11/2026, 12:00 PM"),
        ]
        result = assess_staleness(records, as_of=date(2026, 1, 30))  # 19 days since last touch
        assert result["status"] == "cooling_off"

    def test_stalled_past_flat_threshold(self):
        records = [
            record("1/1/2026, 12:00 PM"),
            record("1/6/2026, 12:00 PM"),
            record("1/11/2026, 12:00 PM"),
        ]
        result = assess_staleness(records, as_of=date(2026, 2, 5))  # 25 days since last touch
        assert result["status"] == "stalled"
        assert result["days_since_last_touch"] == 25

    def test_slow_cadence_account_no_longer_hides_behind_its_own_rhythm(self):
        # The old relative-multiplier system would have called this
        # "on_pace" (9 days is well under 3x a 200-day typical gap) --
        # flat thresholds mean it can't hide behind a naturally slow
        # history anymore.
        records = [
            record("1/1/2024, 12:00 PM"),
            record("7/19/2024, 12:00 PM"),
            record("2/4/2025, 12:00 PM"),
        ]
        result = assess_staleness(records, as_of=date(2025, 2, 28))  # 24 days since last touch
        assert result["typical_gap_days"] == 200.0
        assert result["status"] == "stalled"

    def test_same_day_bursts_do_not_crush_median(self):
        # Regression: several records logged minutes apart on the same day
        # must collapse to ONE engagement day. typical_gap_days is now
        # descriptive only, but should still reflect real rhythm.
        records = [
            record("1/1/2026, 9:00 AM"),
            record("1/1/2026, 9:05 AM"),
            record("1/1/2026, 9:10 AM"),
            record("1/11/2026, 9:00 AM"),
            record("1/21/2026, 9:00 AM"),
        ]
        result = assess_staleness(records, as_of=date(2026, 1, 24))
        assert result["typical_gap_days"] == 10.0
        assert result["status"] == "on_pace"  # 3 days since last touch, well under 14

    def test_as_of_accepts_datetime(self):
        from datetime import datetime

        records = [record("1/1/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=datetime(2026, 1, 5, 8, 30))
        assert result["last_touch_date"] == "2026-01-01"


class TestFormatStalenessSummary:
    def test_no_activity_message(self):
        result = {"status": "no_activity"}
        assert "no dated activity" in format_staleness_summary(result)

    def test_new_message(self):
        result = {"status": "new", "days_since_last_touch": 4}
        summary = format_staleness_summary(result)
        assert "too new" in summary
        assert "NEW" in summary

    def test_never_engaged_message(self):
        result = {"status": "never_engaged", "days_since_last_touch": 45}
        summary = format_staleness_summary(result)
        assert "no real conversation" in summary
        assert "NEVER ENGAGED" in summary

    def test_stalled_includes_account_name_and_flag(self):
        result = {
            "status": "stalled",
            "typical_gap_days": 10.0,
            "days_since_last_touch": 100,
            "threshold_days": 21,
        }
        summary = format_staleness_summary(result, account_name="McKee")
        assert summary.startswith("McKee:")
        assert "STALLED" in summary

    def test_cooling_off_flag(self):
        result = {
            "status": "cooling_off",
            "typical_gap_days": 5.0,
            "days_since_last_touch": 16,
            "threshold_days": 21,
        }
        assert "COOLING OFF" in format_staleness_summary(result)

    def test_on_pace_flag(self):
        result = {
            "status": "on_pace",
            "typical_gap_days": 5.0,
            "days_since_last_touch": 2,
            "threshold_days": 21,
        }
        assert "ON PACE" in format_staleness_summary(result)
