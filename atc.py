from playwright.sync_api import Page
from playwright_manager import PlaywrightManager
from stealth_setup import human_click, human_delay


def add_to_cart(pw: PlaywrightManager, product: dict, on_log) -> bool:
    def _atc(page: Page) -> bool:
        retailer = product.get("retailer", "")
        url      = product["url"]
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            human_delay(800, 1800)

            from captcha_handler import is_captcha_present
            if is_captcha_present(page, retailer):
                from captcha_solver import solve_with_fallback
                if not solve_with_fallback(page, product, on_log):
                    return False

            if retailer == "target":
                human_click(page, "button[data-test='shipItButton']")
                return True
            elif retailer == "walmart":
                human_click(page, "button[data-automation-id='atc-button']")
                return True
        except Exception as e:
            on_log(f"⚠️  ATC error: {e}")
        return False

    try:
        return pw.submit(_atc, f"atc:{product['name'][:30]}", timeout=45)
    except Exception as e:
        on_log(f"❌ ATC job failed: {e}")
        return False