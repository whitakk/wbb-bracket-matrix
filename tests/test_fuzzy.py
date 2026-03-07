from bracket_matrix.normalize import resolve_team_names


def test_low_confidence_match_is_flagged():
    resolved, unresolved = resolve_team_names(
        team_names=["Gonzaga", "Gonzagaa"],
        aliases=[],
        fuzzy_threshold=95,
        fuzzy_review_threshold=80,
        fuzzy_ambiguous_margin=3,
    )

    assert "Gonzaga" in resolved
    assert "Gonzagaa" not in resolved
    assert len(unresolved) == 1
    assert unresolved[0].team_raw == "Gonzagaa"
