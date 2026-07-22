import openpyxl
import pytest

from campaign_parser import _parse_date_group_start, get_recent_engagements, group_by_company, parse_campaign_report


class TestParseDateGroupStart:
    def test_extracts_start_of_week_range(self):
        dt = _parse_date_group_start("7/19/2026 - 7/25/2026")
        assert (dt.month, dt.day, dt.year) == (7, 19, 2026)

    def test_none_input(self):
        assert _parse_date_group_start(None) is None

    def test_unparseable_input(self):
        assert _parse_date_group_start("not a date range") is None


class TestGetRecentEngagements:
    def _engagement(self, date_group, name):
        return {
            "date_group": date_group,
            "member_type": "Contact",
            "first_name": name,
            "last_name": "Test",
            "title": "",
            "email": f"{name}@example.com",
            "company": "Acme",
            "campaign_name": "Some Campaign",
            "member_status": "Attended",
            "campaign_type": "Webinar",
        }

    def test_sorted_newest_first_and_limited(self):
        grouped = {
            "Acme": [
                self._engagement("1/1/2026 - 1/7/2026", "Oldest"),
                self._engagement("6/1/2026 - 6/7/2026", "Newest"),
                self._engagement("3/1/2026 - 3/7/2026", "Middle"),
            ]
        }
        result = get_recent_engagements("Acme", grouped, top_n=2)
        assert [e["first_name"] for e in result] == ["Newest", "Middle"]

    def test_no_engagements_for_unknown_company(self):
        assert get_recent_engagements("Nobody Inc", {}) == []

    def test_exact_match_only_no_fuzzy(self):
        # Regression: unlike opportunity_parser's find_account_status, this
        # must NOT fuzzy-match — a Lead's self-typed company name is too
        # unreliable to risk pairing with the wrong real account.
        grouped = {"Acme Corporation": [self._engagement("1/1/2026 - 1/7/2026", "Someone")]}
        assert get_recent_engagements("Acme", grouped) == []


def _write_campaign_workbook(tmp_path, rows):
    """rows: list of (date_group_or_None, member_type, first, last, title,
    email, company, campaign_name, member_status, campaign_type)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, "Copy of AIQ - Company with any campaign"])
    ws.append([None, "Filtered By"])
    ws.append(
        [
            None,
            "Member First Associated Date  ↓",
            "Member Type",
            "First Name",
            "Last Name",
            "Title",
            "Email",
            "Company",
            "Campaign Name",
            "Member Status",
            "Campaign Type",
        ]
    )
    for row in rows:
        ws.append([None] + list(row))
    path = tmp_path / "campaigns.xlsx"
    wb.save(path)
    return path


class TestParseCampaignReport:
    def test_forward_fills_grouped_date(self, tmp_path):
        rows = [
            ("7/19/2026 - 7/25/2026", "Lead", "A", "One", "", "a@x.com", "Acme", "Camp1", "Attended", "Webinar"),
            (None, "Contact", "B", "Two", "", "b@x.com", "Beta", "Camp2", "Filled Out Form", "Website"),
            (None, "Contact", "C", "Three", "", "c@x.com", "Gamma", "Camp3", "Attended", "Webinar"),
            ("6/1/2026 - 6/7/2026", "Lead", "D", "Four", "", "d@x.com", "Delta", "Camp4", "Attended", "Webinar"),
        ]
        path = _write_campaign_workbook(tmp_path, rows)
        records = parse_campaign_report(str(path))

        assert [r["date_group"] for r in records] == [
            "7/19/2026 - 7/25/2026",
            "7/19/2026 - 7/25/2026",
            "7/19/2026 - 7/25/2026",
            "6/1/2026 - 6/7/2026",
        ]

    def test_skips_blank_rows(self, tmp_path):
        rows = [
            ("7/19/2026 - 7/25/2026", "Lead", "A", "One", "", "a@x.com", "Acme", "Camp1", "Attended", "Webinar"),
            (None, None, None, None, None, None, None, None, None, None),
        ]
        path = _write_campaign_workbook(tmp_path, rows)
        records = parse_campaign_report(str(path))
        assert len(records) == 1

    def test_group_by_company(self, tmp_path):
        rows = [
            ("7/19/2026 - 7/25/2026", "Lead", "A", "One", "", "a@x.com", "Acme", "Camp1", "Attended", "Webinar"),
            (None, "Contact", "B", "Two", "", "b@x.com", "Acme", "Camp2", "Filled Out Form", "Website"),
        ]
        path = _write_campaign_workbook(tmp_path, rows)
        grouped = group_by_company(parse_campaign_report(str(path)))
        assert len(grouped["Acme"]) == 2
