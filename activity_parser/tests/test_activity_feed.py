from activity_feed import build_activity_feed


def email_record(date, subject):
    return {
        "subject": subject,
        "last_modified_date": date,
        "comments": {"raw_text": "body text", "email": {"body": "body text"}},
    }


def note_record(date, subject):
    return {"subject": subject, "last_modified_date": date, "comments": {"raw_text": "call notes", "email": None}}


class TestBuildActivityFeed:
    def test_sorted_newest_first(self):
        records = [
            email_record("1/1/2026, 12:00 PM", "Oldest"),
            email_record("1/15/2026, 12:00 PM", "Newest"),
            email_record("1/8/2026, 12:00 PM", "Middle"),
        ]
        feed = build_activity_feed(records)
        assert [a["subject"] for a in feed] == ["Newest", "Middle", "Oldest"]

    def test_email_records_typed_as_email(self):
        feed = build_activity_feed([email_record("1/1/2026, 12:00 PM", "Email: hello")])
        assert feed[0]["type"] == "Email"

    def test_non_email_records_typed_as_activity(self):
        feed = build_activity_feed([note_record("1/1/2026, 12:00 PM", "call notes")])
        assert feed[0]["type"] == "Activity"

    def test_call_records_typed_as_call(self):
        feed = build_activity_feed([note_record("1/1/2026, 12:00 PM", "Call: No Answer - Left Voicemail")])
        assert feed[0]["type"] == "Call"

    def test_call_prefix_match_is_case_insensitive(self):
        feed = build_activity_feed([note_record("1/1/2026, 12:00 PM", "CALL: Follow-up")])
        assert feed[0]["type"] == "Call"

    def test_call_mentioned_mid_subject_is_not_typed_as_call(self):
        # Only a real leading "Call:" prefix counts -- a subject that
        # merely mentions a call partway through isn't the same signal.
        feed = build_activity_feed([note_record("1/1/2026, 12:00 PM", "Please call back re: renewal")])
        assert feed[0]["type"] == "Activity"

    def test_records_with_unparseable_dates_are_skipped(self):
        records = [{"subject": "bad", "last_modified_date": "garbage", "comments": None}]
        assert build_activity_feed(records) == []

    def test_respects_limit(self):
        records = [email_record(f"1/{i}/2026, 12:00 PM", f"Email {i}") for i in range(1, 11)]
        feed = build_activity_feed(records, limit=3)
        assert len(feed) == 3
        assert feed[0]["subject"] == "Email 10"

    def test_date_is_iso_formatted(self):
        feed = build_activity_feed([email_record("3/5/2026, 9:30 AM", "Email: check-in")])
        assert feed[0]["date"] == "2026-03-05"
