# In PlaywrightManager.__init__() add:
self._proxy_mgr     = None
self._current_proxy = None

# Replace _run() with:

def _run(self):
    from config  import HEADLESS, PROXY_URL, PROXY_FILE, USE_FREE_PROXIES
    from proxy_manager import ProxyManager

    # Build proxy manager
    if os.path.exists(PROXY_FILE):
        self._proxy_mgr = ProxyManager(
            proxy_file=PROXY_FILE,
            use_free=USE_FREE_PROXIES
        )
    elif PROXY_URL:
        self._proxy_mgr = ProxyManager(
            proxies=[PROXY_URL],
            use_free=False
        )
    elif USE_FREE_PROXIES:
        self._proxy_mgr = ProxyManager(
            proxy_file="proxies.txt",
            use_free=True
        )
    else:
        self._proxy_mgr = None

    with sync_playwright() as pw:
        self._pw = pw
        self._launch(pw, HEADLESS)
        self._ready.set()

        while not self._stopped:
            try:
                job = self._queue.get(timeout=1)
                if job is None:
                    break
                self._process(job)
            except queue.Empty:
                continue
            except Exception as e:
                err = str(e)
                print(f"[PlaywrightThread] Error: {err}")
                if any(w in err for w in
                       ["ERR_TUNNEL", "ERR_PROXY", "ERR_CONNECTION",
                        "net::ERR"]):
                    self._rotate_proxy(pw, HEADLESS)

        try:
            self._browser.close()
        except:
            pass


def _launch(self, pw, headless: bool):
    proxy = self._proxy_mgr.get() if self._proxy_mgr else None
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
        print("🌐 Direct connection (no proxy)")

    self._browser  = pw.chromium.launch(**args)
    storage        = SESSION_FILE if os.path.exists(SESSION_FILE) else None
    self._context  = self._browser.new_context(
        storage_state=storage,
        user_agent=HEADERS["User-Agent"],
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
    )
    self._apply_stealth(self._context)
    self._page = self._context.new_page()
    self._page.set_extra_http_headers(HEADERS)


def _rotate_proxy(self, pw, headless: bool):
    if self._proxy_mgr and self._current_proxy:
        self._proxy_mgr.mark_dead(self._current_proxy)
    print("🔄 Rotating proxy...")
    try:
        self._browser.close()
    except:
        pass
    self._launch(pw, headless)