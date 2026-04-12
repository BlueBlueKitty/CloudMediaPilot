from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


def run(base_url: str = "http://127.0.0.1:1315") -> None:
    out_dir = Path("/tmp")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1720, "height": 980})

        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console:{m.type}:{m.text}") if m.type == "error" else None,
        )

        page.goto(base_url + "/", wait_until="networkidle")
        page.fill("#loginUsername", "admin")
        page.fill("#loginPassword", "admin")
        page.click('#loginForm button[type="submit"]')
        page.wait_for_selector('#nav button[data-page="search"]', timeout=6000)

        visible_nav = page.eval_on_selector_all(
            "#nav button",
            "els => els.filter(e => e.offsetParent !== null).map(e => e.textContent.trim())",
        )
        assert len(visible_nav) == 3, f"expected 3 sidebar items, got {visible_nav}"

        page.wait_for_timeout(1500)
        recommend_cards = page.locator("#recommendGrid .trend-card").count()
        if recommend_cards == 0:
            fallback_text = (page.locator("#recommendGrid").text_content() or "").strip()
            assert fallback_text, "recommend area has neither cards nor fallback text"

        page.screenshot(path=str(out_dir / "cmp_recommend_e2e.png"), full_page=True)

        page.click('#nav button[data-page="search"]')
        page.fill("#resourceKeyword", "Inception")
        page.click("#resourceSearchBtn")
        page.wait_for_timeout(1500)
        resource_count = page.locator("#resourceList .resource-item").count()
        if resource_count == 0:
            status_text = page.locator("#status").text_content() or ""
            assert status_text, "resource list empty without status feedback"
        page.screenshot(path=str(out_dir / "cmp_search_e2e.png"), full_page=True)

        page.click('#nav button[data-page="settings"]')
        page.screenshot(path=str(out_dir / "cmp_settings_e2e.png"), full_page=True)

        assert not errors, f"console/page errors found: {errors}"
        browser.close()


if __name__ == "__main__":
    run()
