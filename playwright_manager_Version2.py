import threading
import queue
import json
import os
from typing import Callable, Any
from playwright.sync_api import sync_playwright, Page, BrowserContext

SESSION_FILE = "sessions.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )
}


class PlaywrightJob:
    def __init__(self, fn: Callable[[Page], Any], label: str = ""):
        self.fn      = fn
        self.label   = label
        self._event  = threading.Event()
        self._result = None
        self._error  = None

    def wait(self, timeout: float = 60.0) -> Any:
        if not self._event.wait(timeout=timeout):
            raise TimeoutError(f"Playwright job timed out: {self.label}")
        if self._error:
            raise self._error
        return self._result

    def _resolve(self, result):
        self._result = result
        self._event.set()

    def _reject(self, error):
        self._error = error
        self._event.set()


class PlaywrightManager:
    def __init__(self):
        self._queue   = queue.Queue()
        self._page    = None
        self._context = None
        self._browser = None
        self._pw      = None
        self._thread  = None
        self._ready   = threading.Event()
        self._stopped = False

    def start(self):
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="PlaywrightThread"
        )
        self._thread.start()
        self._ready.wait(timeout=30)

    def submit(self, fn: Callable[[Page], Any],
               label: str = "", timeout: float = 60.0) -> Any:
        job = PlaywrightJob(fn, label)
        self._queue.put(job)
        return job.wait(timeout=timeout)

    def submit_nowait(self, fn: Callable[[Page], Any], label: str = ""):
        job = PlaywrightJob(fn, label)
        self._queue.put(job)

    def save_session(self):
        def _save(page: Page):
            state = page.context.storage_state()
            with open(SESSION_FILE, "w") as f:
                json.dump(state, f)
            return True
        try:
            self.submit(_save, "save_session", timeout=15)
        except Exception as e:
            print(f"Save session error: {e}")

    def stop(self):
        self._stopped = True
        self._queue.put(None)

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    def _run(self):
        from config import HEADLESS, PROXY_URL
        with sync_playwright() as pw:
            self._pw = pw

            launch_args = {
                "headless": HEADLESS,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            }
            if PROXY_URL:
                launch_args["proxy"] = {"server": PROXY_URL}

            self._browser = pw.chromium.launch(**launch_args)

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
                    print(f"[PlaywrightThread] Error: {e}")

            try:
                self._browser.close()
            except:
                pass

    def _process(self, job: PlaywrightJob):
        try:
            result = job.fn(self._page)
            job._resolve(result)
        except Exception as e:
            print(f"[PlaywrightThread] Job '{job.label}' failed: {e}")
            job._reject(e)

    def _apply_stealth(self, context: BrowserContext):
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [
                { name: 'Chrome PDF Plugin' },
                { name: 'Chrome PDF Viewer' },
                { name: 'Native Client' }
            ]});
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            const origGetParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {
                if (p === 37445) return 'Intel Inc.';
                if (p === 37446) return 'Intel Iris OpenGL Engine';
                return origGetParam.call(this, p);
            };
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : origQuery(params)
            );
        """)