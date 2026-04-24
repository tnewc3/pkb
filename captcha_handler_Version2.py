import time
from playwright.sync_api import Page

CAPTCHA_SIGNALS = {
    "target": [
        "iframe[src*='arkoselabs']",
        "iframe[src*='funcaptcha']",
        "#challenge-form",
    ],
    "walmart": [
        "iframe[src*='recaptcha']",
        "iframe[src*='captcha']",
        ".g-recaptcha",
        "#px-captcha",
        "iframe[src*='cloudflare']",
    ],
    "generic": [
        "iframe[src*='captcha']",
        "[id*='captcha']",
        "[class*='captcha']",
        "iframe[title*='challenge']",
    ],
}

CAPTCHA_RESOLVE_SIGNALS = {
    "target": [
        "button[data-test='shipItButton']",
        "[data-test='accountNav-signIn']",
        "#username",
    ],
    "walmart": [
        "button[data-automation-id='atc-button']",
        "#email",
        ".account-menu",
    ],
}


def is_captcha_present(page: Page, retailer: str) -> bool:
    signals = (
        CAPTCHA_SIGNALS.get(retailer, []) +
        CAPTCHA_SIGNALS["generic"]
    )
    for sel in signals:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except:
            continue
    try:
        title = page.title().lower()
        url   = page.url.lower()
        block_words = ["blocked", "attention", "verify", "captcha", "challenge"]
        if any(w in title for w in block_words):
            return True
        if any(w in url for w in block_words):
            return True
    except:
        pass
    return False


def wait_for_captcha_resolution(
    page: Page,
    retailer: str,
    on_log,
    timeout: int = 300
) -> bool:
    on_log("⏸️  Waiting for manual CAPTCHA solve...")
    deadline = time.time() + timeout
    resolve_signals = CAPTCHA_RESOLVE_SIGNALS.get(retailer, [])

    while time.time() < deadline:
        if not is_captcha_present(page, retailer):
            for sel in resolve_signals:
                try:
                    if page.query_selector(sel):
                        on_log("✅ CAPTCHA resolved — resuming.")
                        return True
                except:
                    continue
        time.sleep(2)

    on_log("⏰ CAPTCHA timeout — could not resume.")
    return False