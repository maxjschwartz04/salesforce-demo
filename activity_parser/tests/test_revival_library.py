from revival_library import find_revival_moments


def email_record(date, subject, body="Some real email content here."):
    return {
        "subject": subject,
        "last_modified_date": date,
        "comments": {"raw_text": body, "email": {"body": body}},
    }


def note_record(date, subject):
    """A task/call note — no nested email, so it can't be a revival trigger."""
    return {"subject": subject, "last_modified_date": date, "comments": {"raw_text": "call notes", "email": None}}


def baseline_records():
    """A steady ~5-day rhythm (engagement days: 1,6,11,16,21) so the median
    gap is unambiguous, followed by a big gap and a revival + response."""
    return [
        email_record("1/1/2026, 12:00 PM", "Email A"),
        email_record("1/6/2026, 12:00 PM", "Email B"),
        email_record("1/11/2026, 12:00 PM", "Email C"),
        email_record("1/16/2026, 12:00 PM", "Email D"),
        email_record("1/21/2026, 12:00 PM", "Email E"),
    ]


class TestFindRevivalMoments:
    def test_detects_gap_followed_by_revival_and_response(self):
        records = baseline_records() + [
            email_record("3/1/2026, 12:00 PM", "Email: reconnect"),
            email_record("3/3/2026, 12:00 PM", "Email: RE: reconnect"),
        ]
        moments = find_revival_moments(records)
        assert len(moments) == 1
        moment = moments[0]
        assert moment["revival_subject"] == "Email: reconnect"
        assert moment["next_response_subject"] == "Email: RE: reconnect"
        assert moment["days_to_next_response"] == 2.0

    def test_no_moments_when_gap_within_normal_rhythm(self):
        # Same 5-day rhythm continued — no gap exceeds 3x the median.
        records = baseline_records() + [email_record("1/26/2026, 12:00 PM", "Email F")]
        assert find_revival_moments(records) == []

    def test_excludes_billing_invoice_noise(self):
        records = baseline_records() + [
            email_record("3/1/2026, 12:00 PM", "Email: Overdue Invoice SIN048316"),
            email_record("3/3/2026, 12:00 PM", "Email: RE"),
        ]
        assert find_revival_moments(records) == []

    def test_excludes_auto_reply_noise(self):
        records = baseline_records() + [
            email_record("3/1/2026, 12:00 PM", "Email: Automatic reply: out of office"),
            email_record("3/3/2026, 12:00 PM", "Email: RE"),
        ]
        assert find_revival_moments(records) == []

    def test_excludes_pro_briefing_noise(self):
        records = baseline_records() + [
            email_record("3/1/2026, 12:00 PM", "Email: 3.11 Pro Briefing: Biden's Climate Plan"),
            email_record("3/3/2026, 12:00 PM", "Email: RE"),
        ]
        assert find_revival_moments(records) == []

    def test_excludes_pro_summit_noise(self):
        records = baseline_records() + [
            email_record("3/1/2026, 12:00 PM", "Email: Invitation to our Pro Summit"),
            email_record("3/3/2026, 12:00 PM", "Email: RE"),
        ]
        assert find_revival_moments(records) == []

    def test_excludes_pro_renewal_noise(self):
        records = baseline_records() + [
            email_record("3/1/2026, 12:00 PM", "Email: RE: Upcoming Pro renewal - preferred rates"),
            email_record("3/3/2026, 12:00 PM", "Email: RE"),
        ]
        assert find_revival_moments(records) == []

    def test_excludes_revival_broken_by_task_note_not_email(self):
        records = baseline_records() + [
            note_record("3/1/2026, 12:00 PM", "talk to Lily // reapproach"),
            email_record("3/3/2026, 12:00 PM", "Email: follow up"),
        ]
        assert find_revival_moments(records) == []

    def test_excludes_revival_with_no_followup_response(self):
        records = baseline_records() + [email_record("3/1/2026, 12:00 PM", "Email: last ditch effort")]
        # Nothing after the revival email at all -> not a proven revival.
        assert find_revival_moments(records) == []

    def test_returns_empty_below_minimum_engagement_days(self):
        records = [email_record("1/1/2026, 12:00 PM", "A"), email_record("1/2/2026, 12:00 PM", "B")]
        assert find_revival_moments(records) == []

    def test_gap_days_and_typical_gap_reported_correctly(self):
        records = baseline_records() + [
            email_record("3/1/2026, 12:00 PM", "Email: reconnect"),
            email_record("3/3/2026, 12:00 PM", "Email: RE: reconnect"),
        ]
        [moment] = find_revival_moments(records)
        assert moment["typical_gap_days"] == 5.0
        assert moment["gap_start_date"] == "2026-01-21"
        assert moment["gap_end_date"] == "2026-03-01"
