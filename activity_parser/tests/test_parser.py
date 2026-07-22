import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from parser import extract_html_from_mhtml, filter_and_sort_activities, parse_activities, parse_last_modified_date


def make_panel(
    subject="",
    primary_name="",
    related_to="",
    stage="",
    task_checkbox_html="",
    due_date="",
    assigned_to="",
    last_modified_date="",
    comments_html="",
):
    """Builds a minimal slds-panel fragment matching the real export's
    structure closely enough for parse_activities: each label/value pair
    are direct siblings inside a shared parent div."""

    def field(label, value_html):
        return f'<div><div class="slds-text-label">{label}</div><div class="slds-text-value">{value_html}</div></div>'

    return (
        '<div class="slds-panel">'
        + field("Subject", subject)
        + field("Primary Name", primary_name)
        + field("Related To", related_to)
        + field("Stage", stage)
        + field("Task", task_checkbox_html)
        + field("Due Date", due_date)
        + field("Assigned To", assigned_to)
        + field("Last Modified Date", last_modified_date)
        + field("Comments", comments_html)
        + "</div>"
    )


def wrap(panels_html):
    return f"<html><body>{panels_html}</body></html>"


class TestParseActivities:
    def test_basic_fields(self):
        html = wrap(
            make_panel(
                subject="Email: hello",
                primary_name="Nick Pyle",
                related_to="McKee Foods Corporation",
                assigned_to="Maggie Gall",
                last_modified_date="7/14/2026, 1:11 PM",
            )
        )
        [record] = parse_activities(html)
        assert record["subject"] == "Email: hello"
        assert record["primary_name"] == "Nick Pyle"
        assert record["related_to"] == "McKee Foods Corporation"
        assert record["assigned_to"] == "Maggie Gall"
        assert record["last_modified_date"] == "7/14/2026, 1:11 PM"

    def test_blank_fields_become_none(self):
        html = wrap(make_panel(subject="Email: hello"))
        [record] = parse_activities(html)
        assert record["stage"] is None
        assert record["related_to"] is None
        assert record["assigned_to"] is None

    @pytest.mark.parametrize(
        "checkbox_html, expected",
        [
            ('<input type="checkbox" disabled="" checked="">', True),
            ('<input type="checkbox" disabled="">', False),
            ("", None),
        ],
    )
    def test_task_checkbox_states(self, checkbox_html, expected):
        html = wrap(make_panel(task_checkbox_html=checkbox_html))
        [record] = parse_activities(html)
        assert record["task"] is expected

    def test_comments_with_email_headers_extracts_nested_fields(self):
        comments = (
            "To: nick@dcpyle.com<br>CC: <br>BCC: <br>Attachment: --none--<br><br>"
            "Subject: Reaching out<br>Body:<br>Hi Nick,<br>Following up."
        )
        html = wrap(make_panel(comments_html=comments))
        [record] = parse_activities(html)
        assert record["comments"]["email"]["to"] == "nick@dcpyle.com"
        assert record["comments"]["email"]["subject"] == "Reaching out"
        assert record["comments"]["email"]["body"] == "Hi Nick,\nFollowing up."

    def test_comments_without_to_line_has_no_email(self):
        html = wrap(make_panel(comments_html="Just a call note, no email here."))
        [record] = parse_activities(html)
        assert record["comments"]["email"] is None
        assert record["comments"]["raw_text"] == "Just a call note, no email here."

    def test_blank_comments_is_none(self):
        html = wrap(make_panel(comments_html=""))
        [record] = parse_activities(html)
        assert record["comments"] is None

    def test_multiple_panels_preserve_order(self):
        html = wrap(make_panel(subject="First") + make_panel(subject="Second"))
        records = parse_activities(html)
        assert [r["subject"] for r in records] == ["First", "Second"]


class TestFilterAndSortActivities:
    def _record(self, subject="Email: hi", related_to="Some Company", last_modified_date="1/1/2026, 12:00 PM"):
        return {"subject": subject, "related_to": related_to, "last_modified_date": last_modified_date}

    def test_removes_politico_pro_phrase_in_subject(self):
        records = [self._record(subject="Email: Nick, reaching out from POLITICO Pro")]
        assert filter_and_sort_activities(records) == []

    def test_keeps_bare_pro_word_not_the_phrase(self):
        # Regression: "Pro" alone (e.g. "Pro Analysis") must NOT be treated
        # as POLITICO Pro noise — only the specific phrase should match.
        records = [self._record(subject="Email: A Gift from Pro")]
        assert len(filter_and_sort_activities(records)) == 1

    def test_removes_pro_dot_prefixed_related_to(self):
        records = [self._record(related_to="PRO.McKee Foods Corporat.2027.R")]
        assert filter_and_sort_activities(records) == []

    def test_keeps_normal_related_to(self):
        records = [self._record(related_to="McKee Foods Corporation")]
        assert len(filter_and_sort_activities(records)) == 1

    def test_sorts_chronologically_oldest_first(self):
        records = [
            self._record(subject="Later", last_modified_date="3/1/2026, 12:00 PM"),
            self._record(subject="Earlier", last_modified_date="1/1/2026, 12:00 PM"),
        ]
        result = filter_and_sort_activities(records)
        assert [r["subject"] for r in result] == ["Earlier", "Later"]

    def test_unparseable_date_sorts_first(self):
        records = [
            self._record(subject="Dated", last_modified_date="1/1/2026, 12:00 PM"),
            self._record(subject="Undated", last_modified_date=None),
        ]
        result = filter_and_sort_activities(records)
        assert result[0]["subject"] == "Undated"


class TestParseLastModifiedDate:
    def test_valid_format(self):
        dt = parse_last_modified_date("7/14/2026, 1:11 PM")
        assert (dt.month, dt.day, dt.year, dt.hour, dt.minute) == (7, 14, 2026, 13, 11)

    def test_invalid_format_returns_none(self):
        assert parse_last_modified_date("not a date") is None

    def test_none_input_returns_none(self):
        assert parse_last_modified_date(None) is None


class TestExtractHtmlFromMhtml:
    def test_extracts_html_part(self, tmp_path):
        msg = MIMEMultipart("related")
        msg["Subject"] = "Test"
        msg.attach(MIMEText("<html><body>hello</body></html>", "html"))

        mhtml_path = tmp_path / "test.mhtml"
        with open(mhtml_path, "wb") as f:
            f.write(msg.as_bytes())

        html = extract_html_from_mhtml(str(mhtml_path))
        assert "hello" in html

    def test_raises_when_no_html_part(self, tmp_path):
        msg = email.message.Message()
        msg["Subject"] = "No HTML here"
        msg.set_payload("plain text only")

        mhtml_path = tmp_path / "test.mhtml"
        with open(mhtml_path, "wb") as f:
            f.write(msg.as_bytes())

        with pytest.raises(ValueError):
            extract_html_from_mhtml(str(mhtml_path))
