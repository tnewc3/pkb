import threading
import queue
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Any
from playwright.sync_api import sync_playwright, Page, BrowserContext

SESSION_FILE = "sessions.json"
CDP_PORT     = 9222

# Edge passes PerimeterX where Chrome doesn't — use Edge's real profile.
_EDGE_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"

_EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_edge() -> str:
    """Return path to the Edge executable, or raise."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
            path = winreg.QueryValue(k, None)
            if path and Path(path).exists():
                return path
    except Exception:
        pass
    for p in _EDGE_CANDIDATES:
        if Path(p).exists():
            return str(p)
    raise FileNotFoundError(
        "Microsoft Edge not found. Edge is required to bypass bot detection."
    )


def _wait_for_cdp(port: int, timeout: float = 15.0):
    """Block until Chrome's CDP endpoint is accepting connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=1)
            return
        except Exception:
            time.sleep(0.4)
    raise TimeoutError(f"Chrome CDP did not become available on port {port}")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
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
        self._queue        = queue.Queue()
        self._page         = None
        self._context      = None
        self._browser      = None
        self._pw           = None
        self._thread       = None
        self._ready        = threading.Event()
        self._stopped      = False
        self._chrome_proc  = None

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
        # With a persistent profile the browser saves cookies/storage automatically.
        # This is kept as a no-op so existing callers don't break.
        pass

    def stop(self):
        self._stopped = True
        self._queue.put(None)

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    def _run(self):
        from config import HEADLESS, PROXY_URL

        try:
            edge_exe = _find_edge()
        except FileNotFoundError as e:
            print(f"[PlaywrightManager] ERROR: {e}")
            self._ready.set()
            return

        chrome_args = [
            edge_exe,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={_EDGE_USER_DATA}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-service-autorun",
            "--no-restore-last-session",
        ]
        if HEADLESS:
            chrome_args.append("--headless=new")
        if PROXY_URL:
            chrome_args.append(f"--proxy-server={PROXY_URL}")

        try:
            self._chrome_proc = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"[PlaywrightManager] ERROR launching Chrome: {e}")
            self._ready.set()
            return

        # Wait for CDP to be ready
        try:
            _wait_for_cdp(CDP_PORT)
        except TimeoutError as e:
            print(f"[PlaywrightManager] ERROR: {e}")
            self._chrome_proc.terminate()
            self._ready.set()
            return

        with sync_playwright() as pw:
            self._pw = pw

            try:
                self._browser = pw.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
            except Exception as e:
                print(f"[PlaywrightManager] ERROR connecting to Chrome: {e}")
                self._chrome_proc.terminate()
                self._ready.set()
                return

            contexts = self._browser.contexts
            self._context = contexts[0] if contexts else self._browser.new_context()

            self._apply_stealth(self._context)
            self._inject_saved_cookies(self._context)

            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
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
            except Exception:
                pass

        try:
            self._chrome_proc.terminate()
        except Exception:
            pass

    def _inject_saved_cookies(self, context: BrowserContext):
        """Load cookies from sessions.json into the browser context."""
        if not os.path.exists(SESSION_FILE):
            return
        try:
            with open(SESSION_FILE, "r") as f:
                session = json.load(f)
            cookies = session.get("cookies", [])
            if cookies:
                context.add_cookies(cookies)
                print(f"[PlaywrightManager] Injected {len(cookies)} saved cookies.")
        except Exception as e:
            print(f"[PlaywrightManager] Could not load sessions.json: {e}")

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