import threading
import time
from playwright.sync_api import Page
from playwright_manager import PlaywrightManager

SESSION_CHECK_INTERVAL = 300

LOGIN_CHECKS = {
    "target": {
        "url":            "https://www.target.com/account",
        "logged_in_sel":  "[data-test='accountNav-greeting']",
        "logged_out_sel": "[data-test='accountNav-signIn']",
    },
    "walmart": {
        "url":            "https://www.walmart.com/account",
        "logged_in_sel":  ".account-menu__user-info, [data-automation-id='user-name']",
        "logged_out_sel": "a[href*='/account/login']",
    },
}


def check_session(pw: PlaywrightManager, retailer: str) -> bool:
    """
    Probe the retailer's account page and decide if we're still logged in.

    Be conservative: only return False when we have *positive* evidence the
    user is logged out (e.g. redirected to a login URL). On network errors,
    timeouts, or ambiguous pages, assume still-logged-in to avoid spurious
    "session expired" warnings — a real ATC failure will catch true expiry.
    """
    cfg = LOGIN_CHECKS.get(retailer)
    if not cfg:
        return True

    def _check(page: Page) -> bool:
        try:
            page.goto(cfg["url"],
                      wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
        except Exception:
            # Network hiccup or bot-wall — don't punish the user, assume OK
            return True

        try:
            url_lower = (page.url or "").lower()
            # Positive logged-out signal: redirected to a login/signin URL
            if "/login" in url_lower or "/signin" in url_lower or \
               "account/login" in url_lower:
                return False
            # Positive logged-in signal: greeting / username element present
            if page.query_selector(cfg["logged_in_sel"]):
                return True
            # Logged-out selector AND no logged-in selector → expired
            if page.query_selector(cfg["logged_out_sel"]):
                return False
        except Exception:
            return True

        # Ambiguous: selectors changed or page renders client-side. Assume OK.
        return True

    try:
        return pw.submit(_check, f"session_check:{retailer}", timeout=25)
    except Exception:
        # Even the job itself crashed — don't flip to expired
        return True


class SessionGuard:
    def __init__(self, pw, on_session_lost, on_session_restored, on_log):
        self.pw                  = pw
        self.on_session_lost     = on_session_lost
        self.on_session_restored = on_session_restored
        self.on_log              = on_log
        self._stop               = threading.Event()
        self._status             = {"target": True, "walmart": True}

    def start(self):
        t = threading.Thread(target=self._run, daemon=True, name="SessionGuard")
        t.start()
        self.on_log("🛡️  Session guard started.")

    def stop(self):
        self._stop.set()

    def is_logged_in(self, retailer: str) -> bool:
        return self._status.get(retailer, False)

    def force_check(self):
        threading.Thread(target=self._check_all, daemon=True).start()

    def _run(self):
        self._stop.wait(10)
        self._check_all()
        while not self._stop.is_set():
            self._stop.wait(SESSION_CHECK_INTERVAL)
            if not self._stop.is_set():
                self._check_all()

    def _check_all(self):
        for retailer in ["target", "walmart"]:
            self._check_retailer(retailer)

    def _check_retailer(self, retailer: str):
        self.on_log(f"Checking {retailer.capitalize()} session...")
        valid = check_session(self.pw, retailer)

        if valid:
            if not self._status[retailer]:
                self._status[retailer] = True
                self.on_session_restored(retailer)
                self.on_log(f"{retailer.capitalize()} session restored.")
            else:
                self.on_log(f"{retailer.capitalize()} session valid.")
            return

        self.on_log(f"{retailer.capitalize()} session expired!")
        self._status[retailer] = False
        self.on_session_lost(retailer)

        # Notify and ask the user to sign in manually
        self.on_log(f"Manual sign-in required for {retailer.capitalize()} — use Re-Login.")
        from notifier import notify_session_expired
        from config   import DISCORD_WEBHOOK
        notify_session_expired(retailer, DISCORD_WEBHOOK)