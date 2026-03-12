from __future__ import annotations

import re
from difflib import SequenceMatcher

from bracket_matrix.normalize import load_aliases, normalize_team_name, resolve_team_names
from bracket_matrix.scrapers.common import normalize_ws, to_soup

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


NCAA_WAB_RANKING_URL = "https://www.ncaa.com/rankings/basketball-women/d1/wab-ranking"
NCAA_NET_RANKING_URL = "https://www.ncaa.com/rankings/basketball-women/d1/ncaa-womens-basketball-net-rankings"
NCAA_AUTO_BIDS_URL = "https://www.ncaa.com/news/basketball-women/article/2026-02-17/tracking-all-31-ncaa-womens-basketball-conference-tournaments-auto-bids-march"
BART_POWER_URL = "https://barttorvik.com/ncaaw/#"


def _parse_record_wins_losses(record: str) -> tuple[str, str]:
    cleaned = normalize_ws(record)
    match = re.match(r"^(\d+)\s*-\s*(\d+)$", cleaned)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _find_header_index(headers: list[str], candidates: set[str]) -> int:
    for index, header in enumerate(headers):
        if normalize_ws(header).lower() in candidates:
            return index
    return -1


def parse_ncaa_wab_table(html: str) -> list[dict[str, str]]:
    soup = to_soup(html)
    for table in soup.select("table"):
        header_cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in table.select("thead th")]
        if not header_cells:
            first_row = table.select_one("tr")
            if first_row:
                header_cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in first_row.select("th,td")]

        team_idx = _find_header_index(header_cells, {"team", "school"})
        conf_idx = _find_header_index(header_cells, {"conference", "conf"})
        rank_idx = _find_header_index(header_cells, {"rank", "rk"})
        wab_idx = _find_header_index(header_cells, {"wab"})

        required = [team_idx, conf_idx, rank_idx, wab_idx]
        if any(idx < 0 for idx in required):
            continue

        parsed_rows: list[dict[str, str]] = []
        for row in table.select("tbody tr") or table.select("tr")[1:]:
            cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in row.select("td")]
            if not cells:
                continue

            max_idx = max(required)
            if len(cells) <= max_idx:
                continue

            team = cells[team_idx]
            if not team:
                continue

            parsed_rows.append(
                {
                    "team": team,
                    "conference": cells[conf_idx],
                    "wab_rank": cells[rank_idx],
                    "wab": cells[wab_idx],
                }
            )

        if parsed_rows:
            return parsed_rows

    raise RuntimeError("Unable to parse NCAA WAB rankings table")


def parse_ncaa_net_table(html: str) -> list[dict[str, str]]:
    soup = to_soup(html)
    for table in soup.select("table"):
        header_cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in table.select("thead th")]
        if not header_cells:
            first_row = table.select_one("tr")
            if first_row:
                header_cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in first_row.select("th,td")]

        rank_idx = _find_header_index(header_cells, {"rank", "rk"})
        team_idx = _find_header_index(header_cells, {"team", "school"})
        conf_idx = _find_header_index(header_cells, {"conference", "conf"})
        q1_idx = _find_header_index(header_cells, {"quad 1", "q1"})
        q2_idx = _find_header_index(header_cells, {"quad 2", "q2"})
        q3_idx = _find_header_index(header_cells, {"quad 3", "q3"})
        q4_idx = _find_header_index(header_cells, {"quad 4", "q4"})

        required = [rank_idx, team_idx, conf_idx, q1_idx, q2_idx, q3_idx, q4_idx]
        if any(idx < 0 for idx in required):
            continue

        parsed_rows: list[dict[str, str]] = []
        for row in table.select("tbody tr") or table.select("tr")[1:]:
            cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in row.select("td")]
            if not cells:
                continue

            max_idx = max(required)
            if len(cells) <= max_idx:
                continue

            team = cells[team_idx]
            if not team:
                continue

            q1_w, q1_l = _parse_record_wins_losses(cells[q1_idx])
            q2_w, q2_l = _parse_record_wins_losses(cells[q2_idx])
            q3_w, q3_l = _parse_record_wins_losses(cells[q3_idx])
            q4_w, q4_l = _parse_record_wins_losses(cells[q4_idx])

            parsed_rows.append(
                {
                    "team": team,
                    "conference": cells[conf_idx],
                    "net_rank": cells[rank_idx],
                    "q1_w": q1_w,
                    "q1_l": q1_l,
                    "q2_w": q2_w,
                    "q2_l": q2_l,
                    "q3_w": q3_w,
                    "q3_l": q3_l,
                    "q4_w": q4_w,
                    "q4_l": q4_l,
                }
            )

        if parsed_rows:
            return parsed_rows

    raise RuntimeError("Unable to parse NCAA NET rankings table")


