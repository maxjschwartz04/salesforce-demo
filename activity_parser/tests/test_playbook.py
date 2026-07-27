from playbook import compose_starting_draft, match_plays, next_step_display, suggest_next_step


class TestMatchPlays:
    def test_nurture_only_triggers_personal_touch_play(self):
        row = {"sender_mix": {"had_non_nurture_contact": False}}
        ids = [p["id"] for p in match_plays(row)]
        assert "dormant_nurture_needs_personal_touch" in ids

    def test_rep_contact_present_does_not_trigger_nurture_play(self):
        row = {"sender_mix": {"had_non_nurture_contact": True}}
        ids = [p["id"] for p in match_plays(row)]
        assert "dormant_nurture_needs_personal_touch" not in ids

    def test_manual_personnel_check_always_shown(self):
        # This one is a reminder, never a detection -- must always appear
        # regardless of sender data, since we have no signal for it.
        for row in [{"sender_mix": None}, {"sender_mix": {"had_non_nurture_contact": True}}]:
            ids = [p["id"] for p in match_plays(row)]
            assert "personnel_change_check" in ids

    def test_no_sender_data_does_not_trigger_nurture_play(self):
        row = {"sender_mix": None}
        ids = [p["id"] for p in match_plays(row)]
        assert "dormant_nurture_needs_personal_touch" not in ids


class TestComposeStartingDraft:
    def test_returns_none_when_nothing_real_to_draw_from(self):
        row = {"sender_mix": {"had_non_nurture_contact": True}, "opportunity_status": None, "examples": []}
        # personnel_change_check always fires, so there IS a section -- this
        # documents that behavior rather than asserting total emptiness.
        draft = compose_starting_draft(row)
        assert draft is not None
        assert len(draft["draft_sections"]) == 1

    def test_includes_next_step_when_available(self):
        row = {
            "sender_mix": None,
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [],
        }
        draft = compose_starting_draft(row)
        assert any("confirm budget by June" in s for s in draft["draft_sections"])

    def test_includes_closest_example_excerpt(self):
        row = {
            "sender_mix": None,
            "opportunity_status": None,
            "examples": [
                {
                    "account": "Geron",
                    "source": "raw_export",
                    "revival_subject": "Congrats from AgencyIQ",
                    "revival_excerpt": "Congratulations on your promotion!",
                }
            ],
        }
        draft = compose_starting_draft(row)
        assert any("Congratulations on your promotion!" in s for s in draft["draft_sections"])
        assert any("Geron" in s for s in draft["draft_sections"])

    def test_every_draft_carries_the_edit_before_sending_note(self):
        row = {"sender_mix": None, "opportunity_status": None, "examples": []}
        draft = compose_starting_draft(row)
        assert "not a generated message" in draft["note"]


class TestSuggestNextStep:
    def _precedent(self, account="Geron", days=6.0):
        return {"account": account, "revival_subject": "Re: reconnect", "days_to_next_response": days}

    def test_returns_none_with_nothing_real_to_draw_from(self):
        row = {"opportunity_status": None, "examples": [], "staleness": {"days_since_last_touch": 50}}
        assert suggest_next_step(row) is None

    def test_combines_next_step_and_precedent(self):
        # Reads as a suggestion, not a citation -- no account name or
        # subject line in the sentence, just the rep's plan plus the real
        # response-time as a plain fact.
        row = {
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [self._precedent()],
            "staleness": {"days_since_last_touch": 90},
        }
        sentence = suggest_next_step(row)
        assert sentence.startswith("confirm budget by June")
        assert "6.0" in sentence
        assert "Geron" not in sentence
        assert "Re: reconnect" not in sentence

    def test_next_step_only_when_no_precedent(self):
        row = {
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [],
            "staleness": {"days_since_last_touch": 90},
        }
        sentence = suggest_next_step(row)
        assert sentence == "confirm budget by June"

    def test_precedent_only_when_no_next_step(self):
        row = {
            "opportunity_status": None,
            "examples": [self._precedent()],
            "staleness": {"days_since_last_touch": 90},
        }
        sentence = suggest_next_step(row)
        assert "6.0" in sentence
        assert "Geron" not in sentence
        assert "Reach out directly" in sentence


class TestNextStepDisplay:
    def test_on_pace_shows_raw_note(self):
        row = {
            "actionable_status": "on_pace",
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [],
            "staleness": {"days_since_last_touch": 10},
        }
        result = next_step_display(row)
        assert result == {"mode": "raw", "text": "confirm budget by June"}

    def test_on_pace_with_no_next_step_shows_nothing(self):
        row = {"actionable_status": "on_pace", "opportunity_status": None, "examples": [], "staleness": {}}
        assert next_step_display(row) == {"mode": "none", "text": None}

    def test_cooling_off_shows_blended_not_raw(self):
        row = {
            "actionable_status": "cooling_off",
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [{"account": "Geron", "revival_subject": "Re: reconnect", "days_to_next_response": 6.0}],
            "staleness": {"days_since_last_touch": 90},
        }
        result = next_step_display(row)
        assert result["mode"] == "blended"
        assert "confirm budget by June" in result["text"]
        assert "Geron" not in result["text"]

    def test_stalled_shows_blended_not_raw(self):
        row = {
            "actionable_status": "stalled",
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [],
            "staleness": {"days_since_last_touch": 90},
        }
        result = next_step_display(row)
        assert result["mode"] == "blended"

    def test_other_statuses_show_nothing(self):
        row = {
            "actionable_status": "insufficient_history",
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [],
            "staleness": {},
        }
        assert next_step_display(row) == {"mode": "none", "text": None}
