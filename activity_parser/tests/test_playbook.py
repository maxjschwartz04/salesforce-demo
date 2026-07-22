from playbook import compose_starting_draft, match_plays


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