def parse_ncaa_auto_bids_table(html: str) -> list[dict[str, str]]:
    soup = to_soup(html)
    for table in soup.select("table"):
        header_cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in table.select("thead th")]
        if not header_cells:
            first_row = table.select_one("tr")
            if first_row:
                header_cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in first_row.select("th,td")]

        conference_idx = _find_header_index(header_cells, {"conference"})
        auto_bid_idx = _find_header_index(header_cells, {"automatic bid", "automatic bids"})
        if conference_idx < 0 or auto_bid_idx < 0:
            continue

        rows: list[dict[str, str]] = []
        for row in table.select("tbody tr") or table.select("tr")[1:]:
            cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in row.select("td")]
            if not cells:
                continue
            if len(cells) <= max(conference_idx, auto_bid_idx):
                continue

            conference = cells[conference_idx]
            team = cells[auto_bid_idx]
            if not conference or not team:
                continue

            rows.append({"conference": conference, "team": team})

        if rows:
            return rows

    raise RuntimeError("Unable to parse NCAA automatic bids table")


def combine_ncaa_wab_and_net_rows(
    *,
    wab_rows: list[dict[str, str]],
    net_rows: list[dict[str, str]],
    aliases_path,
    fuzzy_threshold: float,
    fuzzy_review_threshold: float,
    fuzzy_ambiguous_margin: float,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    aliases = load_aliases(aliases_path)
    team_names = [row["team"] for row in wab_rows] + [row["team"] for row in net_rows]
    resolved, unresolved = resolve_team_names(
        team_names=team_names,
        aliases=aliases,
        fuzzy_threshold=fuzzy_threshold,
        fuzzy_review_threshold=fuzzy_review_threshold,
        fuzzy_ambiguous_margin=fuzzy_ambiguous_margin,
    )

    mapping_issues: list[dict[str, str]] = [
        {
            "issue_type": "unresolved_name",
            "source": "ncaa",
            "team_raw": item.team_raw,
            "canonical_slug": item.best_match_slug,
            "detail": f"best_score={item.best_score}; second_score={item.second_score}",
        }
        for item in unresolved
    ]

    wab_by_slug: dict[str, dict[str, str]] = {}
    net_by_slug: dict[str, dict[str, str]] = {}
    identity_by_slug = {}

    for source_name, rows, target in [
        ("ncaa_wab", wab_rows, wab_by_slug),
        ("ncaa_net", net_rows, net_by_slug),
    ]:
        for row in rows:
            team = row.get("team", "")
            resolution = resolved.get(team)
            if resolution is None:
                continue
            slug = resolution.identity.canonical_slug
            identity_by_slug[slug] = resolution.identity
            existing = target.get(slug)
            if existing is not None and existing.get("team", "") != team:
                mapping_issues.append(
                    {
                        "issue_type": "duplicate_canonical_in_source",
                        "source": source_name,
                        "team_raw": team,
                        "canonical_slug": slug,
                        "detail": f"Conflicts with '{existing.get('team', '')}'",
                    }
                )
                continue
            target[slug] = row

    combined_rows: list[dict[str, str]] = []
    for slug in sorted(set(wab_by_slug) | set(net_by_slug)):
        identity = identity_by_slug.get(slug)
        if identity is None:
            continue

        wab_row = wab_by_slug.get(slug, {})
        net_row = net_by_slug.get(slug, {})
        if not wab_row:
            mapping_issues.append(
                {
                    "issue_type": "missing_in_ncaa_wab",
                    "source": "ncaa_wab",
                    "team_raw": net_row.get("team", identity.team_display),
                    "canonical_slug": slug,
                    "detail": "Present in NET page only",
                }
            )
        if not net_row:
            mapping_issues.append(
                {
                    "issue_type": "missing_in_ncaa_net",
                    "source": "ncaa_net",
                    "team_raw": wab_row.get("team", identity.team_display),
                    "canonical_slug": slug,
                    "detail": "Present in WAB page only",
                }
            )

        combined_rows.append(
            {
                "team": identity.team_display,
                "conference": net_row.get("conference") or wab_row.get("conference", ""),
                "net_rank": net_row.get("net_rank", ""),
                "wab_rank": wab_row.get("wab_rank", ""),
                "wab": wab_row.get("wab", ""),
                "q1_w": net_row.get("q1_w", ""),
                "q1_l": net_row.get("q1_l", ""),
                "q2_w": net_row.get("q2_w", ""),
                "q2_l": net_row.get("q2_l", ""),
                "q3_w": net_row.get("q3_w", ""),
                "q3_l": net_row.get("q3_l", ""),
                "q4_w": net_row.get("q4_w", ""),
                "q4_l": net_row.get("q4_l", ""),
            }
        )

    combined_rows.sort(key=lambda row: row["team"].lower())
    mapping_issues.sort(key=lambda row: (row["issue_type"], row["source"], row["team_raw"].lower()))
    return combined_rows, mapping_issues


def parse_bart_power_table(html: str) -> list[dict[str, str]]:
    soup = to_soup(html)
    for table in soup.select("table"):
        header_row = None
        header_cells: list[str] = []
        for candidate in table.select("tr"):
            candidate_headers = [normalize_ws(cell.get_text(" ", strip=True)) for cell in candidate.select("th")]
            if not candidate_headers:
                continue
            rank_idx = _find_header_index(candidate_headers, {"rk", "rank"})
            team_idx = _find_header_index(candidate_headers, {"team"})
            conf_idx = _find_header_index(candidate_headers, {"conf", "conference"})
            barthag_idx = _find_header_index(candidate_headers, {"barthag"})
            required = [rank_idx, team_idx, conf_idx, barthag_idx]
            if all(idx >= 0 for idx in required):
                header_row = candidate
                header_cells = candidate_headers
                break
        if header_row is None:
            continue

        rank_idx = _find_header_index(header_cells, {"rk", "rank"})
        team_idx = _find_header_index(header_cells, {"team"})
        conf_idx = _find_header_index(header_cells, {"conf", "conference"})
        barthag_idx = _find_header_index(header_cells, {"barthag"})
        required = [rank_idx, team_idx, conf_idx, barthag_idx]

        rows: list[dict[str, str]] = []
        started = False
        for row in table.select("tr"):
            if row is header_row:
                started = True
                continue
            if not started:
                continue
            td_cells = row.select("td")
            if not td_cells:
                continue

            cells = [normalize_ws(cell.get_text(" ", strip=True)) for cell in td_cells]
            if len(cells) <= max(required):
                continue

            rank = cells[rank_idx]
            if not re.fullmatch(r"\d+", rank):
                continue

            team_name = cells[team_idx]
            team_cell = td_cells[team_idx]
            team_link = team_cell.select_one("a")
            if team_link is not None:
                primary_team_text = team_link.find(string=True, recursive=False)
                if primary_team_text:
                    team_name = normalize_ws(str(primary_team_text))
            if not team_name:
                continue
            if re.search(r"\bvs\.?\b", team_name, flags=re.IGNORECASE):
                continue

            barthag_cell = cells[barthag_idx]
            barthag_match = re.search(r"-?(?:\d+\.\d+|\.\d+)", barthag_cell)
            barthag = barthag_match.group(0) if barthag_match else ""

            rows.append(
                {
                    "team": team_name,
                    "conference": cells[conf_idx],
                    "bart_rank": rank,
                    "barthag": barthag,
                }
            )
        if rows:
            return rows

    raise RuntimeError("Unable to parse Bart Torvik table")


def merge_analytics_rows(
    *,
    ncaa_rows: list[dict[str, str]],
    bart_rows: list[dict[str, str]],
    aliases_path,
    fuzzy_threshold: float,
    fuzzy_review_threshold: float,
    fuzzy_ambiguous_margin: float,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    aliases = load_aliases(aliases_path)
    team_names = [row["team"] for row in ncaa_rows] + [row["team"] for row in bart_rows]
    resolved, unresolved = resolve_team_names(
        team_names=team_names,
        aliases=aliases,
        fuzzy_threshold=fuzzy_threshold,
        fuzzy_review_threshold=fuzzy_review_threshold,
        fuzzy_ambiguous_margin=fuzzy_ambiguous_margin,
    )

    mapping_issues: list[dict[str, str]] = [
        {
            "issue_type": "unresolved_name",
            "source": "either",
            "team_raw": item.team_raw,
            "canonical_slug": item.best_match_slug,
            "detail": f"best_score={item.best_score}; second_score={item.second_score}",
        }
        for item in unresolved
    ]

    ncaa_by_slug: dict[str, dict[str, str]] = {}
    bart_by_slug: dict[str, dict[str, str]] = {}

    for source_name, source_rows, target in [
        ("ncaa_nitty_gritty", ncaa_rows, ncaa_by_slug),
        ("bart_torvik", bart_rows, bart_by_slug),
    ]:
        for row in source_rows:
            team = row.get("team", "")
            resolution = resolved.get(team)
            if resolution is None:
                mapping_issues.append(
                    {
                        "issue_type": "unmapped_row",
                        "source": source_name,
                        "team_raw": team,
                        "canonical_slug": "",
                        "detail": "No team resolution available",
                    }
                )
                continue

            slug = resolution.identity.canonical_slug
            existing = target.get(slug)
            if existing is not None and existing.get("team", "") != team:
                mapping_issues.append(
                    {
                        "issue_type": "duplicate_canonical_in_source",
                        "source": source_name,
                        "team_raw": team,
                        "canonical_slug": slug,
                        "detail": f"Conflicts with '{existing.get('team', '')}'",
                    }
                )
                continue
            target[slug] = row

    all_slugs = sorted(set(ncaa_by_slug) | set(bart_by_slug))
    merged_rows: list[dict[str, str]] = []

    identity_by_slug = {}
    for team_name, resolution in resolved.items():
        identity_by_slug.setdefault(resolution.identity.canonical_slug, resolution.identity)

    for slug in all_slugs:
        identity = identity_by_slug.get(slug)
        if identity is None:
            continue

        ncaa = ncaa_by_slug.get(slug, {})
        bart = bart_by_slug.get(slug, {})
        if not ncaa:
            mapping_issues.append(
                {
                    "issue_type": "missing_in_ncaa",
                    "source": "ncaa_nitty_gritty",
                    "team_raw": bart.get("team", identity.team_display),
                    "canonical_slug": slug,
                    "detail": "Present in Bart only",
                }
            )
        if not bart:
            mapping_issues.append(
                {
                    "issue_type": "missing_in_bart",
                    "source": "bart_torvik",
                    "team_raw": ncaa.get("team", identity.team_display),
                    "canonical_slug": slug,
                    "detail": "Present in NCAA only",
                }
            )

        merged_rows.append(
            {
                "canonical_slug": slug,
                "team_display": identity.team_display,
                "conference": ncaa.get("conference") or bart.get("conference", ""),
                "ncaa_team": ncaa.get("team", ""),
                "ncaa_conference": ncaa.get("conference", ""),
                "net_rank": ncaa.get("net_rank", ""),
                "wab_rank": ncaa.get("wab_rank", ""),
                "wab": ncaa.get("wab", ""),
                "q1_w": ncaa.get("q1_w", ""),
                "q1_l": ncaa.get("q1_l", ""),
                "q2_w": ncaa.get("q2_w", ""),
                "q2_l": ncaa.get("q2_l", ""),
                "q3_w": ncaa.get("q3_w", ""),
                "q3_l": ncaa.get("q3_l", ""),
                "q4_w": ncaa.get("q4_w", ""),
                "q4_l": ncaa.get("q4_l", ""),
                "bart_team": bart.get("team", ""),
                "bart_conference": bart.get("conference", ""),
                "bart_rank": bart.get("bart_rank", ""),
                "barthag": bart.get("barthag", ""),
                "present_in_ncaa": "1" if ncaa else "0",
                "present_in_bart": "1" if bart else "0",
            }
        )

    merged_rows.sort(key=lambda row: row["team_display"].lower())
    mapping_issues.sort(key=lambda row: (row["issue_type"], row["source"], row["team_raw"].lower()))
    return merged_rows, mapping_issues


def _cross_source_candidate_scores(merged_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    ncaa_only = [row for row in merged_rows if row.get("present_in_ncaa") == "1" and row.get("present_in_bart") == "0"]
    bart_only = [row for row in merged_rows if row.get("present_in_ncaa") == "0" and row.get("present_in_bart") == "1"]
    if not ncaa_only or not bart_only:
        return []

    candidates: list[dict[str, str]] = []
    for ncaa_row in ncaa_only:
        ncaa_team = ncaa_row.get("team_display", "")
        ncaa_norm = normalize_team_name(ncaa_team)
        ncaa_conf = normalize_ws(ncaa_row.get("conference", "")).lower()

        for bart_row in bart_only:
            bart_team = bart_row.get("team_display", "")
            bart_norm = normalize_team_name(bart_team)

            if fuzz is not None:
                name_score = float(fuzz.ratio(ncaa_norm, bart_norm))
                token_score = float(fuzz.token_set_ratio(ncaa_norm, bart_norm))
            else:
                name_score = SequenceMatcher(a=ncaa_norm, b=bart_norm).ratio() * 100
                token_score = name_score
            conf_match = ncaa_conf and normalize_ws(bart_row.get("conference", "")).lower() == ncaa_conf
            combined = (name_score * 0.6) + (token_score * 0.4) + (4.0 if conf_match else 0.0)
            candidates.append(
                {
                    "ncaa_team": ncaa_team,
                    "ncaa_conference": ncaa_row.get("conference", ""),
                    "ncaa_canonical_slug": ncaa_row.get("canonical_slug", ""),
                    "bart_team_candidate": bart_team,
                    "bart_conference": bart_row.get("conference", ""),
                    "bart_canonical_slug": bart_row.get("canonical_slug", ""),
                    "name_score": f"{name_score:.2f}",
                    "conference_match": "1" if conf_match else "0",
                    "combined_score": f"{combined:.2f}",
                }
            )

    candidates.sort(
        key=lambda item: (
            -float(item["combined_score"]),
            -float(item["name_score"]),
            item["ncaa_team"].lower(),
            item["bart_team_candidate"].lower(),
        )
    )
    return candidates


def suggest_cross_source_matches(merged_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates = _cross_source_candidate_scores(merged_rows)
    grouped: dict[str, list[dict[str, str]]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate["ncaa_team"], []).append(candidate)

    suggestions: list[dict[str, str]] = []
    for ncaa_team in sorted(grouped, key=str.lower):
        top_candidates = grouped[ncaa_team][:3]
        for rank, candidate in enumerate(top_candidates, start=1):
            combined = float(candidate["combined_score"])
            conf_match = candidate["conference_match"] == "1"
            confidence = "low"
            if combined >= 95 and conf_match:
                confidence = "high"
            elif combined >= 88:
                confidence = "medium"

            suggestions.append(
                {
                    **candidate,
                    "candidate_rank": str(rank),
                    "confidence": confidence,
                    "suggested_alias": (
                        f"{candidate['ncaa_team']},{candidate['bart_canonical_slug']},{candidate['bart_team_candidate']},,"
                    ),
                }
            )

    suggestions.sort(key=lambda item: (item["ncaa_team"].lower(), int(item["candidate_rank"])))
    return suggestions


def assign_greedy_cross_source_matches(merged_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates = _cross_source_candidate_scores(merged_rows)
    used_ncaa: set[str] = set()
    used_bart: set[str] = set()
    assignments: list[dict[str, str]] = []

    for candidate in candidates:
        ncaa_slug = candidate["ncaa_canonical_slug"]
        bart_slug = candidate["bart_canonical_slug"]
        if ncaa_slug in used_ncaa or bart_slug in used_bart:
            continue

        used_ncaa.add(ncaa_slug)
        used_bart.add(bart_slug)

        combined = float(candidate["combined_score"])
        conf_match = candidate["conference_match"] == "1"
        confidence = "low"
        if combined >= 95 and conf_match:
            confidence = "high"
        elif combined >= 88:
            confidence = "medium"

        assignments.append(
            {
                **candidate,
                "confidence": confidence,
                "suggested_alias": (
                    f"{candidate['ncaa_team']},{candidate['bart_canonical_slug']},{candidate['bart_team_candidate']},,"
                ),
            }
        )

    assignments.sort(
        key=lambda item: (
            -float(item["combined_score"]),
            -float(item["name_score"]),
            item["ncaa_team"].lower(),
        )
    )
    for index, assignment in enumerate(assignments, start=1):
        assignment["assignment_rank"] = str(index)
    return assignments
