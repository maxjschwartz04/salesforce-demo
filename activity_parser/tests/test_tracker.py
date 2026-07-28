from tracker import _actionable_status, check_recent_sender_mix


class TestActionableStatus:
    def test_stalled_with_open_opportunity_stays_stalled(self):
        opp_status = {"has_open_opportunity": True}
        assert _actionable_status("stalled", opp_status) == "stalled"

    def test_stalled_with_all_closed_opportunities_becomes_not_actionable(self):
        # Regression: this is the exact McKee case — gap math says stalled,
        # but the real Opportunity is Closed Lost, so it must NOT show as a
        # live re-engagement candidate.
        opp_status = {"has_open_opportunity": False}
        assert _actionable_status("stalled", opp_status) == "closed_not_actionable"

    def test_stalled_with_unknown_opportunity_status_stays_stalled(self):
        # No Opportunity data available for this account at all -> trust
        # the gap math rather than silently suppressing it.
        assert _actionable_status("stalled", None) == "stalled"

    def test_on_pace_unaffected_by_opportunity_status(self):
        opp_status = {"has_open_opportunity": False}
        assert _actionable_status("on_pace", opp_status) == "on_pace"

    def test_insufficient_history_passes_through(self):
        assert _actionable_status("insufficient_history", None) == "insufficient_history"

    def test_cooling_off_with_open_opportunity_stays_cooling_off(self):
        opp_status = {"has_open_opportunity": True}
        assert _actionable_status("cooling_off", opp_status) == "cooling_off"

    def test_cooling_off_with_all_closed_opportunities_becomes_not_actionable(self):
        opp_status = {"has_open_opportunity": False}
        assert _actionable_status("cooling_off", opp_status) == "closed_not_actionable"

    def test_dormant_with_open_opportunity_stays_dormant(self):
        opp_status = {"has_open_opportunity": True}
        assert _actionable_status("dormant", opp_status) == "dormant"

    def test_dormant_with_all_closed_opportunities_becomes_not_actionable(self):
        opp_status = {"has_open_opportunity": False}
        assert _actionable_status("dormant", opp_status) == "closed_not_actionable"


class TestCheckRecentSenderMix:
    def _record(self, date, assigned_to):
        return {"last_modified_date": date, "assigned_to": assigned_to}

    def test_empty_nurture_list_returns_none(self):
        records = [self._record("1/1/2026, 12:00 PM", "Casey Miles")]
        assert check_recent_sender_mix(records, []) is None

    def test_all_recent_touches_from_nurture_list(self):
        records = [
            self._record("1/1/2026, 12:00 PM", "Anastasiia Romanova"),
            self._record("1/2/2026, 12:00 PM", "Noah Hess"),
        ]
        result = check_recent_sender_mix(records, ["Anastasiia Romanova", "Noah Hess"])
        assert result["had_non_nurture_contact"] is False

    def test_a_non_nurture_contact_present(self):
        records = [
            self._record("1/1/2026, 12:00 PM", "Anastasiia Romanova"),
            self._record("1/2/2026, 12:00 PM", "Casey Miles"),
        ]
        result = check_recent_sender_mix(records, ["Anastasiia Romanova", "Noah Hess"])
        assert result["had_non_nurture_contact"] is True

    def test_nurture_name_matching_is_case_insensitive(self):
        records = [self._record("1/1/2026, 12:00 PM", "anastasiia romanova")]
        result = check_recent_sender_mix(records, ["Anastasiia Romanova"])
        assert result["had_non_nurture_contact"] is False

    def test_no_dated_or_assigned_records_returns_none(self):
        records = [{"last_modified_date": None, "assigned_to": "Casey Miles"}]
        assert check_recent_sender_mix(records, ["Noah Hess"]) is None

    def test_only_looks_at_most_recent_touches(self):
        # 6 touches, lookback window is 5 -> the oldest (non-nurture) one
        # should be excluded from consideration.
        records = [self._record(f"1/{i}/2026, 12:00 PM", name) for i, name in enumerate(
            ["Casey Miles", "Noah Hess", "Noah Hess", "Noah Hess", "Noah Hess", "Noah Hess"], start=1
        )]
        result = check_recent_sender_mix(records, ["Noah Hess"])
        assert result["had_non_nurture_contact"] is False
        assert result["checked_touch_count"] == 5
