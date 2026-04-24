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

            try:
                self._browser = pw.chromium.launch(channel="chrome", **launch_args)
            except Exception as e:
                print(f"[PlaywrightManager] Real Chrome unavailable ({e}), falling back to bundled Chromium.")
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
            // --- navigator.webdriver ---
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // --- navigator.plugins (realistic with MimeType objects) ---
            const makeMime = (type, desc, suffixes) => {
                const m = Object.create(MimeType.prototype);
                Object.defineProperties(m, {
                    type:        { get: () => type },
                    description: { get: () => desc },
                    suffixes:    { get: () => suffixes },
                });
                return m;
            };
            const makePlugin = (name, desc, filename, mimes) => {
                const p = Object.create(Plugin.prototype);
                Object.defineProperties(p, {
                    name:        { get: () => name },
                    description: { get: () => desc },
                    filename:    { get: () => filename },
                    length:      { get: () => mimes.length },
                });
                mimes.forEach((m, i) => { p[i] = m; });
                return p;
            };
            const pdfMime1 = makeMime('application/x-google-chrome-pdf', 'Portable Document Format', 'pdf');
            const pdfMime2 = makeMime('application/pdf', 'Portable Document Format', 'pdf');
            const ncMime   = makeMime('application/x-nacl', 'Native Client Executable', 'nexe');
            const plugins  = [
                makePlugin('Chrome PDF Plugin',  'Portable Document Format', 'internal-pdf-viewer', [pdfMime1]),
                makePlugin('Chrome PDF Viewer',  '', 'mhjfbmdgcfjbbpaeojofohoefgiehjai', [pdfMime2]),
                makePlugin('Native Client',       '', 'internal-nacl-plugin',             [ncMime]),
            ];
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const arr = [...plugins];
                    arr.__proto__ = PluginArray.prototype;
                    return arr;
                }
            });

            // --- navigator.languages / platform / hardwareConcurrency / deviceMemory ---
            Object.defineProperty(navigator, 'languages',           { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'platform',            { get: () => 'Win32' });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            try { Object.defineProperty(navigator, 'deviceMemory',  { get: () => 8 }); } catch(e) {}

            // --- window.chrome runtime object ---
            if (!window.chrome) {
                Object.defineProperty(window, 'chrome', {
                    writable: true, enumerable: true, configurable: false,
                    value: { runtime: {} }
                });
            }

            // --- Remove CDP leak (cdc_ prefixed properties) ---
            for (const key of Object.keys(window)) {
                if (key.startsWith('cdc_')) {
                    try { delete window[key]; } catch(e) {}
                }
            }
            for (const key of Object.keys(document)) {
                if (key.startsWith('cdc_')) {
                    try { delete document[key]; } catch(e) {}
                }
            }

            // --- WebGL vendor / renderer ---
            const origGetParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {
                if (p === 37445) return 'Intel Inc.';
                if (p === 37446) return 'Intel Iris OpenGL Engine';
                return origGetParam.call(this, p);
            };

            // --- Notification / permissions query ---
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : origQuery(params)
            );

            // --- Canvas fingerprint noise (shared helper) ---
            const _addCanvasNoise = (imageData) => {
                const d = imageData.data;
                for (let i = 0; i < d.length; i += 4) {
                    d[i]   = Math.max(0, Math.min(255, d[i]   + (Math.random() * 2 - 1)));
                    d[i+1] = Math.max(0, Math.min(255, d[i+1] + (Math.random() * 2 - 1)));
                    d[i+2] = Math.max(0, Math.min(255, d[i+2] + (Math.random() * 2 - 1)));
                }
            };
            const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
                const ctx = this.getContext('2d');
                if (ctx && this.width > 0 && this.height > 0) {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    _addCanvasNoise(imageData);
                    ctx.putImageData(imageData, 0, 0);
                }
                return _toDataURL.call(this, type, quality);
            };
            const _toBlob = HTMLCanvasElement.prototype.toBlob;
            HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
                const ctx = this.getContext('2d');
                if (ctx && this.width > 0 && this.height > 0) {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    _addCanvasNoise(imageData);
                    ctx.putImageData(imageData, 0, 0);
                }
                return _toBlob.call(this, callback, type, quality);
            };
            const _getImageData = CanvasRenderingContext2D.prototype.getImageData;
            CanvasRenderingContext2D.prototype.getImageData = function(sx, sy, sw, sh) {
                const imageData = _getImageData.call(this, sx, sy, sw, sh);
                _addCanvasNoise(imageData);
                return imageData;
            };

            // --- Audio fingerprint noise ---
            const _getChannelData = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function(channel) {
                const data = _getChannelData.call(this, channel);
                for (let i = 0; i < data.length; i++) {
                    data[i] += (Math.random() * 0.0002 - 0.0001);
                }
                return data;
            };

            // --- navigator.connection realistic values (slightly randomized) ---
            try {
                if (navigator.connection) {
                    const _rtt      = [25, 50, 75][Math.floor(Math.random() * 3)];
                    const _downlink = +(7 + Math.random() * 6).toFixed(1);
                    Object.defineProperties(navigator.connection, {
                        rtt:           { get: () => _rtt,      configurable: true },
                        downlink:      { get: () => _downlink, configurable: true },
                        effectiveType: { get: () => '4g',      configurable: true },
                        saveData:      { get: () => false,     configurable: true },
                    });
                }
            } catch(e) {}
        """)