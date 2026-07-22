from report_parser import _to_bool, group_by_account, parse_report_export


def _write_report_html(tmp_path, rows):
    """rows: list of (date, company, opportunity, contact, lead, subject,
    assigned, priority, status, task, last_modified, full_comments, email)."""
    header = (
        "<table><tr>"
        + "".join(
            f'<th filter=all>{h}</th>'
            for h in [
                "Date",
                "Company / Account",
                "Opportunity",
                "Contact",
                "Lead",
                "Subject",
                "Assigned",
                "Priority",
                "Status",
                "Task",
                "Last Modified Date",
                "Full Comments",
                "Email",
            ]
        )
        + "</tr>"
    )
    body_rows = ""
    for row in rows:
        cells = "".join(f"<td>{v}</td>" for v in row)
        body_rows += f"<tr>{cells}</tr>"
    html = f'<head><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"></head>{header}{body_rows}</table>'
    path = tmp_path / "report.xls"
    path.write_text(html, encoding="ISO-8859-1")
    return path


class TestToBool:
    def test_zero_is_false(self):
        assert _to_bool("0") is False

    def test_one_is_true(self):
        assert _to_bool("1") is True

    def test_blank_is_false(self):
        assert _to_bool("") is False

    def test_word_false_is_false(self):
        assert _to_bool("false") is False
        assert _to_bool("False") is False


class TestParseReportExport:
    def test_basic_row_parses_into_standard_shape(self, tmp_path):
        rows = [
            (
                "7/19/2024",
                "Intuitive Surgical, Inc.",
                "AIQ.Intuitive.2024.Q3",
                "Jade Kondo",
                "",
                "New Business",
                "Noah Hess",
                "",
                "",
                "0",
                "8/28/2024",
                "Wants to trial on an individual basis.",
                "jade.kondo@intusurg.com",
            )
        ]
        path = _write_report_html(tmp_path, rows)
        [record] = parse_report_export(str(path))

        assert record["subject"] == "New Business"
        assert record["primary_name"] == "Jade Kondo"
        assert record["related_to"] == "Intuitive Surgical, Inc."
        assert record["assigned_to"] == "Noah Hess"
        assert record["due_date"] == "7/19/2024"
        assert record["task"] is False
        assert record["last_modified_date"] == "8/28/2024, 12:00 PM"
        assert record["comments"]["raw_text"] == "Wants to trial on an individual basis."
        assert record["comments"]["email"] is None  # this source never has real email content
        assert record["opportunity"] == "AIQ.Intuitive.2024.Q3"
        assert record["contact_email"] == "jade.kondo@intusurg.com"

    def test_falls_back_to_lead_when_no_contact(self, tmp_path):
        rows = [("7/19/2024", "Acme", "", "", "Some Lead", "Subj", "Rep", "", "", "0", "8/28/2024", "note", "x@x.com")]
        path = _write_report_html(tmp_path, rows)
        [record] = parse_report_export(str(path))
        assert record["primary_name"] == "Some Lead"

    def test_blank_comments_becomes_none(self, tmp_path):
        rows = [("7/19/2024", "Acme", "", "", "", "Subj", "Rep", "", "", "0", "8/28/2024", "", "x@x.com")]
        path = _write_report_html(tmp_path, rows)
        [record] = parse_report_export(str(path))
        assert record["comments"] is None

    def test_malformed_row_with_wrong_cell_count_is_skipped(self, tmp_path):
        path = _write_report_html(tmp_path, [])
        # Manually append a malformed row with too few cells.
        html = path.read_text(encoding="ISO-8859-1")
        html = html.replace("</table>", "<tr><td>only one cell</td></tr></table>")
        path.write_text(html, encoding="ISO-8859-1")
        assert parse_report_export(str(path)) == []


class TestGroupByAccount:
    def test_groups_by_related_to(self, tmp_path):
        rows = [
            ("7/19/2024", "Acme", "", "", "", "Subj1", "Rep", "", "", "0", "8/28/2024", "note", "x@x.com"),
            ("7/20/2024", "Acme", "", "", "", "Subj2", "Rep", "", "", "0", "8/29/2024", "note2", "x@x.com"),
            ("7/21/2024", "Beta", "", "", "", "Subj3", "Rep", "", "", "0", "8/30/2024", "note3", "x@x.com"),
        ]
        path = _write_report_html(tmp_path, rows)
        grouped = group_by_account(parse_report_export(str(path)))
        assert len(grouped["Acme"]) == 2
        assert len(grouped["Beta"]) == 1

    def test_drops_records_without_account(self, tmp_path):
        rows = [("7/19/2024", "", "", "", "", "Subj1", "Rep", "", "", "0", "8/28/2024", "note", "x@x.com")]
        path = _write_report_html(tmp_path, rows)
        grouped = group_by_account(parse_report_export(str(path)))
        assert grouped == {}
