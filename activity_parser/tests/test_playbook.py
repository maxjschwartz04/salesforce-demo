from playbook import compose_starting_draft, match_plays, suggest_next_step


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
        row = {
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [self._precedent()],
            "staleness": {"days_since_last_touch": 90},
        }
        sentence = suggest_next_step(row)
        assert "confirm budget by June" in sentence
        assert "90d" in sentence
        assert "Geron" in sentence
        assert "6.0d" in sentence

    def test_next_step_only_when_no_precedent(self):
        row = {
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [],
            "staleness": {"days_since_last_touch": 90},
        }
        sentence = suggest_next_step(row)
        assert "confirm budget by June" in sentence
        assert "Geron" not in sentence

    def test_precedent_only_when_no_next_step(self):
        row = {
            "opportunity_status": None,
            "examples": [self._precedent()],
            "staleness": {"days_since_last_touch": 90},
        }
        sentence = suggest_next_step(row)
        assert "Geron" in sentence
        assert "No logged next step" in sentence

    def test_never_replaces_missing_days_since_with_a_guess(self):
        row = {
            "opportunity_status": {"open_next_steps": ["confirm budget by June"]},
            "examples": [],
            "staleness": {},
        }
        sentence = suggest_next_step(row)
        assert "?d ago" in sentence
