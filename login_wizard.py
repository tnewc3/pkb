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
        self.pw          = pw
        self.on_complete = on_complete
        self.title("Pokemon Bot - Setup")
        self.geometry("620x520")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e")
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._step       = 0
        self._target_ok  = False
        self._walmart_ok = False
        self._container  = tk.Frame(self, bg="#1a1a2e")
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
                    login_page.goto("https://www.target.com/account",
                                    wait_until="domcontentloaded", timeout=20000)
                    try:
                        login_page.click(
                            "button[data-test='accountNav-signIn']",
                            timeout=5000)
                    except:
                        pass

                    login_page.wait_for_selector("#username", timeout=15000)
                    time.sleep(random.uniform(0.8, 1.5))
                    human_type(login_page, "#username", email)
                    try:
                        human_click(login_page, "button[type='submit']")
                    except:
                        pass

                    # Dismiss passkey prompt if shown
                    try:
                        login_page.wait_for_selector(
                            "button[data-test='passkey-cancel-button'],"
                            "a[data-test='use-password-link'],"
                            "button:has-text('Use password'),"
                            "button:has-text('Sign in with a password'),"
                            "[data-test='passkeys-cancel']",
                            timeout=5000
                        )
                        for sel in [
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
                    # Walmart redirects to identity.walmart.com (OIDC).
                    # Navigate and wait for the redirect to settle fully.
                    login_page.goto("https://www.walmart.com/account/login",
                                    wait_until="domcontentloaded", timeout=20000)
                    try:
                        login_page.wait_for_load_state("networkidle", timeout=12000)
                    except:
                        pass

                    # Human-like mouse movement before interacting
                    login_page.mouse.move(
                        random.randint(200, 600),
                        random.randint(150, 400),
                        steps=random.randint(15, 30)
                    )
                    time.sleep(random.uniform(0.8, 1.5))

                    # Step 1 — "Phone number or email" field on identity.walmart.com
                    # Selector covers both the old #email and the new unlabelled input
                    email_sel = (
                        "#email, "
                        "input[name='email'], "
                        "input[type='email'], "
                        "input[autocomplete='email'], "
                        "input[autocomplete='username']"
                    )
                    login_page.wait_for_selector(email_sel, state="visible", timeout=15000)
                    time.sleep(random.uniform(1.0, 2.0))
                    human_type(login_page, email_sel, email)
                    time.sleep(random.uniform(0.5, 1.0))

                    # Click Continue / Next button
                    for btn_sel in [
                        "button[type='submit']",
                        "button:has-text('Continue')",
                        "button:has-text('Next')",
                    ]:
                        try:
                            human_click(login_page, btn_sel)
                            break
                        except:
                            continue

                    # Step 2 — password field (may be on same page or new page after Continue)
                    login_page.wait_for_selector("input[type='password']",
                                                 state="visible", timeout=15000)
                    time.sleep(random.uniform(0.8, 1.5))
                    human_type(login_page, "input[type='password']", password)
                    time.sleep(random.uniform(0.4, 0.9))

                    for btn_sel in [
                        "button[type='submit']",
                        "button:has-text('Sign in')",
                        "button:has-text('Continue')",
                    ]:
                        try:
                            human_click(login_page, btn_sel)
                            break
                        except:
                            continue

                    try:
                        login_page.wait_for_url(
                            re.compile(r"walmart\.com(?!/account/login)"),
                            timeout=20000
                        )
                    except:
                        pass
                    url = login_page.url.lower()
                    return "walmart.com" in url and "/account/login" not in url and "identity.walmart.com" not in url

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