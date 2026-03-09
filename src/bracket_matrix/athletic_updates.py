from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from bracket_matrix.config import get_default_paths
from bracket_matrix.scrapers.common import fetch_html, fetch_html_playwright, normalize_ws
from bracket_matrix.scrapers.theathletic import _find_latest_bracket_watch_article_url


ATHLETIC_TAG_URL = "https://www.nytimes.com/athletic/tag/bracketcentral/"


def default_state_file() -> Path:
    return get_default_paths().data_dir / "manual" / "the_athletic_latest_url.txt"


def _read_last_seen_url(state_file: Path) -> str:
    if not state_file.exists():
        return ""
    return normalize_ws(state_file.read_text(encoding="utf-8"))


def _notification_email_from_env() -> str:
    return normalize_ws(os.getenv("GMAIL_TO", ""))


def _gmail_credentials_from_env() -> tuple[str, str]:
    user = normalize_ws(os.getenv("GMAIL_USER", ""))
    app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    return user, app_password


def send_email_notification(*, to_email: str, subject: str, body: str) -> None:
    recipient = normalize_ws(to_email) or _notification_email_from_env()
    if not recipient:
        raise RuntimeError("Set --notify-email or GMAIL_TO")

    gmail_user, gmail_app_password = _gmail_credentials_from_env()
    if not gmail_user or not gmail_app_password:
        raise RuntimeError("Set GMAIL_USER and GMAIL_APP_PASSWORD to send notification email")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_app_password)
        server.send_message(msg)


def check_for_new_athletic_update(
    *,
    state_file: Path | None = None,
    notify_email: str = "",
    use_playwright: bool = False,
    timeout_seconds: int = 20,
) -> dict[str, str]:
    target_state_file = state_file or default_state_file()

    if use_playwright:
        html = fetch_html_playwright(ATHLETIC_TAG_URL, timeout_seconds=timeout_seconds)
    else:
        html = fetch_html(
            ATHLETIC_TAG_URL,
            timeout_seconds=timeout_seconds,
            user_agent="Mozilla/5.0 (compatible; WBBBracketMatrix/0.1; +https://github.com/)",
        )

    latest_url = _find_latest_bracket_watch_article_url(html, ATHLETIC_TAG_URL)
    if not latest_url:
        raise RuntimeError("Could not find latest Women's Bracket Watch URL on The Athletic tag page")

    previous_url = _read_last_seen_url(target_state_file)
    if not previous_url:
        return {
            "status": "missing_manual_url",
            "latest_url": latest_url,
            "previous_url": "",
            "state_file": str(target_state_file),
        }

    if previous_url == latest_url:
        return {
            "status": "no_change",
            "latest_url": latest_url,
            "previous_url": previous_url,
            "state_file": str(target_state_file),
        }

    if notify_email:
        send_email_notification(
            to_email=notify_email,
            subject="New The Athletic Women's Bracket Watch update",
            body=(
                "The Athletic Women's Bracket Watch appears out of date in your manual file.\n\n"
                f"Manual URL: {previous_url}\n"
                f"Latest URL: {latest_url}\n"
                f"Manual file: {target_state_file}\n"
            ),
        )

    return {
        "status": "updated",
        "latest_url": latest_url,
        "previous_url": previous_url,
        "state_file": str(target_state_file),
    }
