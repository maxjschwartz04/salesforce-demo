from datetime import date

from opportunity_parser import (
    _normalize_company_name,
    build_account_status,
    find_account_status,
    list_winback_candidates,
)


def opp(account_name, stage, close_date=None, opportunity_name=None, owner=None, next_step=None):
    return {
        "account_name": account_name,
        "opportunity_name": opportunity_name or f"{account_name}.OPP",
        "owner": owner or "Some Rep",
        "stage": stage,
        "close_date": close_date,
        "created_date": None,
        "type": "New Business",
        "next_step": next_step,
    }


class TestNormalizeCompanyName:
    def test_strips_punctuation_and_common_suffixes(self):
        assert _normalize_company_name("Celldex Therapeutics, Inc.") == "celldex therapeutics"
        assert _normalize_company_name("Kerry, Inc.") == "kerry"
        assert _normalize_company_name("Geron Corporation") == "geron"

    def test_empty_input(self):
        assert _normalize_company_name("") == ""
        assert _normalize_company_name(None) == ""


class TestFindAccountStatus:
    def test_exact_match(self):
        status = {"GSK": {"has_open_opportunity": True}}
        assert find_account_status("GSK", status)["has_open_opportunity"] is True

    def test_normalized_match_suffix_difference(self):
        status = {"Celldex Therapeutics, Inc.": {"has_open_opportunity": False}}
        assert find_account_status("Celldex Therapeutics", status) is not None

    def test_prefix_match_short_label(self):
        # Regression: "McKee" (a short CLI label) must resolve against
        # "McKee Foods Corporation" (the Opportunity export's own name).
        status = {"McKee Foods Corporation": {"has_open_opportunity": False}}
        assert find_account_status("McKee", status) is not None

    def test_no_match_returns_none(self):
        status = {"Totally Different Company": {}}
        assert find_account_status("McKee", status) is None

    def test_ambiguous_prefix_match_returns_none(self):
        # Two different real companies could share a normalized prefix —
        # must not guess which one is meant.
        status = {
            "Acme Corporation": {"has_open_opportunity": True},
            "Acme Industries": {"has_open_opportunity": False},
        }
        assert find_account_status("Acme", status) is None


class TestBuildAccountStatus:
    def test_open_opportunity_detected(self):
        records = [opp("Noom", "Negotiating")]
        status = build_account_status(records)
        assert status["Noom"]["has_open_opportunity"] is True
        assert status["Noom"]["has_closed_won"] is False

    def test_all_closed_has_no_open_opportunity(self):
        records = [opp("McKee", "Closed Lost"), opp("McKee", "Closed Won")]
        status = build_account_status(records)
        assert status["McKee"]["has_open_opportunity"] is False
        assert status["McKee"]["has_closed_won"] is True

    def test_open_next_steps_only_from_open_opportunities(self):
        records = [
            opp("UCB", "Negotiating", next_step="confirm budget by June"),
            opp("UCB", "Closed Lost", next_step="this should not appear"),
        ]
        status = build_account_status(records)
        assert status["UCB"]["open_next_steps"] == ["confirm budget by June"]

    def test_no_next_step_gives_empty_list(self):
        records = [opp("Noom", "Negotiating")]
        status = build_account_status(records)
        assert status["Noom"]["open_next_steps"] == []


class TestListWinbackCandidates:
    def test_includes_account_whose_most_recent_opp_is_closed_lost(self):
        records = [opp("Foo Inc", "Closed Lost", close_date="1/1/2026")]
        candidates = list_winback_candidates(records, as_of=date(2026, 2, 1))
        assert len(candidates) == 1
        assert candidates[0]["account"] == "Foo Inc"
        assert candidates[0]["days_since_loss"] == 31

    def test_excludes_account_whose_most_recent_opp_is_open(self):
        records = [
            opp("Foo Inc", "Closed Lost", close_date="1/1/2026"),
            opp("Foo Inc", "Negotiating", close_date="2/1/2026"),
        ]
        assert list_winback_candidates(records, as_of=date(2026, 3, 1)) == []

    def test_excludes_account_whose_most_recent_opp_is_closed_won(self):
        records = [
            opp("Foo Inc", "Closed Lost", close_date="1/1/2026"),
            opp("Foo Inc", "Closed Won", close_date="2/1/2026"),
        ]
        assert list_winback_candidates(records, as_of=date(2026, 3, 1)) == []

    def test_excludes_defunct_flagged_accounts(self):
        records = [opp("ACQUIRED - Clif Bar", "Closed Lost", close_date="1/1/2026")]
        assert list_winback_candidates(records, as_of=date(2026, 2, 1)) == []

    def test_sorted_most_recent_loss_first(self):
        records = [
            opp("Old Loss Co", "Closed Lost", close_date="1/1/2016"),
            opp("Recent Loss Co", "Closed Lost", close_date="1/1/2026"),
        ]
        candidates = list_winback_candidates(records, as_of=date(2026, 2, 1))
        assert [c["account"] for c in candidates] == ["Recent Loss Co", "Old Loss Co"]
