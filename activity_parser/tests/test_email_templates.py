import pytest

from email_templates import suggest_email_template


def row(
    status,
    subscribed=True,
    attended=True,
    contacts=None,
    account="Acme Corp",
    examples=None,
    stalled_attempt_count=None,
    vertical=None,
):
    return {
        "actionable_status": status,
        "account": account,
        "contacts": contacts if contacts is not None else [{"first_name": "Jane"}],
        "subscribed_to_newsletter": subscribed,
        "attended_webinar": attended,
        "examples": examples if examples is not None else [{"account": "Geron Corporation"}],
        "stalled_attempt_count": stalled_attempt_count,
        "vertical": vertical,
    }


class TestSuggestEmailTemplate:
    def test_new_gets_no_suggestion(self):
        assert suggest_email_template(row("new")) is None

    def test_on_pace_gets_no_suggestion(self):
        assert suggest_email_template(row("on_pace")) is None

    def test_stalled_with_precedent_gets_slow_track_reapproach(self):
        # Not yet subscribed/attended (so the trial-offer branch doesn't
        # apply) -- an established relationship gone quiet, with a real
        # closed-won revival example backing it up, gets the "we've seen
        # this before" re-approach script, not a cold newsletter pitch.
        result = suggest_email_template(row("stalled", subscribed=False, attended=False))
        assert result["id"] == "slow_track_reapproach"

    def test_stalled_without_precedent_gets_product_feedback(self):
        # No matching closed-won revival example for this account, and
        # not yet subscribed/attended -- don't imply a precedent that
        # isn't there; ask for product feedback instead (a different real
        # script, not generated copy).
        result = suggest_email_template(row("stalled", subscribed=False, attended=False, examples=[]))
        assert result["id"] == "slow_track_product_feedback"

    def test_stalled_subscribed_and_attended_gets_webinar_reinvite_not_trial_offer(self):
        # Proven engagement that still went dark gets a forward-looking
        # re-invite, NOT the trial-offer script -- that script's real
        # wording ("thank you for subscribing... since you signed up")
        # asserts the subscribe was recent, which the underlying signal
        # (a lifetime yes/no flag, no date attached) can't actually back
        # up. Takes priority over the precedent check entirely, regardless
        # of what's in the revival library.
        result = suggest_email_template(row("stalled", subscribed=True, attended=True, examples=[]))
        assert result["id"] == "webinar_invite"

    def test_stalled_with_no_attempt_count_recorded_behaves_as_attempt_one(self):
        # Backward compatible: when suggestion_history isn't wired up (no
        # --suggestion-history passed), every stalled suggestion is still
        # a first attempt, same as before escalation existed.
        result = suggest_email_template(row("stalled", subscribed=True, attended=True, stalled_attempt_count=None))
        assert result["id"] == "webinar_invite"

    def test_stalled_second_attempt_after_reapproach_gets_determining_interest(self):
        # A second consecutive stalled suggestion, where attempt 1 would
        # have been the pricing-themed reapproach script, escalates to its
        # real documented sequel.
        result = suggest_email_template(
            row("stalled", subscribed=False, attended=False, examples=[{"account": "Geron"}], stalled_attempt_count=2)
        )
        assert result["id"] == "determining_interest"

    def test_stalled_second_attempt_after_webinar_reinvite_gets_trial_offer(self):
        # The gentle re-invite didn't land -- escalate to the stronger,
        # proven-engagement incentive script (real, and reserved for
        # exactly this point in the real library: a late-stage lever, not
        # a first move).
        result = suggest_email_template(
            row("stalled", subscribed=True, attended=True, examples=[{"account": "Geron"}], stalled_attempt_count=2)
        )
        assert result["id"] == "trial_offer"

    def test_stalled_second_attempt_after_product_feedback_gets_last_ditch_effort(self):
        result = suggest_email_template(
            row("stalled", subscribed=False, attended=False, examples=[], stalled_attempt_count=2)
        )
        assert result["id"] == "last_ditch_effort"

    def test_stalled_third_attempt_gets_breakup(self):
        result = suggest_email_template(row("stalled", stalled_attempt_count=3))
        assert result["id"] == "breakup"

    def test_stalled_attempt_beyond_three_still_gets_breakup(self):
        result = suggest_email_template(row("stalled", stalled_attempt_count=7))
        assert result["id"] == "breakup"

    def test_no_vertical_defaults_to_food(self):
        result = suggest_email_template(row("never_engaged", subscribed=False, vertical=None))
        assert result["vertical"] == "food"
        assert "food" in result["body"].lower()

    def test_life_sciences_vertical_uses_life_sciences_content(self):
        result = suggest_email_template(row("never_engaged", subscribed=False, vertical="life_sciences"))
        assert result["vertical"] == "life_sciences"
        assert "food" not in result["body"].lower()

    def test_unknown_vertical_suppresses_suggestion_regardless_of_status(self):
        # An account genuinely not determined to be Food or Life Sciences
        # (a law firm, consultancy, etc.) gets no suggestion at all --
        # better than guessing Food by default. Checked across every
        # status that would otherwise get one.
        for status in ("never_engaged", "cooling_off", "stalled"):
            assert suggest_email_template(row(status, vertical="unknown")) is None

    def test_unrecognized_vertical_raises_instead_of_silently_guessing_food(self):
        # A genuine typo/un-onboarded vertical is a caller bug to fix, not
        # something to quietly paper over by guessing Food (the old
        # behavior this replaces) -- "unknown" is the explicit way to say
        # "not determined."
        with pytest.raises(ValueError):
            suggest_email_template(row("never_engaged", subscribed=False, vertical="chemicals"))

    def test_life_sciences_stalled_escalation_stays_within_vertical(self):
        # Attempt 2 after a life-sciences reapproach should pull the
        # life-sciences Determining Interest script, not the Food one.
        result = suggest_email_template(
            row(
                "stalled",
                subscribed=False,
                attended=False,
                examples=[{"account": "Geron"}],
                stalled_attempt_count=2,
                vertical="life_sciences",
            )
        )
        assert result["id"] == "determining_interest"
        assert "food" not in result["body"].lower()

    def test_never_engaged_not_subscribed_gets_newsletter_invite(self):
        result = suggest_email_template(row("never_engaged", subscribed=False, attended=False))
        assert result["id"] == "newsletter_invite"

    def test_cooling_off_subscribed_but_no_webinar_gets_webinar_invite(self):
        result = suggest_email_template(row("cooling_off", subscribed=True, attended=False))
        assert result["id"] == "webinar_invite"

    def test_cooling_off_subscribed_and_attended_gets_followup_content(self):
        result = suggest_email_template(row("cooling_off", subscribed=True, attended=True))
        assert result["id"] == "followup_sample_content"

    def test_fills_real_first_name_and_account(self):
        result = suggest_email_template(row("never_engaged", subscribed=False, contacts=[{"first_name": "Priya"}]))
        assert "Priya" in result["body"]
        assert "Acme Corp" in result["body"]

    def test_falls_back_to_generic_greeting_with_no_contact_on_file(self):
        result = suggest_email_template(row("never_engaged", subscribed=False, contacts=[]))
        assert "Hi there," in result["body"]

    def test_source_attribution_is_present(self):
        # Every suggestion must cite which real script it came from -- not
        # generated prose passed off as a real template.
        for status in ("never_engaged", "cooling_off", "stalled"):
            result = suggest_email_template(row(status))
            assert result["source"]

    def test_source_script_placeholders_are_preserved_not_guessed(self):
        # [topic], [DATE & TIME], etc. are left as brackets for a rep to
        # fill in by hand, same as the source script -- never fabricated.
        result = suggest_email_template(row("cooling_off", subscribed=True, attended=False))
        assert "[DATE & TIME]" in result["body"]
        assert "[WEBINAR TITLE]" in result["body"]
