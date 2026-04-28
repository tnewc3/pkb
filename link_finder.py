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
    # Reseller / marketplace markers
    "case of", "pack of", "bundle of", "x pack",
    "japanese import", "import lot", "factory sealed lot",
    "wholesale", "vintage", "graded", "psa ", "cgc ", "bgs ",
    "proxy", "fake", "replica", "counterfeit",
]

# MSRP ceilings for each Pokémon TCG product type (in USD).
# Anything priced above (MSRP * MSRP_BUFFER) is filtered out as a reseller markup.
# Order matters: most-specific keywords first.
MSRP_RULES = [
    # (keywords that must all appear in lowercased name, MSRP USD)
    (("ascended heroes", "premium poster"),         49.99),
    (("premium poster collection",),                49.99),
    (("poster collection",),                        24.99),
    (("deluxe pin collection",),                    29.99),
    (("pin collection",),                           24.99),
    (("elite trainer box",),                        59.99),
    (("etb",),                                      59.99),
    (("booster bundle",),                           26.99),
    (("three booster blister",),                    14.99),
    (("3-pack blister",),                           14.99),
    (("blister",),                                  14.99),
    (("mini tin",),                                 13.99),
    (("tin",),                                      24.99),
    (("booster box",),                             161.99),
    (("premium collection",),                       49.99),
    (("zacian ex box",),                            34.99),
    (("ex box",),                                   29.99),
    (("collection box",),                           29.99),
    (("booster pack",),                              5.49),
]

# Allow up to this multiplier over MSRP (covers tax, sale price variance, etc.)
MSRP_BUFFER = 1.15


def _classify_msrp(name_lower: str) -> float:
    """Return the MSRP ceiling for a product name, or 0.0 if unknown."""
    for keywords, msrp in MSRP_RULES:
        if all(kw in name_lower for kw in keywords):
            return msrp
    return 0.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )
}


def _wait_for_any(page: Page, selectors: list, timeout: int = 12000) -> str:
    """Wait until any of the given selectors appears. Returns the matching one or ''."""
    deadline = time.monotonic() + (timeout / 1000.0)
    while time.monotonic() < deadline:
        for sel in selectors:
            try:
                if page.query_selector(sel):
                    return sel
            except Exception:
                pass
        page.wait_for_timeout(250)
    return ""


