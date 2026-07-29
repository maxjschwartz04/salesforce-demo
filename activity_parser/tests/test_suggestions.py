from datetime import date

from suggestions import SMALL_LIBRARY_THRESHOLD, suggest_reengagement_examples


def stalled_records():
    """5-day rhythm, then a big gap -> stalled as of 2026-04-01."""
    return [
        {"last_modified_date": "1/1/2026, 12:00 PM"},
        {"last_modified_date": "1/6/2026, 12:00 PM"},
        {"last_modified_date": "1/11/2026, 12:00 PM"},
    ]


def library_moment(account, gap_days, typical_gap_days, source="raw_export"):
    return {
        "account": account,
        "source": source,
        "gap_days": gap_days,
        "typical_gap_days": typical_gap_days,
        "revival_subject": f"Email from {account}",
        "revival_excerpt": "Some excerpt",
        "days_to_next_response": 2.0,
        "revival_date": "2025-01-01T12:00:00",
    }


class TestSuggestReengagementExamples:
    def test_not_stalled_returns_no_examples(self):
        records = [{"last_modified_date": "1/1/2026, 12:00 PM"}]
        result = suggest_reengagement_examples(records, [], as_of=date(2026, 1, 2))
        assert result["staleness"]["status"] != "stalled"
        assert result["examples"] == []

    def test_stalled_ranks_by_closest_gap_ratio(self):
        library = [
            library_moment("Far Match", gap_days=100, typical_gap_days=5),  # 20x
            library_moment("Close Match", gap_days=30, typical_gap_days=5),  # 6x
        ]
        # live account: typical gap 5 days, ~80 days since last touch (as_of far in the future) -> ~16x
        result = suggest_reengagement_examples(stalled_records(), library, as_of=date(2026, 4, 1), top_n=2)
        assert result["staleness"]["status"] == "stalled"
        assert result["examples"][0]["account"] == "Far Match"  # 20x is closer to ~16x than 6x is

    def test_small_library_flag_below_threshold(self):
        library = [library_moment("Only One", gap_days=30, typical_gap_days=5)]
        result = suggest_reengagement_examples(stalled_records(), library, as_of=date(2026, 4, 1))
        assert result["library_account_count"] == 1
        assert result["library_is_small_sample"] is True

    def test_small_library_flag_clears_at_threshold(self):
        library = [
            library_moment(f"Account {i}", gap_days=30, typical_gap_days=5) for i in range(SMALL_LIBRARY_THRESHOLD)
        ]
        result = suggest_reengagement_examples(stalled_records(), library, as_of=date(2026, 4, 1))
        assert result["library_account_count"] == SMALL_LIBRARY_THRESHOLD
        assert result["library_is_small_sample"] is False

    def test_curator_notes_attached_to_matching_account(self):
        library = [library_moment("Geron", gap_days=30, typical_gap_days=5)]
        lessons = {"Geron": ["Congrats-on-promotion note revived this deal."]}
        result = suggest_reengagement_examples(
            stalled_records(), library, as_of=date(2026, 4, 1), lessons_by_account=lessons
        )
        assert result["examples"][0]["curator_notes"] == ["Congrats-on-promotion note revived this deal."]

    def test_top_n_limits_results(self):
        library = [library_moment(f"Account {i}", gap_days=30 + i, typical_gap_days=5) for i in range(10)]
        result = suggest_reengagement_examples(stalled_records(), library, as_of=date(2026, 4, 1), top_n=2)
        assert len(result["examples"]) == 2
