from __future__ import annotations

import os
from pathlib import Path

from bracket_matrix.scrapers.common import normalize_ws

from bracket_matrix.config import get_default_paths


AUTH_SOURCE_URLS = {
    "the_athletic": "https://www.nytimes.com/athletic/tag/bracketcentral/",
}


def run_auth_login(
    *,
    source_key: str,
    output_path: Path | None = None,
    url: str | None = None,
    timeout_seconds: int = 60,
) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed") from exc

    if source_key not in AUTH_SOURCE_URLS:
        raise ValueError(f"unsupported auth source: {source_key}")

    target_url = url or AUTH_SOURCE_URLS[source_key]
    default_output = get_default_paths().data_dir / f"{source_key}_storage_state.json"
    destination = output_path or default_output
    destination.parent.mkdir(parents=True, exist_ok=True)

    channel = normalize_ws(os.getenv("BRACKET_MATRIX_PLAYWRIGHT_CHANNEL", ""))
    launch_kwargs: dict[str, object] = {
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if channel:
        launch_kwargs["channel"] = channel

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context()
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.goto(target_url, timeout=timeout_seconds * 1000, wait_until="domcontentloaded")
        input("Complete login in the browser, then press Enter...")
        context.storage_state(path=str(destination))
        context.close()
        browser.close()

    return destination
