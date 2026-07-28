from datetime import date, timedelta

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
        # Exactly NEW_LEAD_GRACE_DAYS (30) since the only touch -- still
        # "new," not yet "never_engaged" (strictly greater trips it).
        records = [record("1/1/2026, 12:00 PM"), record("1/2/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 2, 1))  # 30 days since 1/2
        assert result["days_since_last_touch"] == 30
        assert result["status"] == "new"

    def test_never_engaged_past_the_grace_period(self):
        # Silent longer than one normal follow-up cycle, but not old enough
        # to hit the flat Dormant backstop -- a real gap, but not "stalled"
        # (there was never a relationship here to go quiet on).
        records = [record("1/1/2026, 12:00 PM"), record("1/2/2026, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 2, 2))  # 31 days since 1/2
        assert result["days_since_last_touch"] == 31
        assert result["status"] == "never_engaged"

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

    def test_cooling_off_between_cooling_and_stalled_thresholds(self):
        # typical gap 5 -> cooling threshold 7.5, stalled threshold 15.
        # 10 days since last touch sits between the two.
        records = [
            record("1/1/2026, 12:00 PM"),
            record("1/6/2026, 12:00 PM"),
            record("1/11/2026, 12:00 PM"),
        ]
        result = assess_staleness(records, as_of=date(2026, 1, 21))
        assert result["status"] == "cooling_off"
        assert result["cooling_threshold_days"] == 7.5
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

    def test_dormant_when_extremely_stale_on_a_normal_rhythm(self):
        # Same 5-day-rhythm records as test_stalled_when_silence_exceeds_threshold,
        # but pushed well past the DORMANT_DAYS flat backstop — "recently
        # stalled" and "silent for well over a year" shouldn't read the same.
        records = [
            record("1/1/2026, 12:00 PM"),
            record("1/6/2026, 12:00 PM"),
            record("1/11/2026, 12:00 PM"),
        ]
        result = assess_staleness(records, as_of=date(2027, 2, 1))  # 386 days since last touch
        assert result["status"] == "dormant"

    def test_dormant_overrides_relative_math_via_flat_backstop(self):
        # A naturally slow cadence (~200-day gap) means relative math alone
        # would only call 400 days of silence "cooling_off" (its own
        # "stalled" threshold would be 600 days) -- but the flat 365-day
        # backstop means a slow-cadence account can't hide behind its own
        # rhythm forever.
        start = date(2024, 1, 1)
        touches = [start, start + timedelta(days=200), start + timedelta(days=400)]
        records = [record(d.strftime("%m/%d/%Y") + ", 12:00 PM") for d in touches]
        as_of = touches[-1] + timedelta(days=400)
        result = assess_staleness(records, as_of=as_of)
        assert result["typical_gap_days"] == 200.0
        assert result["status"] == "dormant"

    def test_dormant_overrides_never_engaged_via_flat_backstop(self):
        # Too few engagement days to trust a median gap, but the flat
        # backstop doesn't need one -- a sparse account silent for two years
        # shouldn't sit in "never_engaged" limbo forever.
        records = [record("1/1/2024, 12:00 PM"), record("1/2/2024, 12:00 PM")]
        result = assess_staleness(records, as_of=date(2026, 1, 1))
        assert result["status"] == "dormant"
        assert result["typical_gap_days"] is None


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
            "threshold_days": 30.0,
        }
        summary = format_staleness_summary(result, account_name="McKee")
        assert summary.startswith("McKee:")
        assert "STALLED" in summary

    def test_cooling_off_flag(self):
        result = {
            "status": "cooling_off",
            "typical_gap_days": 5.0,
            "days_since_last_touch": 10,
            "threshold_days": 15.0,
        }
        assert "COOLING OFF" in format_staleness_summary(result)

    def test_on_pace_flag(self):
        result = {
            "status": "on_pace",
            "typical_gap_days": 5.0,
            "days_since_last_touch": 2,
            "threshold_days": 15.0,
        }
        assert "ON PACE" in format_staleness_summary(result)

    def test_dormant_flag(self):
        result = {
            "status": "dormant",
            "typical_gap_days": 5.0,
            "days_since_last_touch": 400,
            "threshold_days": 15.0,
        }
        assert "DORMANT" in format_staleness_summary(result)

    def test_dormant_message_without_established_rhythm(self):
        result = {"status": "dormant", "typical_gap_days": None, "days_since_last_touch": 500}
        summary = format_staleness_summary(result)
        assert "not enough history" in summary
        assert "DORMANT" in summary
