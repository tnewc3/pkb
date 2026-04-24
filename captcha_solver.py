import time
import requests
from playwright.sync_api import Page
from config import TWOCAPTCHA_API_KEY

BASE_URL   = "https://api.2captcha.com"
POLL_DELAY = 5
MAX_POLLS  = 24


# ── API v2 CORE ──────────────────────────────

def _create_task(task: dict) -> str | None:
    try:
        r    = requests.post(f"{BASE_URL}/createTask", json={
            "clientKey": TWOCAPTCHA_API_KEY,
            "task":      task,
        }, timeout=15)
        data = r.json()
        if data.get("errorId") == 0:
            return str(data["taskId"])
        print(f"  ❌ 2Captcha createTask: {data.get('errorDescription')}")
        return None
    except Exception as e:
        print(f"  ❌ 2Captcha createTask exception: {e}")
        return None


def _get_result(task_id: str) -> str | None:
    payload = {"clientKey": TWOCAPTCHA_API_KEY, "taskId": task_id}
    for attempt in range(MAX_POLLS):
        time.sleep(POLL_DELAY)
        try:
            r    = requests.post(f"{BASE_URL}/getTaskResult",
                                 json=payload, timeout=15)
            data = r.json()
            if data.get("errorId") != 0:
                print(f"  ❌ 2Captcha: {data.get('errorDescription')}")
                return None
            if data.get("status") == "ready":
                sol = data.get("solution", {})
                return sol.get("token") or sol.get("gRecaptchaResponse")
            print(f"  ⏳ 2Captcha solving... ({attempt+1}/{MAX_POLLS})")
        except Exception as e:
            print(f"  ❌ 2Captcha poll exception: {e}")
            return None
    print("  ⏰ 2Captcha timed out.")
    return None


# ── SOLVERS ──────────────────────────────────

def solve_recaptcha_v2(site_key: str, page_url: str) -> str | None:
    print("  🔄 Solving reCAPTCHA V2...")
    tid = _create_task({
        "type":       "RecaptchaV2TaskProxyless",
        "websiteURL": page_url,
        "websiteKey": site_key,
    })
    return _get_result(tid) if tid else None


def solve_recaptcha_v3(site_key: str, page_url: str,
                       action: str = "login") -> str | None:
    print("  🔄 Solving reCAPTCHA V3...")
    tid = _create_task({
        "type":       "RecaptchaV3TaskProxyless",
        "websiteURL": page_url,
        "websiteKey": site_key,
        "pageAction": action,
        "minScore":   0.7,
    })
    return _get_result(tid) if tid else None


def solve_arkose(site_key: str, page_url: str) -> str | None:
    print("  🔄 Solving Arkose Labs CAPTCHA...")
    tid = _create_task({
        "type":                     "FuncaptchaTaskProxyless",
        "websiteURL":               page_url,
        "websitePublicKey":         site_key,
        "funcaptchaApiJSSubdomain": "client-api.arkoselabs.com",
    })
    return _get_result(tid) if tid else None


def solve_turnstile(site_key: str, page_url: str) -> str | None:
    print("  🔄 Solving Cloudflare Turnstile...")
    tid = _create_task({
        "type":       "TurnstileTaskProxyless",
        "websiteURL": page_url,
        "websiteKey": site_key,
    })
    return _get_result(tid) if tid else None


# ── DETECTION ────────────────────────────────

def detect_captcha_type(page: Page) -> tuple:
    # reCAPTCHA v2/v3
    el = page.query_selector("[data-sitekey]")
    if el:
        site_key = el.get_attribute("data-sitekey") or ""
        is_v3 = page.evaluate("""
            () => typeof grecaptcha !== 'undefined'
               && typeof grecaptcha.execute === 'function'
               && document.querySelector('.g-recaptcha') === null
        """)
        return ("recaptcha_v3" if is_v3 else "recaptcha_v2"), site_key

    # Arkose Labs
    arkose = (
        page.query_selector("iframe[src*='arkoselabs']") or
        page.query_selector("iframe[src*='funcaptcha']")  or
        page.query_selector("[data-pkey]")
    )
    if arkose:
        site_key = (
            arkose.get_attribute("data-pkey") or
            _extract_arkose_key(page) or ""
        )
        return "arkose", site_key

    # Cloudflare Turnstile
    ts = page.query_selector(".cf-turnstile, [data-cf-turnstile]")
    if ts:
        return "turnstile", (ts.get_attribute("data-sitekey") or "")

    return None, None


