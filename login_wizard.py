import tkinter as tk
from tkinter import messagebox
import threading
import json
import os
import time
from playwright.sync_api import Page
from playwright_manager import PlaywrightManager

SESSION_FILE = "sessions.json"

LOGIN_CONFIG = {
    "target": {
        "url":           "https://www.target.com",
        "logged_in_sel": "[data-test='accountNav-greeting']",
        "color":         "#e94560",
        "logo":          "Target",
        "pct":           33,
    },
    "walmart": {
        "url":           "https://www.walmart.com",
        "logged_in_sel": ".account-menu__user-info, [data-automation-id='user-name']",
        "color":         "#0071ce",
        "logo":          "Walmart",
        "pct":           66,
    },
}


class LoginWizard(tk.Toplevel):
    STEPS = ["welcome", "target", "walmart", "done"]

    def __init__(self, parent, pw: PlaywrightManager, on_complete):
        super().__init__(parent)
        self.pw          = pw
        self.on_complete = on_complete
        self.title("Pokemon Bot - Setup")
        self.geometry("620x480")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e")
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._step       = 0
        self._target_ok  = False
        self._walmart_ok = False
        self._polling    = False
        self._container  = tk.Frame(self, bg="#1a1a2e")
        self._container.pack(fill="both", expand=True, padx=30, pady=20)
        self._show_step()

    def _show_step(self):
        self._polling = False  # cancel any running poll on step change
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
        cfg   = LOGIN_CONFIG[retailer]
        color = cfg["color"]
        logo  = cfg["logo"]

        self._title(f"Sign in to {logo}")
        self._spacer(8)
        self._label(
            f"1.  Click  'Open {logo}'  below to open the {logo} homepage.\n"
            f"2.  Click the sign-in icon on the site and log in normally.\n"
            f"3.  The bot detects your login automatically —\n"
            f"    no need to come back and click anything."
        )
        self._spacer(12)
        self._progress(cfg["pct"])
        self._spacer(16)

        status_var = tk.StringVar(value="")
        tk.Label(self._container, textvariable=status_var,
                 font=("Helvetica", 9), fg="#facc15",
                 bg="#1a1a2e").pack()

        btn_row = tk.Frame(self._container, bg="#1a1a2e")
        btn_row.pack(fill="x", pady=8)

        open_btn = tk.Button(
            btn_row, text=f"Open {logo}",
            bg=color, fg="white",
            font=("Helvetica", 10, "bold"),
            relief="flat", padx=14, pady=8,
        )
        open_btn.pack(side="left", padx=(0, 8))

        def _on_open():
            if self._polling:
                return
            self._polling = True
            open_btn.config(state="disabled", text="Browser opened...")
            threading.Thread(
                target=self._open_and_wait,
                args=(retailer, status_var),
                daemon=True,
            ).start()

        open_btn.config(command=_on_open)

        tk.Button(btn_row, text="Skip",
                  command=self._next,
                  bg="#3b3b6b", fg="#ccc",
                  font=("Helvetica", 9),
                  relief="flat", padx=10, pady=8,
                  ).pack(side="left")

    def _open_and_wait(self, retailer: str, status_var: tk.StringVar):
        """Open the login URL in a new browser tab and poll until signed in."""
        cfg  = LOGIN_CONFIG[retailer]
        url  = cfg["url"]
        sels = [s.strip() for s in cfg["logged_in_sel"].split(",")]

        def _open(page: Page):
            new_pg = page.context.new_page()
            new_pg.goto(url, wait_until="domcontentloaded", timeout=20000)
            return True

        try:
            self.pw.submit(_open, f"manual_login_open:{retailer}", timeout=30)
        except Exception as e:
            self.after(0, lambda: status_var.set(f"Could not open browser: {e}"))
            self._polling = False
            return

        self.after(0, lambda: status_var.set(
            "Waiting for you to sign in... (up to 5 min)"))

        def _check(page: Page) -> bool:
            for pg in page.context.pages:
                for sel in sels:
                    try:
                        el = pg.query_selector(sel)
                        if el and el.is_visible():
                            return True
                    except Exception:
                        pass
            return False

        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            time.sleep(2)
            if not self._polling:
                return  # Skip was pressed; abandon this poll loop
            try:
                ok = self.pw.submit(_check,
                                    f"manual_login_check:{retailer}",
                                    timeout=10)
            except Exception:
                ok = False

            if ok:
                self.pw.save_session()
                if retailer == "target":
                    self._target_ok = True
                else:
                    self._walmart_ok = True
                self.after(0, lambda: status_var.set("Signed in successfully!"))
                self.after(800, self._next)
                return

            remaining = int(deadline - time.monotonic())
            self.after(0, lambda r=remaining: status_var.set(
                f"Waiting for sign-in... ({r // 60}m {r % 60:02d}s remaining)"
            ))

        self.after(0, lambda: status_var.set(
            "Timed out. Press Skip or click the button again."))
        self._polling = False

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