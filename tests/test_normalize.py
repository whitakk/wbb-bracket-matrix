from bracket_matrix.normalize import is_placeholder_team, normalize_team_name, slugify


def test_normalize_nc_state_variants_match():
    a = normalize_team_name("NC State")
    b = normalize_team_name("North Carolina St")
    c = normalize_team_name("N.C. State")

    assert a == b == c
    assert slugify("N.C. State") == "north-carolina-state"


def test_placeholder_filters_known_content_noise():
    assert is_placeholder_team('Order "Rare Gems"')
    assert is_placeholder_team("Order “Rare Gems”")
    assert is_placeholder_team("the-ix-sports")
    assert is_placeholder_team("The IX Sports")
