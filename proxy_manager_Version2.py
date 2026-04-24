import threading
import itertools
import requests
from typing import Optional


class ProxyManager:
    """
    Dual-mode proxy manager:
    - FREE mode: uses swiftshadow to auto-fetch + rotate public proxies
    - FILE mode: rotates through your own proxies.txt
    - NONE mode: direct connection (no proxy)

    Includes:
    - Health checking
    - Dead proxy removal
    - Auto-refresh when pool runs low
    - Per-domain ban detection
    """

    def __init__(self,
                 proxy_file:  str  = "proxies.txt",
                 use_free:    bool = True,
                 test_url:    str  = "https://httpbin.org/ip"):
        self._proxies      = []
        self._dead         = set()
        self._lock         = threading.Lock()
        self._cycle        = None
        self._test_url     = test_url
        self._proxy_file   = proxy_file
        self._use_free     = use_free
        self._swift        = None

        self._load()

    # ── LOAD ─────────────────────────────────

    def _load(self):
        """Load proxies from file first, fall back to swiftshadow."""
        loaded = False

        # Try proxies.txt first
        try:
            with open(self._proxy_file) as f:
                lines = [
                    l.strip() for l in f
                    if l.strip() and not l.startswith("#")
                ]
            self._proxies = [
                p if p.startswith("http") else f"http://{p}"
                for p in lines
            ]
            if self._proxies:
                print(f"📡 Loaded {len(self._proxies)} proxies from "
                      f"{self._proxy_file}")
                loaded = True
        except FileNotFoundError:
            pass

        # Fall back to swiftshadow free proxies
        if not loaded and self._use_free:
            self._load_swiftshadow()

        self._build_cycle()

    def _load_swiftshadow(self):
        """Fetch free proxies via swiftshadow."""
        try:
            from swiftshadow.classes import ProxyInterface
            print("🌐 Fetching free proxies via swiftshadow...")
            self._swift = ProxyInterface(
                countries=["US"],
                protocol="http",
                autoRotate=True,
            )
            # Pull up to 20 proxies from the pool
            proxies = []
            for _ in range(20):
                try:
                    p = self._swift.get()
                    url = p.as_string()
                    if url and url not in proxies:
                        proxies.append(url)
                except:
                    break
            self._proxies = proxies
            print(f"📡 Loaded {len(self._proxies)} free proxies.")
        except ImportError:
            print("⚠️  swiftshadow not installed — run: pip install swiftshadow")
        except Exception as e:
            print(f"⚠️  swiftshadow failed: {e}")

    def _build_cycle(self):
        alive = [p for p in self._proxies if p not in self._dead]
        self._cycle = itertools.cycle(alive) if alive else None

    def reload(self):
        """Refresh the proxy pool."""
        with self._lock:
            self._dead.clear()
            self._proxies = []
            self._load()

    # ── GET ──────────────────────────────────

    def get(self) -> Optional[str]:
        """
        Get next proxy in rotation.
        Returns None if no proxies → direct connection.
        """
        if not self._proxies:
            return None

        with self._lock:
            alive = [p for p in self._proxies if p not in self._dead]
            if not alive:
                print("⚠️  All proxies dead — reloading pool...")
                self._dead.clear()
                if self._use_free:
                    self._load_swiftshadow()
                    self._build_cycle()
                alive = self._proxies

            if not alive:
                print("⚠️  No proxies available — using direct connection.")
                return None

            self._build_cycle()
            return next(self._cycle)

    def mark_dead(self, proxy: str):
        with self._lock:
            self._dead.add(proxy)
            print(f"💀 Proxy dead: {proxy[:40]}")
            # If pool is nearly exhausted, auto-reload
            alive = len(self._proxies) - len(self._dead)
            if alive <= 2 and self._use_free:
                print("🔄 Pool low — reloading free proxies...")
                threading.Thread(
                    target=self._reload_background,
                    daemon=True
                ).start()

    def _reload_background(self):
        self._load_swiftshadow()
        self._build_cycle()

    def count(self) -> dict:
        alive = len(self._proxies) - len(self._dead)
        return {
            "total": len(self._proxies),
            "alive": alive,
            "dead":  len(self._dead),
        }

    # ── HEALTH CHECK ─────────────────────────

    def health_check_all(self, on_log=None) -> dict:
        """Test all proxies. Returns alive/dead counts."""
        results = {"alive": 0, "dead": 0}
        for proxy in list(self._proxies):
            ok = self._test_proxy(proxy)
            if ok:
                results["alive"] += 1
                self._dead.discard(proxy)
            else:
                results["dead"] += 1
                self.mark_dead(proxy)
                msg = f"💀 Dead: {proxy[:40]}"
                on_log(msg) if on_log else print(msg)
        return results

    def _test_proxy(self, proxy: str, timeout: int = 6) -> bool:
        try:
            r = requests.get(
                self._test_url,
                proxies={"http": proxy, "https": proxy},
                timeout=timeout
            )
            return r.status_code == 200
        except:
            return False

    # ── BAN DETECTION ────────────────────────

    def check_if_banned(self, proxy: str, retailer: str) -> bool:
        """
        Check if a proxy is specifically banned by Target/Walmart
        by looking for block page indicators.
        """
        test_urls = {
            "target":  "https://www.target.com",
            "walmart": "https://www.walmart.com",
        }
        url = test_urls.get(retailer)
        if not url:
            return False

        try:
            r = requests.get(
                url,
                proxies={"http": proxy, "https": proxy},
                timeout=8,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                    )
                }
            )
            blocked = any(word in r.text.lower() for word in [
                "access denied", "blocked", "captcha",
                "403", "unusual traffic"
            ])
            return blocked
        except:
            return True  # Assume banned if can't connect