import openpyxl
import pytest

from campaign_parser import (
    parse_date_group_start,
    get_recent_engagements,
    group_by_company,
    has_attended_webinar,
    has_subscribed_to_newsletter,
    parse_campaign_report,
    top_contacts,
)


class TestParseDateGroupStart:
    def test_extracts_start_of_week_range(self):
        dt = parse_date_group_start("7/19/2026 - 7/25/2026")
        assert (dt.month, dt.day, dt.year) == (7, 19, 2026)

    def test_none_input(self):
        assert parse_date_group_start(None) is None

    def test_unparseable_input(self):
        assert parse_date_group_start("not a date range") is None


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


class TestHasAttendedWebinar:
    def _row(self, campaign_name, member_status):
        return {"company": "Acme", "campaign_name": campaign_name, "member_status": member_status}

    def test_real_webinar_naming_convention_with_attended_status(self):
        grouped = {"Acme": [self._row("AIQ.2026.07.21.Food Webinar.WBN.Unified Agenda", "Attended")]}
        assert has_attended_webinar("Acme", grouped) is True

    def test_attended_on_demand_counts_too(self):
        grouped = {"Acme": [self._row("AIQ.2026.07.21.Food Webinar.WBN.Unified Agenda", "Attended On-demand")]}
        assert has_attended_webinar("Acme", grouped) is True

    def test_registered_but_not_attended_does_not_count(self):
        grouped = {"Acme": [self._row("AIQ.2026.07.21.Food Webinar.WBN.Unified Agenda", "Filled Out Form")]}
        assert has_attended_webinar("Acme", grouped) is False

    def test_non_webinar_campaign_does_not_count(self):
        grouped = {"Acme": [self._row("MKT.AIQ.2025.Subscribe FDA Today Food.EM.Food Webinar", "Responded")]}
        assert has_attended_webinar("Acme", grouped) is False

    def test_unknown_company_returns_false(self):
        assert has_attended_webinar("Nobody Inc", {}) is False


class TestHasSubscribedToNewsletter:
    def test_real_subscribe_campaign_naming(self):
        grouped = {
            "Acme": [{"company": "Acme", "campaign_name": "MKT.AIQ.2025.Subscribe FDA Today Food.EM.Food Webinar"}]
        }
        assert has_subscribed_to_newsletter("Acme", grouped) is True

    def test_webinar_only_campaign_does_not_count(self):
        grouped = {"Acme": [{"company": "Acme", "campaign_name": "AIQ.2026.07.21.Food Webinar.WBN.Unified Agenda"}]}
        assert has_subscribed_to_newsletter("Acme", grouped) is False

    def test_unknown_company_returns_false(self):
        assert has_subscribed_to_newsletter("Nobody Inc", {}) is False


class TestTopContacts:
    def _touch(self, date_group, first, last, title, email):
        return {
            "date_group": date_group,
            "member_type": "Contact",
            "first_name": first,
            "last_name": last,
            "title": title,
            "email": email,
            "company": "Acme",
            "campaign_name": "Some Campaign",
            "member_status": "Attended",
            "campaign_type": "Webinar",
        }

    def test_dedupes_by_email_and_keeps_most_recent_touch_count(self):
        grouped = {
            "Acme": [
                self._touch("1/1/2026 - 1/7/2026", "Jane", "Doe", "Manager", "jane@acme.com"),
                self._touch("6/1/2026 - 6/7/2026", "Jane", "Doe", "Director", "jane@acme.com"),
            ]
        }
        contacts = top_contacts("Acme", grouped)
        assert len(contacts) == 1
        assert contacts[0]["engagement_count"] == 2
        # Most recent touch's title wins -- a promotion since the first touch.
        assert contacts[0]["title"] == "Director"

    def test_email_dedup_is_case_insensitive(self):
        grouped = {
            "Acme": [
                self._touch("1/1/2026 - 1/7/2026", "Jane", "Doe", "Manager", "Jane@Acme.com"),
                self._touch("2/1/2026 - 2/7/2026", "Jane", "Doe", "Manager", "jane@acme.com"),
            ]
        }
        contacts = top_contacts("Acme", grouped)
        assert len(contacts) == 1
        assert contacts[0]["engagement_count"] == 2

    def test_sorted_by_most_recent_engagement_not_by_count(self):
        # "Frequent" engaged 3 times but all long ago; "Recent" engaged once
        # but just now -- recency wins since that's who's actually warm.
        grouped = {
            "Acme": [
                self._touch("1/1/2020 - 1/7/2020", "Frequent", "One", "", "frequent@acme.com"),
                self._touch("1/8/2020 - 1/14/2020", "Frequent", "One", "", "frequent@acme.com"),
                self._touch("1/15/2020 - 1/21/2020", "Frequent", "One", "", "frequent@acme.com"),
                self._touch("6/1/2026 - 6/7/2026", "Recent", "Two", "", "recent@acme.com"),
            ]
        }
        contacts = top_contacts("Acme", grouped)
        assert [c["email"] for c in contacts] == ["recent@acme.com", "frequent@acme.com"]

    def test_skips_contacts_with_no_email(self):
        grouped = {"Acme": [self._touch("1/1/2026 - 1/7/2026", "No", "Email", "", None)]}
        assert top_contacts("Acme", grouped) == []

    def test_respects_limit(self):
        grouped = {
            "Acme": [
                self._touch(f"1/{i}/2026 - 1/{i+6}/2026", f"Person{i}", "Test", "", f"p{i}@acme.com")
                for i in range(1, 6)
            ]
        }
        assert len(top_contacts("Acme", grouped, limit=3)) == 3

    def test_unknown_company_returns_empty(self):
        assert top_contacts("Nobody Inc", {}) == []


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
