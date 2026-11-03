import json
from collections import Counter

import pytest

from bracket_matrix import pipeline
from bracket_matrix.analytics import parse_bart_power_csv
from bracket_matrix.config import PipelinePaths
from bracket_matrix.render import _projected_seed_numbers, split_projected_field
from bracket_matrix.scrapers.espn import parse_espn
from bracket_matrix.scrapers.herhoopstats import parse_her_hoop_stats
from bracket_matrix.scrapers.theix import _validate_bracket_quality
from bracket_matrix.season import SourceUnavailable, validate_ncaa_rankings_date
from bracket_matrix.types import MatrixRow


def test_opening_round_has_twelve_teams_in_each_category_and_64_slots():
    rows = [MatrixRow(str(i), f"Team {i}", "", "", 2, i, source_seeds={}) for i in range(76)]
    autobids = {str(i) for i in range(44, 76)}
    seeds = _projected_seed_numbers(rows, autobids)
    assert sum(str(seed).endswith('/OR') for seed in seeds[:44]) == 12
    assert sum(str(seed).endswith('/OR') for seed in seeds[44:]) == 12
    slots = Counter()
    for seed in seeds:
        number = int(str(seed).split('/')[0])
        slots[number] += 0.5 if isinstance(seed, str) else 1
    assert slots == {seed: 4 for seed in range(1, 17)}
    projected, other = split_projected_field(rows + [MatrixRow('out', 'Out', '', '', 1, 99)])
    assert len(projected) == 76
    assert len(other) == 1


def test_hhs_collects_both_play_in_teams_once_and_parses_october_date():
    html = '''<div class="update-date">Oct. 26, 2026 11:09PM ET</div>
    <table><tr class="first-4"><td><span class="seed">16</span><a href="/stats/ncaa/team/a">A</a></td></tr>
    <tr><td><span class="seed">16</span><a href="/stats/ncaa/team/a">A</a>/<a href="/stats/ncaa/team/b">B</a></td></tr></table>'''
    result = parse_her_hoop_stats(source_key='hhs', source_name='HHS', source_url='https://example.com', html=html, scraped_at_iso='')
    assert [(r.team_raw, r.is_play_in) for r in result.rows] == [('A', True), ('B', True)]
    assert result.updated_at_iso == '2026-10-27T03:09:00+00:00'


def test_espn_json_extracts_both_opening_round_teams_and_bubble():
    data = {'tournamentName': 'NCAAW', 'pageContent': {'publishedAt': '10/27/2026 7:55'},
            'bracket': [{'podCities': [{'matchups': [{'slotA': {'seedNumber': 11,
                'team': {'apiData': {'shortDisplayName': 'Miami'}},
                'playInTeam': {'apiData': {'shortDisplayName': 'Indiana'}}}}]}]}],
            'Bubble': {'First Four Out': {'teams': [{'shortDisplayName': 'Davidson'}]}}}
    result = parse_espn(source_key='espn', source_name='ESPN', source_url='https://example.com', html=json.dumps(data), scraped_at_iso='')
    assert [(r.seed, r.team_raw, r.is_play_in) for r in result.rows] == [(11, 'Miami', True), (11, 'Indiana', True), ('FFO', 'Davidson', False)]
    assert result.updated_at_iso.startswith('2026-10-27')


def test_ncaa_rankings_date_ignores_current_season_sidebar():
    html = '<p>Through Games Apr. 05 2026</p><aside>2026-27 preseason rankings</aside>'
    with pytest.raises(SourceUnavailable, match='Previous-season'):
        validate_ncaa_rankings_date(html, {'season_start_date': '2026-07-01'})


def test_bart_csv_and_ix_support_expanded_field():
    rows = parse_bart_power_csv('rank,team,conf,barthag\n1,Connecticut,BE,.999\n')
    assert rows[0]['bart_rank'] == '1'
    pairs = [(seed, f'Team {seed}-{i}', False) for seed in range(1, 17) for i in range(4)]
    _validate_bracket_quality(pairs + [(16, f'Opening {i}', True) for i in range(12)])


@pytest.mark.parametrize('updated_at,enabled,expected', [
    ('2026-03-15T00:00:00+00:00', True, 'unavailable'),
    ('', True, 'unavailable'),
    ('2026-10-27T00:00:00+00:00', False, 'unavailable'),
    ('2026-10-27T00:00:00+00:00', True, 'ok'),
])
def test_scrape_season_guard(tmp_path, monkeypatch, updated_at, enabled, expected):
    from bracket_matrix.io_utils import read_dict_csv
    from bracket_matrix.types import ScrapeResult, SourceProjectionRow
    paths = PipelinePaths(tmp_path, tmp_path/'config', tmp_path/'data', tmp_path/'data/latest', tmp_path/'data/snapshots', tmp_path/'site')
    paths.config_dir.mkdir()
    (paths.config_dir/'settings.json').write_text(json.dumps({'request_timeout_seconds': 1, 'user_agent': 'test', 'season_start_date': '2026-07-01', 'tournament_field_size': 1}))
    (paths.config_dir/'sources.json').write_text(json.dumps({'sources': [{'source_key': 'test', 'source_name': 'Test', 'source_url': 'https://example.com', 'parser': 'test', 'enabled': enabled}]}))
    row = SourceProjectionRow('test', 'Test', 'https://example.com', '', updated_at, 'Team', 1, False, '')
    monkeypatch.setitem(pipeline.PARSERS, 'test', lambda **kw: ScrapeResult([row], '', updated_at))
    pipeline.run_scrape(paths=paths, fetcher=lambda *a, **kw: '<html/>')
    assert read_dict_csv(paths.latest_dir/'source_status_latest.csv')[0]['status'] == expected
    assert len(read_dict_csv(paths.latest_dir/'source_rows_latest.csv')) == (1 if expected == 'ok' else 0)
