import threading
from playwright.sync_api import Page
from playwright_manager import PlaywrightManager


class CartManager:
    def __init__(self, pw: PlaywrightManager):
        self.pw    = pw
        self.cart  = []
        self._lock = threading.Lock()

    def mark_added(self, product: dict):
        with self._lock:
            if not self.is_in_cart(product["url"]):
                self.cart.append(product)

    def is_in_cart(self, url: str) -> bool:
        return url in [p["url"] for p in self.cart]

    def local_total(self) -> float:
        return sum(p.get("price", 0) for p in self.cart)

    def count(self) -> int:
        return len(self.cart)

    def clear_local(self):
        with self._lock:
            self.cart = []

    def fetch_site_cart(self) -> dict:
        def _fetch(page: Page) -> dict:
            items = []
            total = 0.0

            # Target
            try:
                page.goto("https://www.target.com/cart",
                          wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector("[data-test='cartItem']", timeout=8000)
                for el in page.query_selector_all("[data-test='cartItem']"):
                    try:
                        name  = el.query_selector(
                            "[data-test='cart-item-title']"
                        ).inner_text().strip()
                        price = float(
                            el.query_selector("[data-test='cart-item-price']")
                            .inner_text().strip()
                            .replace("$","").replace(",","")
                        )
                        href  = el.query_selector("a").get_attribute("href") or ""
                        items.append({
                            "name": name, "price": price,
                            "url":  f"https://www.target.com{href}",
                            "retailer": "target",
                        })
                        total += price
                    except:
                        continue
            except:
                pass

            # Walmart
            try:
                page.goto("https://www.walmart.com/cart",
                          wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector(
                    "[data-automation-id='cart-item']", timeout=8000)
                for el in page.query_selector_all(
                        "[data-automation-id='cart-item']"):
                    try:
                        name  = el.query_selector(
                            "[itemprop='name']"
                        ).inner_text().strip()
                        price = float(
                            el.query_selector("[itemprop='price']")
                            .get_attribute("content")
                        )
                        href  = el.query_selector("a").get_attribute("href") or ""
                        items.append({
                            "name": name, "price": price,
                            "url":  f"https://www.walmart.com{href}",
                            "retailer": "walmart",
                        })
                        total += price
                    except:
                        continue
            except:
                pass

            return {"items": items, "total": total}

        try:
            return self.pw.submit(_fetch, "fetch_site_cart", timeout=60)
        except Exception as e:
            print(f"Cart fetch error: {e}")
            return {"items": [], "total": 0.0}