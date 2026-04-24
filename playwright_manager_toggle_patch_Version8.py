# Update PlaywrightManager.__init__() signature:

class PlaywrightManager:
    def __init__(self, force_proxy: str = None):
        self._force_proxy = force_proxy   # ← None = use config, "" = no proxy
        # ... rest unchanged ...

# Update _launch() to respect force_proxy:

def _launch(self, pw, headless: bool):
    # force_proxy=None → use config
    # force_proxy=""   → no proxy (disabled)
    # force_proxy=url  → use that specific proxy
    if self._force_proxy is None:
        proxy = self._proxy_mgr.get() if self._proxy_mgr else None
    elif self._force_proxy == "":
        proxy = None
    else:
        proxy = self._force_proxy

    self._current_proxy = proxy

    args = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
    }
    if proxy:
        args["proxy"] = {"server": proxy}
        print(f"📡 Proxy: {proxy[:40]}")
    else:
        print("🌐 Direct connection")

    self._browser = pw.chromium.launch(**args)
    storage = SESSION_FILE if os.path.exists(SESSION_FILE) else None
    self._context = self._browser.new_context(
        storage_state=storage,
        user_agent=HEADERS["User-Agent"],
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
    )
    self._apply_stealth(self._context)
    self._page = self._context.new_page()
    self._page.set_extra_http_headers(HEADERS)