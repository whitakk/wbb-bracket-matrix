from pathlib import Path

from bracket_matrix.scrapers import cbssports
from bracket_matrix.scrapers.collegesportsmadness import parse_college_sports_madness
from bracket_matrix.scrapers.espn import parse_espn
from bracket_matrix.scrapers.herhoopstats import parse_her_hoop_stats
from bracket_matrix.scrapers import theix


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _team_label(index: int) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    first = letters[index % 26]
    second = letters[(index // 26) % 26]
    return f"Team {first}{second}"


def _balanced_pairs(count_per_seed: int = 4) -> list[tuple[int, str, bool]]:
    pairs: list[tuple[int, str, bool]] = []
    index = 0
    for seed in range(1, 17):
        for _ in range(count_per_seed):
            pairs.append((seed, _team_label(index), False))
            index += 1
    return pairs


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parse_her_hoop_stats_fixture():
    result = parse_her_hoop_stats(
        source_key="her_hoop_stats",
        source_name="Her Hoop Stats",
        source_url="https://example.com",
        html=_read("herhoopstats.html"),
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )
    assert result.updated_at_raw
    assert any(row.team_raw == "UCLA" and row.seed == 1 for row in result.rows)


def test_parse_college_sports_madness_fixture():
    result = parse_college_sports_madness(
        source_key="college_sports_madness",
        source_name="College Sports Madness",
        source_url="https://example.com",
        html=_read("collegesportsmadness.html"),
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )
    assert len(result.rows) >= 2
    assert any(row.team_raw == "Texas" and row.seed == 1 for row in result.rows)


def test_parse_college_sports_madness_extracts_multiple_pairs_per_table_row():
    html = """
    <html>
      <body>
        <table>
          <tr><td>1</td><td>South Carolina</td><td>16</td><td>Howard</td></tr>
          <tr><td>8</td><td>Iowa</td><td>9</td><td>Colorado</td></tr>
        </table>
      </body>
    </html>
    """

    result = parse_college_sports_madness(
        source_key="college_sports_madness",
        source_name="College Sports Madness",
        source_url="https://example.com",
        html=html,
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )

    parsed = {(row.seed, row.team_raw) for row in result.rows}
    assert (1, "South Carolina") in parsed
    assert (16, "Howard") in parsed
    assert (8, "Iowa") in parsed
    assert (9, "Colorado") in parsed


def test_parse_espn_blocked_page_returns_no_rows():
    blocked = _read("espn_blocked.html")
    result = parse_espn(
        source_key="espn",
        source_name="ESPN",
        source_url="https://example.com",
        html=blocked,
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )
    assert len(result.rows) == 0


def test_cbssports_finds_bracketology_menu_url():
    url = cbssports._find_bracketology_menu_url(
        _read("cbssports_hub.html"),
        "https://www.cbssports.com/womens-college-basketball/",
    )

    assert url == "https://www.cbssports.com/womens-college-basketball/bracketology/"


def test_parse_cbssports_uses_menu_link_and_parses_article(monkeypatch):
    hub_html = _read("cbssports_hub.html")
    article_html = _read("cbssports_article.html")
    resolved_url = (
        "https://www.cbssports.com/womens-college-basketball/news/"
        "womens-bracketology-ncaa-tournament-projections-arizona-state-march-7/"
    )

    def fake_fetch_html_response(url: str) -> tuple[str, str]:
        assert url == "https://www.cbssports.com/womens-college-basketball/bracketology/"
        return resolved_url, article_html

    monkeypatch.setattr(cbssports, "_fetch_html_response", fake_fetch_html_response)

    result = cbssports.parse_cbssports(
        source_key="cbssports",
        source_name="CBS Sports",
        source_url="https://www.cbssports.com/womens-college-basketball/",
        html=hub_html,
        scraped_at_iso="2026-03-07T20:00:00+00:00",
    )

    parsed = {(row.seed, row.team_raw, row.is_play_in) for row in result.rows}
    assert (1, "UCLA", False) in parsed
    assert (2, "South Carolina", False) in parsed
    assert (11, "Princeton", True) in parsed
    assert (11, "Villanova", True) in parsed
    assert (16, "Southern", False) in parsed
    assert all(row.source_url == resolved_url for row in result.rows)


def test_cbssports_extracts_rows_from_projection_table():
    html = """
    <html>
      <body>
        <div class="ArticleContentTable">
          <table class="team-picks-authors">
            <tbody>
              <tr>
                <td>1</td>
                <td><div class="team-name">UConn</div></td>
                <td><div class="team-name">UCLA</div></td>
              </tr>
              <tr>
                <td>11</td>
                <td><div class="team-name">Princeton / Villanova</div></td>
                <td><div class="team-name">Rhode Island</div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </body>
    </html>
    """

    pairs = cbssports._extract_pairs_from_projection_table(cbssports.to_soup(html))

    assert (1, "UConn", False) in pairs
    assert (1, "UCLA", False) in pairs
    assert (11, "Princeton", True) in pairs
    assert (11, "Villanova", True) in pairs
    assert (11, "Rhode Island", False) in pairs


def test_theix_finds_latest_bracketology_article_url():
    url = theix._find_latest_article_url(
        _read("theix_category.html"),
        "https://www.theixsports.com/category/the-ix-basketball-newsroom/ncaa-basketball/bracketology/",
    )

    assert url == "https://www.theixsports.com/features/march-1-bracketology-update/"


def test_theix_finds_primary_image_url_from_article_html():
    image_url = theix._find_primary_image_url(
        _read("theix_article.html"),
        "https://www.theixsports.com/features/march-1-bracketology-update/",
    )

    assert image_url == "https://cdn.theixsports.com/images/main-bracket.jpg"


def test_theix_prefers_full_resolution_srcset_image():
    html = """
    <html>
      <body>
        <article>
          <img
            src="https://cdn.theixsports.com/images/bracketology-99-780x410.png"
            srcset="https://cdn.theixsports.com/images/bracketology-99-780x410.png 780w,
                    https://cdn.theixsports.com/images/bracketology-99-1200x630.png 1200w,
                    https://cdn.theixsports.com/images/bracketology-99.png 1600w"
            alt="Bracketology update"
            class="wp-post-image"
          />
        </article>
      </body>
    </html>
    """

    image_urls = theix._find_primary_image_urls(html, "https://www.theixsports.com/example-article/")

    assert image_urls[0] == "https://cdn.theixsports.com/images/bracketology-99.png"


def test_theix_extracts_seed_team_pairs_from_ocr_text():
    ocr_text = """
    1 UCLA 16 Norfolk State
    8 Iowa State 9 Colorado
    2 Texas 15 Albany
    """

    pairs = theix._extract_pairs_from_ocr_text(ocr_text)

    assert (1, "UCLA", False) in pairs
    assert (16, "Norfolk State", False) in pairs
    assert (8, "Iowa State", False) in pairs
    assert (9, "Colorado", False) in pairs


def test_theix_extracts_pairs_when_seed_and_team_are_split_lines():
    ocr_text = """
    1
    UCLA
    16
    Norfolk State
    8 Iowa State
    9
    Colorado
    """

    pairs = theix._extract_pairs_from_ocr_text(ocr_text)

    assert (1, "UCLA", False) in pairs
    assert (16, "Norfolk State", False) in pairs
    assert (8, "Iowa State", False) in pairs
    assert (9, "Colorado", False) in pairs


def test_theix_cleans_common_ocr_team_artifacts():
    ocr_text = """
    2 lowa
    3 Illinois Storrs
    13 McNeese St I
    """

    pairs = theix._extract_pairs_from_ocr_text(ocr_text)

    assert (2, "Iowa", False) in pairs
    assert (3, "Illinois", False) in pairs
    assert (13, "McNeese St", False) in pairs


def test_theix_parses_openai_json_content():
    content = """
    [
      {"seed": 1, "team": "UCLA", "is_play_in": false},
      {"seed": "2", "team": "lowa", "is_play_in": false},
      {"seed": 13, "team": "McNeese St I", "is_play_in": false}
    ]
    """

    pairs = theix._pairs_from_openai_content(content)

    assert (1, "UCLA", False) in pairs
    assert (2, "Iowa", False) in pairs
    assert (13, "McNeese St", False) in pairs


def test_theix_parses_openai_json_object_entries_content():
    content = """
    {
      "entries": [
        {"seed": 1, "team": "UCLA", "is_play_in": false},
        {"seed": 2, "team": "Iowa", "is_play_in": false}
      ]
    }
    """

    pairs = theix._pairs_from_openai_content(content)

    assert (1, "UCLA", False) in pairs
    assert (2, "Iowa", False) in pairs


def test_parse_theix_uses_latest_article_and_ocr(monkeypatch):
    category_html = _read("theix_category.html")
    article_html = _read("theix_article.html")
    article_url = "https://www.theixsports.com/features/march-1-bracketology-update/"
    image_url = "https://cdn.theixsports.com/images/main-bracket.jpg"
    ocr_lines = [f"{seed} {team}" for seed, team, _ in _balanced_pairs(4)]
    ocr_text = "\n".join(ocr_lines)

    def fake_fetch_html(url: str) -> str:
        if url == article_url:
            return article_html
        raise AssertionError(f"Unexpected HTML URL: {url}")

    def fake_fetch_image(url: str) -> bytes:
        if url == image_url:
            return b"fake-image"
        raise AssertionError(f"Unexpected image URL: {url}")

    monkeypatch.setattr(theix, "_fetch_html", fake_fetch_html)
    monkeypatch.setattr(theix, "_fetch_image_bytes", fake_fetch_image)
    monkeypatch.setattr(theix, "_ocr_image_text", lambda _: ocr_text)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = theix.parse_the_ix(
        source_key="the_ix",
        source_name="The IX",
        source_url="https://www.theixsports.com/category/the-ix-basketball-newsroom/ncaa-basketball/bracketology/",
        html=category_html,
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )

    assert result.updated_at_raw == "March 2, 2026"
    assert len(result.rows) == 64
    assert result.rows[0].source_url == article_url


def test_parse_theix_prefers_openai_when_available(monkeypatch):
    category_html = _read("theix_category.html")
    article_html = _read("theix_article.html")
    article_url = "https://www.theixsports.com/features/march-1-bracketology-update/"

    def fake_fetch_html(url: str) -> str:
        if url == article_url:
            return article_html
        raise AssertionError(f"Unexpected HTML URL: {url}")

    openai_pairs = _balanced_pairs(4)

    monkeypatch.setattr(theix, "_fetch_html", fake_fetch_html)
    monkeypatch.setattr(theix, "_extract_pairs_with_openai", lambda **_: openai_pairs)
    monkeypatch.setattr(theix, "_fetch_image_bytes", lambda _: (_ for _ in ()).throw(AssertionError("OCR fallback should not run")))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = theix.parse_the_ix(
        source_key="the_ix",
        source_name="The IX",
        source_url="https://www.theixsports.com/category/the-ix-basketball-newsroom/ncaa-basketball/bracketology/",
        html=category_html,
        scraped_at_iso="2026-03-06T00:00:00+00:00",
    )

    assert len(result.rows) == 64


def test_theix_quality_validation_rules():
    with_seed_gap = [(1, "Team AA", False)] * 4
    with_seed_gap.extend((seed, f"Team {seed}", False) for seed in range(2, 16))

    try:
        theix._validate_bracket_quality(with_seed_gap)
        assert False, "expected validation error for missing seed coverage"
    except RuntimeError as exc:
        assert "too few teams for seed" in str(exc)

    too_many = _balanced_pairs(5)
    too_many.extend([(1, "Team ZZ", False), (2, "Team ZY", False), (3, "Team ZX", False), (4, "Team ZW", False)])
    try:
        theix._validate_bracket_quality(too_many)
        assert False, "expected validation error for too many rows"
    except RuntimeError as exc:
        assert "too many rows" in str(exc)


def test_theix_applies_known_corrections():
    pairs = [
        (8, "Illinois State", False),
        (8, "Illinois", False),
        (5, "Notre Dame", False),
    ]

    corrected = theix._apply_the_ix_known_corrections(pairs)

    assert (8, "Illinois", False) in corrected
    assert (8, "Illinois State", False) not in corrected


def test_theix_corrects_nc_state_misread_when_missing():
    pairs = [
        (4, "North Carolina", False),
        (1, "UConn", False),
    ]

    corrected = theix._apply_the_ix_known_corrections(pairs)

    assert (4, "NC State", False) in corrected
    assert (4, "North Carolina", False) not in corrected
