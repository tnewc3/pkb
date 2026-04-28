import json
import os
import time
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright, Page

PRODUCTS_FILE = "products.json"
SESSION_FILE  = "sessions.json"

SEARCH_TERMS = [
    "pokemon elite trainer box",
    "pokemon poster collection",
    "pokemon booster bundle",
    "pokemon pin collection",
    "pokemon blister pack",
    "pokemon tin",
    "pokemon booster box",
    "pokemon single card holo",
]

EXCLUDE_KEYWORDS = [
    "sleeve", "binder", "deck box", "playmat",
    "lot", "used", "custom", "damage", "code card",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )
}


def search_target(page: Page, term: str) -> list:
    products = []
    try:
        page.goto(
            f"https://www.target.com/s?searchTerm={quote_plus(term)}",
            wait_until="domcontentloaded", timeout=20000
        )
        page.wait_for_selector("[data-test='product-details']", timeout=12000)
        time.sleep(2)

        for card in page.query_selector_all("[data-test='product-details']"):
            try:
                name_el = card.query_selector("[data-test='product-title']")
                if not name_el:
                    continue
                name = name_el.inner_text().strip()

                link_el = card.query_selector("a")
                if not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = f"https://www.target.com{href}"

                price = 0.0
                for sel in [
                    "[data-test='product-price']",
                    ".styles__CurrentPriceFontSize",
                    "[aria-label*='current price']",
                ]:
                    price_el = card.query_selector(sel)
                    if price_el:
                        try:
                            raw = price_el.inner_text().strip()\
                                .replace("$","").replace(",","").split()[0]
                            price = float(raw)
                            break
                        except:
                            continue

                products.append({
                    "name": name, "retailer": "target",
                    "url": href, "price": price,
                })
            except:
                continue
    except Exception as e:
        print(f"  ❌ Target '{term}': {e}")
    return products


def search_walmart(page: Page, term: str) -> list:
    products = []
    try:
        page.goto(
            f"https://www.walmart.com/search?q={quote_plus(term)}",
            wait_until="domcontentloaded", timeout=20000
        )
        page.wait_for_selector(
            "[data-automation-id='product-title']", timeout=12000)
        time.sleep(2)

        for card in page.query_selector_all("div[data-item-id]"):
            try:
                name_el = card.query_selector(
                    "[data-automation-id='product-title']")
                if not name_el:
                    continue
                name = name_el.inner_text().strip()

                link_el = card.query_selector("a")
                if not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = f"https://www.walmart.com{href}"

                price = 0.0
                for sel in [
                    "[itemprop='price']",
                    "[data-automation-id='product-price'] span",
                    ".price-characteristic",
                ]:
                    price_el = card.query_selector(sel)
                    if price_el:
                        try:
                            raw = (
                                price_el.get_attribute("content") or
                                price_el.inner_text().strip()
                            ).replace("$","").replace(",","").split()[0]
                            price = float(raw)
                            break
                        except:
                            continue

                products.append({
                    "name": name, "retailer": "walmart",
                    "url": href, "price": price,
                })
            except:
                continue
    except Exception as e:
        print(f"  ❌ Walmart '{term}': {e}")
    return products


def filter_products(products: list) -> list:
    seen, out = set(), []
    for p in products:
        nl = p["name"].lower()
        if "pokemon" not in nl and "pokémon" not in nl:
            continue
        if any(kw in nl for kw in EXCLUDE_KEYWORDS):
            continue
        if p["url"] in seen:
            continue
        if p["price"] == 0.0:
            continue
        seen.add(p["url"])
        out.append(p)
    return out


def save_products(products: list):
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=2)
    print(f"💾 Saved {len(products)} products.")


def load_products() -> list:
    try:
        with open(PRODUCTS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def discover_links(session_file: str = SESSION_FILE) -> list:
    print("=" * 55)
    print("🔎 POKÉMON CARD LINK + PRICE DISCOVERY")
    print("=" * 55)

    all_products = []
    storage = session_file if os.path.exists(session_file) else None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=storage,
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        print("\n🎯 Searching Target...")
        for term in SEARCH_TERMS:
            print(f"  → {term}")
            results = search_target(page, term)
            print(f"     {len(results)} results")
            all_products.extend(results)

        print("\n🛒 Searching Walmart...")
        for term in SEARCH_TERMS:
            print(f"  → {term}")
            results = search_walmart(page, term)
            print(f"     {len(results)} results")
            all_products.extend(results)

        browser.close()

    filtered = filter_products(all_products)
    print(f"\n📦 {len(filtered)} unique products with prices.")
    save_products(filtered)
    return filtered