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
    cfg = LOGIN_CHECKS.get(retailer)
    if not cfg:
        return True

    def _check(page: Page) -> bool:
        try:
            page.goto(cfg["url"],
                      wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            if page.query_selector(cfg["logged_in_sel"]):
                return True
            if page.query_selector(cfg["logged_out_sel"]):
                return False
            if "login" in page.url.lower() or "signin" in page.url.lower():
                return False
            return True
        except:
            return False

    try:
        return pw.submit(_check, f"session_check:{retailer}", timeout=25)
    except:
        return False


def relogin(pw: PlaywrightManager, retailer: str,
            email: str, password: str, on_log) -> bool:
    def _login(page: Page) -> bool:
        try:
            if retailer == "target":
                page.goto("https://www.target.com/account",
                          wait_until="domcontentloaded", timeout=15000)
                try:
                    page.click("button[data-test='accountNav-signIn']",
                               timeout=5000)
                except:
                    pass
                page.wait_for_selector("#username", timeout=10000)
                page.fill("#username", email)
                page.fill("#password", password)
                page.click("button[type='submit']")
                page.wait_for_selector(
                    "[data-test='accountNav-greeting']", timeout=15000)
                return True
            elif retailer == "walmart":
                page.goto("https://www.walmart.com/account/login",
                          wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector("#email", timeout=10000)
                page.fill("#email", email)
                page.fill("#password", password)
                page.click("button[type='submit']")
                page.wait_for_selector(
                    ".account-menu__user-info,"
                    "[data-automation-id='user-name']",
                    timeout=15000)
                return True
        except Exception as e:
            print(f"  ❌ Auto re-login ({retailer}): {e}")
            return False

    try:
        ok = pw.submit(_login, f"relogin:{retailer}", timeout=45)
        if ok:
            pw.save_session()
            on_log(f"✅ Auto re-login: {retailer.capitalize()}")
        return ok
    except:
        return False


class SessionGuard:
    def __init__(self, pw, get_credentials,
                 on_session_lost, on_session_restored, on_log):
        self.pw                  = pw
        self.get_credentials     = get_credentials
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
        self.on_log(f"🔍 Checking {retailer.capitalize()} session...")
        valid = check_session(self.pw, retailer)

        if valid:
            if not self._status[retailer]:
                self._status[retailer] = True
                self.on_session_restored(retailer)
                self.on_log(f"✅ {retailer.capitalize()} session restored.")
            else:
                self.on_log(f"✅ {retailer.capitalize()} session valid.")
            return

        self.on_log(f"⚠️  {retailer.capitalize()} session expired!")
        self._status[retailer] = False
        self.on_session_lost(retailer)

        creds       = self.get_credentials()
        email, pwd  = creds.get(retailer, (None, None))

        if email and pwd:
            self.on_log(f"🔄 Auto re-login: {retailer.capitalize()}...")
            ok = relogin(self.pw, retailer, email, pwd, self.on_log)
            if ok:
                self._status[retailer] = True
                self.on_session_restored(retailer)
                return

        self.on_log(f"❌ Manual re-login required: {retailer.capitalize()}")
        from notifier import notify_session_expired
        from config   import DISCORD_WEBHOOK
        notify_session_expired(retailer, DISCORD_WEBHOOK)