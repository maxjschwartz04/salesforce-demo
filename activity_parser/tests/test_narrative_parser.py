from datetime import date

import docx

from narrative_parser import _is_boilerplate_annotation, _touch_to_record, extract_lessons, parse_narrative_docx


def _build_docx(tmp_path):
    """A tiny synthetic version of the master doc's structure: one rep
    heading, one account heading, a mix of touches, annotations, and a
    section divider."""
    document = docx.Document()
    document.add_paragraph("Casey Miles", style="Heading 1")
    document.add_paragraph("1. Acme Corp", style="Heading 2")
    document.add_paragraph("Opportunity: AIQ.ACME.2025.1  |  Close Date: 1/1/2026  |  $10,000 ACV")
    document.add_paragraph("--- Trial kickoff ---")
    document.add_paragraph('4/10/2025 — Casey Miles: "Acme + AgencyIQ" (trial kickoff)')
    document.add_paragraph("Hi team, here is your trial access.")
    document.add_paragraph("⚠ Gap in the record: no logged emails for two weeks, likely a call happened offline.")
    document.add_paragraph('5/1/2025 — Casey Miles: "RE: Acme + AgencyIQ"')
    document.add_paragraph("Following up on the trial.")
    document.add_paragraph(
        "⚠ 3/14/2025 — Casey Miles: \"RE: AgencyIQ\" — touch is logged in Salesforce but the export only "
        "captured corrupted HTML source for this entry; actual message content isn't recoverable."
    )
    document.add_paragraph("2. Beta Inc", style="Heading 2")
    document.add_paragraph('6/1/2025 — Casey Miles: "Beta kickoff"')
    document.add_paragraph(
        "[Newsletter/research analysis sent — not reproduced here to reduce document length; 500 characters omitted]"
    )
    path = tmp_path / "master.docx"
    document.save(path)
    return path


class TestParseNarrativeDocx:
    def test_groups_touches_by_account(self, tmp_path):
        path = _build_docx(tmp_path)
        accounts = parse_narrative_docx(str(path))
        assert set(accounts.keys()) == {"Acme Corp", "Beta Inc"}
        assert len(accounts["Acme Corp"]) == 2
        assert len(accounts["Beta Inc"]) == 1

    def test_touch_fields_parsed_correctly(self, tmp_path):
        path = _build_docx(tmp_path)
        accounts = parse_narrative_docx(str(path))
        touch = accounts["Acme Corp"][0]
        assert touch["date"].isoformat() == "2025-04-10"
        assert touch["subject"] == "Acme + AgencyIQ"
        assert touch["body_lines"] == ["Hi team, here is your trial access."]

    def test_annotations_are_not_parsed_as_touches(self, tmp_path):
        path = _build_docx(tmp_path)
        accounts = parse_narrative_docx(str(path))
        # Only the 2 real touch lines for Acme, the "⚠" lines must not
        # appear as touches or get attached as body text to the wrong touch.
        subjects = [t["subject"] for t in accounts["Acme Corp"]]
        assert subjects == ["Acme + AgencyIQ", "RE: Acme + AgencyIQ"]

    def test_opportunity_metadata_line_is_not_a_touch_or_body(self, tmp_path):
        path = _build_docx(tmp_path)
        accounts = parse_narrative_docx(str(path))
        for touch in accounts["Acme Corp"]:
            assert not any("Opportunity:" in line for line in touch["body_lines"])


class TestExtractLessons:
    def test_extracts_non_boilerplate_annotation(self, tmp_path):
        path = _build_docx(tmp_path)
        lessons = extract_lessons(str(path))
        assert len(lessons) == 1
        assert lessons[0]["account"] == "Acme Corp"
        assert "Gap in the record" in lessons[0]["text"]

    def test_filters_out_corrupted_export_boilerplate(self, tmp_path):
        path = _build_docx(tmp_path)
        lessons = extract_lessons(str(path))
        assert not any("corrupted" in l["text"].lower() for l in lessons)


class TestIsBoilerplateAnnotation:
    def test_corrupted_export_is_boilerplate(self):
        assert _is_boilerplate_annotation("⚠ export only captured corrupted HTML")

    def test_no_significant_gap_is_boilerplate(self):
        assert _is_boilerplate_annotation("⚠ No significant time gaps in this record")

    def test_real_insight_is_not_boilerplate(self):
        assert not _is_boilerplate_annotation("⚠ A 94-day gap preceded direct engagement")


class TestTouchToRecord:
    def test_redacted_placeholder_becomes_no_body(self):
        touch = {
            "date": date(2025, 6, 1),
            "subject": "Some subject",
            "body_lines": ["[Newsletter/research analysis sent — not reproduced here to reduce document length]"],
        }
        record = _touch_to_record(touch)
        assert record["comments"]["raw_text"] is None
        assert record["comments"]["email"]["body"] is None

    def test_real_body_preserved(self):
        touch = {
            "date": date(2025, 6, 1),
            "subject": "Some subject",
            "body_lines": ["Hi there, following up on our call."],
        }
        record = _touch_to_record(touch)
        assert record["comments"]["raw_text"] == "Hi there, following up on our call."

    def test_synthetic_noon_timestamp_format(self):
        touch = {"date": date(2025, 6, 1), "subject": "X", "body_lines": []}
        record = _touch_to_record(touch)
        assert record["last_modified_date"] == "06/01/2025, 12:00 PM"