def search_target(page: Page, term: str) -> list:
    products = []
    # Target's search results have shifted across multiple data-test ids.
    card_selectors = [
        "[data-test='product-details']",
        "[data-test='@web/site-top-of-funnel/ProductCardWrapper']",
        "[data-test='productCard']",
        "div[data-test*='product']",
    ]
    title_selectors = [
        "[data-test='product-title']",
        "a[data-test='product-title']",
        "[data-test='@web/site-top-of-funnel/ProductCardWrapper'] a[href*='/p/']",
    ]
    price_selectors = [
        "[data-test='current-price']",
        "[data-test='product-price']",
        ".styles__CurrentPriceFontSize",
        "[aria-label*='current price']",
        "span[data-test*='price']",
    ]
    try:
        page.goto(
            f"https://www.target.com/s?searchTerm={quote_plus(term)}",
            wait_until="domcontentloaded", timeout=20000
        )
        matched = _wait_for_any(page, card_selectors, timeout=12000)
        if not matched:
            # Fallback: any anchor that looks like a product page
            if not page.query_selector("a[href*='/p/']"):
                print(f"  ⚠ Target '{term}': no product cards found "
                      f"(layout may have changed). URL={page.url}")
                return products
        time.sleep(2)

        cards = []
        for sel in card_selectors:
            cards = page.query_selector_all(sel)
            if cards:
                break
        if not cards:
            # Last-resort: treat each /p/ anchor as a card
            cards = page.query_selector_all("a[href*='/p/']")

        for card in cards:
            try:
                name = ""
                for tsel in title_selectors:
                    el = card.query_selector(tsel)
                    if el:
                        name = el.inner_text().strip()
                        if name:
                            break
                if not name:
                    # fall back to the card's own text if it's the anchor
                    try:
                        name = card.inner_text().strip().splitlines()[0]
                    except Exception:
                        name = ""
                if not name:
                    continue

                link_el = card if (card.evaluate("e => e.tagName") == "A") \
                          else card.query_selector("a[href*='/p/']") or card.query_selector("a")
                if not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = f"https://www.target.com{href}"

                price = 0.0
                for sel in price_selectors:
                    price_el = card.query_selector(sel)
                    if price_el:
                        try:
                            raw = price_el.inner_text().strip()\
                                .replace("$","").replace(",","").split()[0]
                            price = float(raw)
                            break
                        except Exception:
                            continue

                products.append({
                    "name": name, "retailer": "target",
                    "url": href, "price": price,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"  ❌ Target '{term}': {e}")
    return products


def search_walmart(page: Page, term: str) -> list:
    products = []
    card_selectors = [
        "div[data-item-id]",
        "div[data-testid='item-stack']",
        "div[data-testid='list-view']",
        "[data-testid='product-tile']",
    ]
    title_selectors = [
        "[data-automation-id='product-title']",
        "span[data-automation-id='product-title']",
        "a[link-identifier]",
        "a[href*='/ip/']",
    ]
    try:
        page.goto(
            f"https://www.walmart.com/search?q={quote_plus(term)}",
            wait_until="domcontentloaded", timeout=20000
        )
        matched = _wait_for_any(page, card_selectors + title_selectors, timeout=12000)
        if not matched:
            if not page.query_selector("a[href*='/ip/']"):
                print(f"  ⚠ Walmart '{term}': no product cards found. URL={page.url}")
                return products
        time.sleep(2)

        cards = []
        for sel in card_selectors:
            cards = page.query_selector_all(sel)
            if cards:
                break
        if not cards:
            cards = page.query_selector_all("a[href*='/ip/']")

        for card in cards:
            try:
                name = ""
                for tsel in title_selectors:
                    el = card.query_selector(tsel)
                    if el:
                        name = (el.inner_text() or el.get_attribute("aria-label") or "").strip()
                        if name:
                            break
                if not name:
                    try:
                        name = card.inner_text().strip().splitlines()[0]
                    except Exception:
                        name = ""
                if not name:
                    continue

                if card.evaluate("e => e.tagName") == "A":
                    link_el = card
                else:
                    link_el = (card.query_selector("a[href*='/ip/']")
                               or card.query_selector("a"))
                if not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = f"https://www.walmart.com{href}"

                price = 0.0
                for sel in [
                    "[itemprop='price']",
                    "[data-automation-id='product-price'] span",
                    "div[data-automation-id='product-price']",
                    ".price-characteristic",
                    "span.f2",
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
                        except Exception:
                            continue

                products.append({
                    "name": name, "retailer": "walmart",
                    "url": href, "price": price,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"  ❌ Walmart '{term}': {e}")
    return products


def filter_products(products: list) -> list:
    """
    Keep only sealed first-party Pokémon TCG product priced at or near MSRP.
    Rejects:
      - Non-Pokémon items
      - Accessories (sleeves, binders, etc.)
      - Reseller / marketplace listings priced > MSRP * MSRP_BUFFER
      - Items whose product type can't be identified (defensive)
      - Duplicates by URL
      - $0 / unknown price
    """
    seen, out = set(), []
    rejected_above_msrp = 0
    rejected_unknown_type = 0
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

        msrp = _classify_msrp(nl)
        if msrp == 0.0:
            rejected_unknown_type += 1
            continue
        ceiling = msrp * MSRP_BUFFER
        if p["price"] > ceiling:
            rejected_above_msrp += 1
            continue

        p["msrp"] = msrp  # annotate for downstream use
        seen.add(p["url"])
        out.append(p)

    if rejected_above_msrp or rejected_unknown_type:
        print(f"  Filtered out {rejected_above_msrp} above-MSRP, "
              f"{rejected_unknown_type} unknown-type listings.")
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