import tkinter as tk
from tkinter import messagebox
import threading
import subprocess
import os
from playwright_manager import PROFILE_DIR, _find_chrome

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

    def __init__(self, parent, on_complete):
        super().__init__(parent)
        self.on_complete   = on_complete
        self.title("Pokemon Bot - Setup")
        self.geometry("620x480")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e")
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._step         = 0
        self._target_ok    = False
        self._walmart_ok   = False
        self._chrome_proc  = None
        self._container    = tk.Frame(self, bg="#1a1a2e")
        self._container.pack(fill="both", expand=True, padx=30, pady=20)
        self._show_step()

    def _show_step(self):
        self._kill_chrome()    # close any open login browser on step change
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
        profile_cookies = PROFILE_DIR / "Default" / "Network" / "Cookies"
        if profile_cookies.exists():
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

        done_btn = tk.Button(
            btn_row, text="I've signed in ✓",
            bg="#4ade80", fg="#1a1a2e",
            font=("Helvetica", 10, "bold"),
            relief="flat", padx=14, pady=8,
            state="disabled",
        )
        done_btn.pack(side="left", padx=(0, 8))

        open_btn = tk.Button(
            btn_row, text=f"Open {logo}",
            bg=color, fg="white",
            font=("Helvetica", 10, "bold"),
            relief="flat", padx=14, pady=8,
        )
        open_btn.pack(side="left", padx=(0, 8))

        def _on_done():
            if retailer == "target":
                self._target_ok = True
            else:
                self._walmart_ok = True
            self._next()

        done_btn.config(command=_on_done)

        def _on_open():
            open_btn.config(state="disabled")
            threading.Thread(
                target=self._launch_login_chrome,
                args=(cfg["url"], status_var, done_btn),
                daemon=True,
            ).start()

        open_btn.config(command=_on_open)

        tk.Button(btn_row, text="Skip",
                  command=self._next,
                  bg="#3b3b6b", fg="#ccc",
                  font=("Helvetica", 9),
                  relief="flat", padx=10, pady=8,
                  ).pack(side="left")

    def _launch_login_chrome(self, url: str, status_var: tk.StringVar,
                              done_btn: tk.Button):
        """Launch a plain Chrome process (no CDP) for the user to log in."""
        try:
            chrome_exe = _find_chrome()
        except FileNotFoundError as e:
            self.after(0, lambda: status_var.set(str(e)))
            return

        # Kill any previous login Chrome before launching a new one
        self._kill_chrome()

        try:
            self._chrome_proc = subprocess.Popen(
                [
                    chrome_exe,
                    f"--user-data-dir={PROFILE_DIR}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--no-service-autorun",
                    url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            self.after(0, lambda: status_var.set(f"Could not open browser: {e}"))
            return

        self.after(0, lambda: status_var.set(
            "Sign in, then click  'I've signed in ✓'  above."
        ))
        self.after(0, lambda: done_btn.config(state="normal"))

    def _kill_chrome(self):
        """Terminate the login Chrome subprocess if it's still running."""
        if self._chrome_proc is not None:
            try:
                self._chrome_proc.terminate()
            except Exception:
                pass
            self._chrome_proc = None

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
        self._kill_chrome()
        if messagebox.askyesno("Exit",
                               "Cancel setup and exit?",
                               parent=self):
            self.master.destroy()