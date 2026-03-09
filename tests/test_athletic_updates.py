from pathlib import Path

from bracket_matrix import athletic_updates


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_check_for_new_athletic_update_reports_missing_manual_url(monkeypatch, tmp_path):
    state_file = tmp_path / "athletic_last_seen.txt"
    manual_html_path = tmp_path / "the_athletic_latest.html"
    tag_html = _read("theathletic_tag.html")

    monkeypatch.setattr(
        athletic_updates,
        "fetch_html",
        lambda url, timeout_seconds, user_agent: tag_html,
    )

    result = athletic_updates.check_for_new_athletic_update(
        state_file=state_file,
        manual_html_path=manual_html_path,
    )

    assert result["status"] == "missing_manual_url"
    assert "women-ncaa-tournament-bracket-watch" in result["latest_url"]
    assert not state_file.exists()


def test_check_for_new_athletic_update_detects_new_article(monkeypatch, tmp_path):
    state_file = tmp_path / "athletic_last_seen.txt"
    state_file.write_text(
        "https://www.nytimes.com/athletic/7061111/2026/02/28/women-ncaa-tournament-bracket-watch-conference-races/\n",
        encoding="utf-8",
    )
    tag_html = _read("theathletic_tag.html")

    monkeypatch.setattr(
        athletic_updates,
        "fetch_html",
        lambda url, timeout_seconds, user_agent: tag_html,
    )

    sent: dict[str, str] = {}

    def fake_send_email_notification(*, to_email: str, subject: str, body: str) -> None:
        sent["to_email"] = to_email
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(athletic_updates, "send_email_notification", fake_send_email_notification)

    result = athletic_updates.check_for_new_athletic_update(
        state_file=state_file,
        notify_email="me@example.com",
    )

    assert result["status"] == "updated"
    assert sent["to_email"] == "me@example.com"
    assert "New The Athletic Women's Bracket Watch update" in sent["subject"]
    assert result["latest_url"] in sent["body"]
    assert state_file.read_text(encoding="utf-8").strip().startswith("https://www.nytimes.com/athletic/7061111/")


def test_check_for_new_athletic_update_no_change(monkeypatch, tmp_path):
    state_file = tmp_path / "athletic_last_seen.txt"
    latest_url = "https://www.nytimes.com/athletic/7092398/2026/03/06/women-ncaa-tournament-bracket-watch-uconn-ucla/"
    state_file.write_text(f"{latest_url}\n", encoding="utf-8")

    monkeypatch.setattr(
        athletic_updates,
        "fetch_html",
        lambda url, timeout_seconds, user_agent: _read("theathletic_tag.html"),
    )

    result = athletic_updates.check_for_new_athletic_update(state_file=state_file)

    assert result["status"] == "no_change"
    assert result["latest_url"] == latest_url


def test_check_for_new_athletic_update_uses_manual_html_when_state_file_missing(monkeypatch, tmp_path):
    state_file = tmp_path / "athletic_last_seen.txt"
    manual_html = tmp_path / "the_athletic_latest.html"
    latest_url = "https://www.nytimes.com/athletic/7092398/2026/03/06/women-ncaa-tournament-bracket-watch-uconn-ucla/"
    manual_html.write_text(
        f"<html><head><meta property=\"og:url\" content=\"{latest_url}\" /></head><body></body></html>",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        athletic_updates,
        "fetch_html",
        lambda url, timeout_seconds, user_agent: _read("theathletic_tag.html"),
    )

    result = athletic_updates.check_for_new_athletic_update(
        state_file=state_file,
        manual_html_path=manual_html,
    )

    assert result["status"] == "no_change"
    assert result["latest_url"] == latest_url
