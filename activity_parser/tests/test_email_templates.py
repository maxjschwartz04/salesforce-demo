from email_templates import suggest_email_template


def row(status, subscribed=True, attended=True, contacts=None, account="Acme Corp", examples=None):
    return {
        "actionable_status": status,
        "account": account,
        "contacts": contacts if contacts is not None else [{"first_name": "Jane"}],
        "subscribed_to_newsletter": subscribed,
        "attended_webinar": attended,
        "examples": examples if examples is not None else [{"account": "Geron Corporation"}],
    }


class TestSuggestEmailTemplate:
    def test_new_gets_no_suggestion(self):
        assert suggest_email_template(row("new")) is None

    def test_on_pace_gets_no_suggestion(self):
        assert suggest_email_template(row("on_pace")) is None

    def test_stalled_with_precedent_gets_slow_track_reapproach(self):
        # Regardless of newsletter/webinar status -- an established
        # relationship gone quiet, with a real closed-won revival example
        # backing it up, gets the "we've seen this before" re-approach
        # script, not a cold newsletter pitch.
        result = suggest_email_template(row("stalled", subscribed=False, attended=False))
        assert result["id"] == "slow_track_reapproach"

    def test_stalled_without_precedent_gets_product_feedback(self):
        # No matching closed-won revival example for this account -- don't
        # imply a precedent that isn't there; ask for product feedback
        # instead (a different real script, not generated copy).
        result = suggest_email_template(row("stalled", examples=[]))
        assert result["id"] == "slow_track_product_feedback"

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
