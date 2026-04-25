import tkinter as tk
from tkinter import messagebox
import threading
import json
import os
import re
import random
import time
from playwright.sync_api import Page
from playwright_manager import PlaywrightManager
from stealth_setup import human_type, human_click, human_delay

SESSION_FILE = "sessions.json"


class LoginWizard(tk.Toplevel):
    STEPS = ["welcome", "target", "walmart", "done"]

    def __init__(self, parent, pw: PlaywrightManager, on_complete):
        super().__init__(parent)
        self.pw              = pw
        self.on_complete     = on_complete
        self.title("Pokemon Bot - Setup")
        self.geometry("620x520")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e")
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._step           = 0
        self._target_ok      = False
        self._walmart_ok     = False
        self._captcha_event  = threading.Event()
        self._captcha_btn    = None
        self._container      = tk.Frame(self, bg="#1a1a2e")
        self._container.pack(fill="both", expand=True, padx=30, pady=20)
        self._show_step()

    def _show_step(self):
        for w in self._container.winfo_children():
            w.destroy()
        step = self.STEPS[self._step]
        if step == "welcome":  self._build_welcome()
        elif step == "target":   self._build_login("target")
        elif step == "walmart":  self._build_login("walmart")
        elif step == "done":     self._build_done()

    def _next(self):
        self._step += 1
        self._show_step()

    def _jump_done(self):
        self._step = self.STEPS.index("done")
        self._show_step()

    def _build_welcome(self):
        self._title("Welcome to Pokemon Card Bot")
        self._spacer(10)
        self._label(
            "This wizard logs you into Target and Walmart so the bot\n"
            "can monitor stock and add items to your cart automatically.\n\n"
            "Your session is saved locally in  sessions.json  and is\n"
            "never uploaded anywhere.\n\n"
            "You only need to do this once -- sessions are reused on\n"
            "every future launch until they expire."
        )
        self._spacer(20)
        self._progress(0)
        self._spacer(20)
        self._btn("Begin Setup", self._next, "#4ade80")
        if os.path.exists(SESSION_FILE):
            self._spacer(6)
            tk.Label(self._container,
                     text="Saved session found -- you can skip setup.",
                     font=("Helvetica", 9), fg="#4ade80", bg="#1a1a2e"
                     ).pack()
            self._btn("Skip (use saved session)", self._jump_done, "#0f3460")

    def _build_login(self, retailer: str):
        is_target = retailer == "target"
        color     = "#e94560" if is_target else "#0071ce"
        logo      = "Target" if is_target else "Walmart"
        pct       = 33 if is_target else 66

        self._title(f"Sign in to {logo}")
        self._spacer(8)
        self._label(f"Enter your {logo} credentials below.")
        self._spacer(12)
        self._progress(pct)
        self._spacer(16)

        tk.Label(self._container, text="Email",
                 font=("Helvetica", 10), fg="#a8dadc",
                 bg="#1a1a2e", anchor="w").pack(fill="x")
        email_var = tk.StringVar()
        email_ent = tk.Entry(self._container, textvariable=email_var,
                             font=("Helvetica", 11),
                             bg="#16213e", fg="white",
                             insertbackground="white", relief="flat",
                             highlightthickness=1, highlightcolor=color)
        email_ent.pack(fill="x", ipady=6, pady=(2, 10))
        email_ent.focus_set()

        tk.Label(self._container, text="Password",
                 font=("Helvetica", 10), fg="#a8dadc",
                 bg="#1a1a2e", anchor="w").pack(fill="x")
        pass_var = tk.StringVar()
        pass_ent = tk.Entry(self._container, textvariable=pass_var,
                            show="*", font=("Helvetica", 11),
                            bg="#16213e", fg="white",
                            insertbackground="white", relief="flat",
                            highlightthickness=1, highlightcolor=color)
        pass_ent.pack(fill="x", ipady=6, pady=(2, 16))

        status_var = tk.StringVar(value="")
        tk.Label(self._container, textvariable=status_var,
                 font=("Helvetica", 9), fg="#facc15",
                 bg="#1a1a2e").pack()

        btn_row = tk.Frame(self._container, bg="#1a1a2e")
        btn_row.pack(fill="x", pady=8)

        def _do():
            e, p = email_var.get().strip(), pass_var.get().strip()
            if not e or not p:
                status_var.set("Enter both email and password.")
                return
            status_var.set("Logging in...")
            self.update_idletasks()
            threading.Thread(
                target=self._attempt_login,
                args=(retailer, e, p, status_var),
                daemon=True
            ).start()

        tk.Button(btn_row, text=f"Login to {logo}",
                  command=_do, bg=color, fg="white",
                  font=("Helvetica", 10, "bold"),
                  relief="flat", padx=14, pady=8
                  ).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Skip",
                  command=self._next,
                  bg="#3b3b6b", fg="#ccc",
                  font=("Helvetica", 9),
                  relief="flat", padx=10, pady=8
                  ).pack(side="left")

        pass_ent.bind("<Return>", lambda e: _do())

    def _attempt_login(self, retailer, email, password, status_var):
        def _login(page: Page) -> bool:
            # Use a dedicated fresh page for each login so the shared
            # monitoring page cannot interfere via cross-navigation.
            login_page = page.context.new_page()
            try:
                if retailer == "target":
                    login_page.goto("https://www.target.com/account/login",
                                    wait_until="domcontentloaded", timeout=20000)
                    try:
                        login_page.wait_for_load_state("networkidle", timeout=10000)
                    except:
                        pass

                    login_page.wait_for_selector("#username", timeout=15000)
                    time.sleep(random.uniform(0.8, 1.5))
                    human_type(login_page, "#username", email)
                    try:
                        human_click(login_page, "button[type='submit']")
                    except:
                        pass

                    # After email submit — handle method picker OR direct password field
                    try:
                        # Wait for either: password field directly, or the method-picker page
                        login_page.wait_for_selector(
                            # Direct password field (skip picker)
                            "input[type='password'], "
                            # New 3-option method picker ("Enter your password")
                            "button:has-text('Enter your password'), "
                            "a:has-text('Enter your password'), "
                            # Legacy passkey dismissal options
                            "button[data-test='passkey-cancel-button'], "
                            "a[data-test='use-password-link'], "
                            "button:has-text('Use password'), "
                            "button:has-text('Sign in with a password'), "
                            "[data-test='passkeys-cancel']",
                            timeout=10000
                        )
                        # If the password field is NOT yet visible, click through the method picker
                        if not login_page.is_visible("input[type='password']"):
                            for sel in [
                                # New method picker options (preferred)
                                "button:has-text('Enter your password')",
                                "a:has-text('Enter your password')",
                                "[data-test='password-option']",
                                "[data-test*='enter-password']",
                                # Legacy passkey dismissal fallbacks
                                "button[data-test='passkey-cancel-button']",
                                "a[data-test='use-password-link']",
                                "button:has-text('Use password')",
                                "button:has-text('Sign in with a password')",
                                "[data-test='passkeys-cancel']",
                            ]:
                                try:
                                    login_page.click(sel, timeout=2000)
                                    break
                                except:
                                    continue
                    except:
                        pass

                    login_page.wait_for_selector("input[type='password']", timeout=10000)
                    time.sleep(random.uniform(0.5, 1.0))
                    human_type(login_page, "input[type='password']", password)
                    time.sleep(random.uniform(0.4, 0.9))
                    human_click(login_page, "button[type='submit']")

                    try:
                        login_page.wait_for_url(
                            re.compile(r"(?!.*(/signin|/login)).*target\.com.*"),
                            timeout=20000
                        )
                    except:
                        pass
                    url = login_page.url.lower()
                    return "target.com" in url and "signin" not in url and "login" not in url

                elif retailer == "walmart":
                    # ---- helper: detect DataDome / generic captcha ----
                    def _captcha_present(p):
                        for sel in [
                            "iframe[src*='datadome']",
                            "iframe[src*='captcha']",
                            "#captcha-holder",
                            "#dd-captcha",
                            "iframe[title*='DataDome']",
                            "iframe[title*='CAPTCHA']",
                        ]:
                            try:
                                el = p.query_selector(sel)
                                if el and el.is_visible():
                                    return True
                            except Exception:
                                pass
                        url = p.url.lower()
                        return "captcha" in url or "datadome" in url

                    # Bug 1 fix: include input[name='userName'] and use state=visible
                    email_sel = (
                        "#email, "
                        "input[name='email'], "
                        "input[name='userName'], "
                        "input[type='email'], "
                        "input[autocomplete='email'], "
                        "input[autocomplete='username']"
                    )

                    # Retry loop: initial attempt + up to 2 retries on timeout
                    for attempt in range(3):
                        try:
                            login_page.goto(
                                "https://www.walmart.com/account/login",
                                wait_until="domcontentloaded", timeout=20000,
                            )
                            try:
                                login_page.wait_for_load_state("networkidle", timeout=12000)
                            except Exception:
                                pass

                            # CAPTCHA check after goto
                            if _captcha_present(login_page):
                                if not self._wait_for_captcha_solve(status_var):
                                    return False
                                # Reload login page after captcha solved
                                login_page.goto(
                                    "https://www.walmart.com/account/login",
                                    wait_until="domcontentloaded", timeout=20000,
                                )
                                try:
                                    login_page.wait_for_load_state("networkidle", timeout=12000)
                                except Exception:
                                    pass

                            # Human-like mouse movement before interacting
                            login_page.mouse.move(
                                random.randint(200, 600),
                                random.randint(150, 400),
                                steps=random.randint(15, 30),
                            )
                            time.sleep(random.uniform(0.8, 1.5))

                            # Step 1 — enter email / phone
                            login_page.wait_for_selector(
                                email_sel, state="visible", timeout=15000
                            )
                            if _captcha_present(login_page):
                                if not self._wait_for_captcha_solve(status_var):
                                    return False
                                login_page.wait_for_selector(
                                    email_sel, state="visible", timeout=15000
                                )
                            time.sleep(random.uniform(1.0, 2.0))
                            human_type(login_page, email_sel, email)
                            time.sleep(random.uniform(0.5, 1.0))

                            # Click Continue to advance to the password page
                            human_click(login_page, "button[type='submit']")
                            time.sleep(random.uniform(0.8, 1.5))

                            # Step 2 — enter password
                            login_page.wait_for_selector(
                                "input[type='password']", state="visible", timeout=15000
                            )
                            if _captcha_present(login_page):
                                if not self._wait_for_captcha_solve(status_var):
                                    return False
                            time.sleep(random.uniform(0.8, 1.5))
                            human_type(login_page, "input[type='password']", password)
                            time.sleep(random.uniform(0.4, 0.9))

                            # Submit sign-in
                            human_click(login_page, "button[type='submit']")

                            try:
                                login_page.wait_for_url(
                                    re.compile(r"walmart\.com(?!/account/login)"),
                                    timeout=20000,
                                )
                            except Exception:
                                pass
                            url = login_page.url.lower()
                            return (
                                "walmart.com" in url
                                and "/account/login" not in url
                                and "identity.walmart.com" not in url
                            )

                        except Exception as attempt_err:
                            print(f"[Login:walmart] attempt {attempt + 1} error: {attempt_err}")
                            if attempt >= 2:
                                raise
                            time.sleep(2)
                    return False

            except Exception as login_err:
                print(f"[Login:{retailer}] error: {login_err}")
                return False
            finally:
                try:
                    login_page.close()
                except:
                    pass

        try:
            ok = self.pw.submit(_login, f"login:{retailer}", timeout=60)
            if ok:
                if retailer == "target":
                    self._target_ok = True
                else:
                    self._walmart_ok = True
                self.pw.save_session()
                self.after(0, lambda: status_var.set("Login successful!"))
                self.after(800, self._next)
            else:
                self.after(0, lambda: status_var.set(
                    "Login failed -- check credentials or try again."))
        except Exception as e:
            _msg = str(e)[:60]
            self.after(0, lambda: status_var.set(f"Error: {_msg}"))

    # ------------------------------------------------------------------ captcha
    def _show_captcha_resume_btn(self, status_var):
        """Show a 'Resume after CAPTCHA' button in the UI (called from bg thread)."""
        def _ui():
            status_var.set(
                "⚠️  CAPTCHA detected — solve it in the browser, then click Resume."
            )
            try:
                if self._captcha_btn and self._captcha_btn.winfo_exists():
                    return
            except Exception:
                pass
            self._captcha_btn = tk.Button(
                self._container,
                text="▶  Resume after CAPTCHA",
                command=self._on_captcha_solved,
                bg="#f59e0b", fg="#1a1a2e",
                font=("Helvetica", 10, "bold"),
                relief="flat", padx=14, pady=8,
            )
            self._captcha_btn.pack(pady=4)
        self.after(0, _ui)

    def _on_captcha_solved(self):
        """Called when the user clicks the Resume button."""
        self._captcha_event.set()
        try:
            if self._captcha_btn and self._captcha_btn.winfo_exists():
                self._captcha_btn.destroy()
        except Exception:
            pass
        self._captcha_btn = None

    def _wait_for_captcha_solve(self, status_var, timeout=300):
        """Block the login thread until the user signals CAPTCHA is solved."""
        self._captcha_event.clear()
        self._show_captcha_resume_btn(status_var)
        return self._captcha_event.wait(timeout=timeout)

    # ------------------------------------------------------------------ done
    def _build_done(self):
        self._title("Setup Complete!")
        self._spacer(10)
        self._progress(100)
        self._spacer(20)
        lines = []
        lines.append("Target -- logged in" if self._target_ok
                     else "Target -- skipped")
        lines.append("Walmart -- logged in" if self._walmart_ok
                     else "Walmart -- skipped")
        if os.path.exists(SESSION_FILE) and \
                not (self._target_ok or self._walmart_ok):
            lines.append("\nUsing previously saved session.")
        lines.append(
            "\n\nPress Launch Bot to open the main window.\n"
            "Click Start when ready to begin monitoring."
        )
        self._label("\n".join(lines))
        self._spacer(24)
        self._btn("Launch Bot", self._finish, "#4ade80")

    def _finish(self):
        self.destroy()
        self.on_complete()

    def _title(self, text):
        tk.Label(self._container, text=text,
                 font=("Helvetica", 16, "bold"),
                 fg="#e94560", bg="#1a1a2e",
                 justify="center").pack(pady=(0, 4))

    def _label(self, text):
        tk.Label(self._container, text=text,
                 font=("Helvetica", 10),
                 fg="#a8dadc", bg="#1a1a2e",
                 justify="center").pack()

    def _spacer(self, h):
        tk.Frame(self._container, bg="#1a1a2e", height=h).pack()

    def _btn(self, text, cmd, color):
        tk.Button(self._container, text=text, command=cmd,
                  bg=color, fg="#1a1a2e",
                  font=("Helvetica", 11, "bold"),
                  relief="flat", padx=20, pady=10, width=28
                  ).pack(pady=3)

    def _progress(self, pct: int):
        outer = tk.Frame(self._container, bg="#16213e",
                         height=10, bd=0)
        outer.pack(fill="x", pady=4)
        outer.update_idletasks()
        w = max(outer.winfo_reqwidth(), 400)
        tk.Frame(outer, bg="#4ade80",
                 width=int(w * pct / 100),
                 height=10).place(x=0, y=0)

    def _on_close(self):
        if messagebox.askyesno("Exit",
                               "Cancel setup and exit?",
                               parent=self):
            self.master.destroy()