from playwright.sync_api import Page
from playwright_manager import PlaywrightManager

STOCK_SELECTORS = {
    "target": {
        "in_stock":    "button[data-test='shipItButton']:not([disabled])",
        "out_of_stock": "[data-test='outOfStock']",
    },
    "walmart": {
        "in_stock":    "button[data-automation-id='atc-button']:not([disabled])",
        "out_of_stock": "[data-automation-id='out-of-stock']",
    },
}


def check_stock(pw: PlaywrightManager, product: dict) -> bool:
    retailer  = product.get("retailer", "")
    url       = product["url"]
    selectors = STOCK_SELECTORS.get(retailer)
    if not selectors:
        return False

    def _check(page: Page) -> bool:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if page.query_selector(selectors["out_of_stock"]):
                return False
            try:
                page.wait_for_selector(selectors["in_stock"], timeout=6000)
                return True
            except:
                return False
        except:
            return False

    try:
        return pw.submit(_check, f"stock:{product['name'][:30]}", timeout=30)
    except:
        return False