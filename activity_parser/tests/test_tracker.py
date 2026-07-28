from tracker import _actionable_status, check_recent_sender_mix, format_tracker_report


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


class TestFormatTrackerReportNextStep:
    """format_tracker_report reads the precomputed row["next_step_display"]
    (from playbook.next_step_display) rather than deciding raw vs. blended
    itself -- these test that wiring, not playbook's own logic (already
    covered by test_playbook.py)."""

    def _row(self, actionable_status, next_step_display, opportunity_status=None):
        return {
            "account": "Acme Corp",
            "result": {
                "staleness": {
                    "status": actionable_status,
                    "typical_gap_days": 10.0,
                    "days_since_last_touch": 40,
                    "threshold_days": 30.0,
                },
                "library_account_count": 0,
                "library_is_small_sample": True,
                "library_accounts": [],
                "examples": [],
                "live_gap_ratio": None,
            },
            "sender_mix": None,
            "opportunity_status": opportunity_status,
            "actionable_status": actionable_status,
            "recent_engagements": [],
            "next_step_display": next_step_display,
        }

    def test_blended_next_step_is_printed_for_cooling_off(self):
        row = self._row("cooling_off", {"mode": "blended", "text": "confirm budget by June"})
        report = format_tracker_report([row])
        assert "Suggested next step: confirm budget by June" in report
        assert "Rep's own last" not in report

    def test_raw_next_step_is_printed_for_on_pace(self):
        row = self._row("on_pace", {"mode": "raw", "text": "confirm budget by June"})
        report = format_tracker_report([row])
        assert 'Rep\'s own last "Next Step" note on the open deal: "confirm budget by June"' in report
        assert "Suggested next step" not in report

    def test_no_next_step_material_prints_neither_line(self):
        row = self._row("on_pace", {"mode": "none", "text": None})
        report = format_tracker_report([row])
        assert "Next Step" not in report
        assert "Suggested next step" not in report