def _extract_arkose_key(page: Page) -> str | None:
    try:
        return page.evaluate("""
            () => {
                const iframe = document.querySelector(
                    'iframe[src*="arkoselabs"], iframe[src*="funcaptcha"]'
                );
                if (iframe) {
                    const m = iframe.src.match(/public_key=([^&]+)/);
                    if (m) return m[1];
                }
                for (const s of document.querySelectorAll('script')) {
                    const m = s.innerText.match(/["']([A-Z0-9-]{36})["'].*arkoselabs/i);
                    if (m) return m[1];
                }
                return null;
            }
        """)
    except:
        return None


# ── INJECTION ────────────────────────────────

def _inject_recaptcha(page: Page, token: str, on_log) -> bool:
    try:
        page.evaluate(f"""
            (() => {{
                const ta = document.getElementById('g-recaptcha-response');
                if (ta) ta.innerHTML = '{token}';
                if (window.___grecaptcha_cfg) {{
                    Object.values(window.___grecaptcha_cfg.clients || {{}})
                        .forEach(c => {{ if (c.callback) c.callback('{token}'); }});
                }}
            }})();
        """)
        on_log("✅ reCAPTCHA token injected.")
        return True
    except Exception as e:
        on_log(f"❌ reCAPTCHA inject failed: {e}")
        return False


def _inject_arkose(page: Page, token: str, on_log) -> bool:
    try:
        page.evaluate(f"""
            (() => {{
                const input = document.querySelector(
                    'input[name="fc-token"], input[name="arkose_token"]'
                );
                if (input) {{
                    input.value = '{token}';
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }})();
        """)
        on_log("✅ Arkose token injected.")
        return True
    except Exception as e:
        on_log(f"❌ Arkose inject failed: {e}")
        return False


def _inject_turnstile(page: Page, token: str, on_log) -> bool:
    try:
        page.evaluate(f"""
            (() => {{
                const input = document.querySelector(
                    '[name="cf-turnstile-response"]'
                );
                if (input) {{
                    input.value = '{token}';
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }})();
        """)
        on_log("✅ Turnstile token injected.")
        return True
    except Exception as e:
        on_log(f"❌ Turnstile inject failed: {e}")
        return False


# ── MAIN ENTRY POINT ─────────────────────────

def solve_with_fallback(page: Page, product: dict, on_log) -> bool:
    from captcha_handler import wait_for_captcha_resolution
    from notifier import notify_captcha

    url = page.url

    if not TWOCAPTCHA_API_KEY:
        on_log("⚠️  No 2Captcha key — manual solve required.")
        notify_captcha(product)
        page.bring_to_front()
        return wait_for_captcha_resolution(
            page, product.get("retailer", ""), on_log)

    on_log("🔒 CAPTCHA detected — sending to 2Captcha...")
    captcha_type, site_key = detect_captcha_type(page)

    if not captcha_type or not site_key:
        on_log("⚠️  Could not identify CAPTCHA type — manual fallback.")
        notify_captcha(product)
        page.bring_to_front()
        return wait_for_captcha_resolution(
            page, product.get("retailer", ""), on_log)

    on_log(f"🔍 Type: {captcha_type.upper()} | Key: {site_key[:20]}...")

    token = None
    if captcha_type == "recaptcha_v2":
        token = solve_recaptcha_v2(site_key, url)
    elif captcha_type == "recaptcha_v3":
        token = solve_recaptcha_v3(site_key, url)
    elif captcha_type == "arkose":
        token = solve_arkose(site_key, url)
    elif captcha_type == "turnstile":
        token = solve_turnstile(site_key, url)

    if not token:
        on_log("⚠️  2Captcha solve failed — manual fallback.")
        notify_captcha(product)
        page.bring_to_front()
        return wait_for_captcha_resolution(
            page, product.get("retailer", ""), on_log)

    injected = False
    if captcha_type in ("recaptcha_v2", "recaptcha_v3"):
        injected = _inject_recaptcha(page, token, on_log)
    elif captcha_type == "arkose":
        injected = _inject_arkose(page, token, on_log)
    elif captcha_type == "turnstile":
        injected = _inject_turnstile(page, token, on_log)

    if injected:
        on_log("✅ CAPTCHA solved automatically!")
        return True

    on_log("⚠️  Token injection failed — manual fallback.")
    notify_captcha(product)
    page.bring_to_front()
    return wait_for_captcha_resolution(
        page, product.get("retailer", ""), on_log)