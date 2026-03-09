from pathlib import Path

from bracket_matrix import athletic_updates


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_check_for_new_athletic_update_initializes_state(monkeypatch, tmp_path):
    state_file = tmp_path / "athletic_last_seen.txt"
    tag_html = _read("theathletic_tag.html")

    monkeypatch.setattr(
        athletic_updates,
        "fetch_html",
        lambda url, timeout_seconds, user_agent: tag_html,
    )

    result = athletic_updates.check_for_new_athletic_update(state_file=state_file)

    assert result["status"] == "initialized"
    assert "women-ncaa-tournament-bracket-watch" in result["latest_url"]
    assert state_file.read_text(encoding="utf-8").strip() == result["latest_url"]


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
