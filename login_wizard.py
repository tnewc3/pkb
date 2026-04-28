import tkinter as tk
from tkinter import messagebox
import threading
import subprocess
import json
import os
from pathlib import Path
from playwright_manager import _find_edge, _EDGE_USER_DATA

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
            "This wizard signs you into Target and Walmart so the bot\n"
            "can monitor stock and add items to your cart automatically.\n\n"
            "Your session is saved locally and never uploaded anywhere.\n\n"
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
        if retailer == "target":
            self._build_target_import()
        else:
            self._build_edge_login(retailer)

    def _build_target_import(self):
        """Target: extract session cookies directly from Edge's cookie DB.
        No browser automation — completely sidesteps PerimeterX."""
        self._title("Sign in to Target")
        self._spacer(8)
        self._label(
            "1.  Open Edge and sign into Target normally.\n"
            "2.  Close Edge completely (all windows).\n"
            "    (Check Task Manager and end all msedge.exe processes.)\n"
            "3.  Click  'Import Target Session'  below."
        )
        self._spacer(12)
        self._progress(33)
        self._spacer(16)

        status_var = tk.StringVar(value="")
        tk.Label(self._container, textvariable=status_var,
                 font=("Helvetica", 9), fg="#facc15",
                 bg="#1a1a2e").pack()

        btn_row = tk.Frame(self._container, bg="#1a1a2e")
        btn_row.pack(fill="x", pady=8)

        import_btn = tk.Button(
            btn_row, text="Import Target Session",
            bg="#e94560", fg="white",
            font=("Helvetica", 10, "bold"),
            relief="flat", padx=14, pady=8,
        )
        import_btn.pack(side="left", padx=(0, 8))

        def _on_import():
            import_btn.config(state="disabled", text="Importing...")
            threading.Thread(target=self._import_target_cookies,
                             args=(status_var, import_btn), daemon=True).start()

        import_btn.config(command=_on_import)

        tk.Button(btn_row, text="Skip",
                  command=self._next,
                  bg="#3b3b6b", fg="#ccc",
                  font=("Helvetica", 9),
                  relief="flat", padx=10, pady=8,
                  ).pack(side="left")

    def _import_target_cookies(self, status_var: tk.StringVar, btn: tk.Button):
        """Read Target cookies from Edge's SQLite database and save them."""
        try:
            from cookie_extractor import extract_cookies
            cookies = extract_cookies(["target.com"])
        except FileNotFoundError as e:
            self.after(0, lambda: status_var.set(str(e)))
            self.after(0, lambda: btn.config(state="normal", text="Import Target Session"))
            return
        except Exception as e:
            msg = str(e)
            if "Edge" in msg or "close" in msg.lower():
                self.after(0, lambda: status_var.set(
                    "Close Edge completely (including Task Manager), then try again."))
            else:
                self.after(0, lambda: status_var.set(f"Error: {e}"))
            self.after(0, lambda: btn.config(state="normal", text="Import Target Session"))
            return

        if not cookies:
            self.after(0, lambda: status_var.set(
                "No Target cookies found. Make sure you're signed into Target in Edge."))
            self.after(0, lambda: btn.config(state="normal", text="Import Target Session"))
            return

        # Save to sessions.json in Playwright storage_state format
        session = {"cookies": cookies, "origins": []}
        try:
            with open(SESSION_FILE, "w") as f:
                json.dump(session, f)
        except Exception as e:
            self.after(0, lambda: status_var.set(f"Could not save session: {e}"))
            self.after(0, lambda: btn.config(state="normal", text="Import Target Session"))
            return

        self._target_ok = True
        self.after(0, lambda: status_var.set(
            f"Imported {len(cookies)} cookies successfully!"))
        self.after(800, self._next)

    def _build_edge_login(self, retailer: str):
        """Walmart (and any future retailer): open Edge for manual login."""
        cfg   = LOGIN_CONFIG[retailer]
        color = cfg["color"]
        logo  = cfg["logo"]

        self._title(f"Sign in to {logo}")
        self._spacer(8)
        self._label(
            f"1.  Click  'Open {logo}'  below.\n"
            f"2.  Sign into {logo} in the browser that opens.\n"
            f"3.  Click  'I've signed in \u2713'  when done."
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
            btn_row, text="I've signed in \u2713",
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
            if retailer == "walmart":
                self._walmart_ok = True
            self._next()

        done_btn.config(command=_on_done)

        def _on_open():
            open_btn.config(state="disabled")
            try:
                edge_exe = _find_edge()
            except FileNotFoundError as e:
                status_var.set(str(e))
                open_btn.config(state="normal")
                return
            self._kill_chrome()
            try:
                self._chrome_proc = subprocess.Popen(
                    [edge_exe, "--no-first-run",
                     "--no-default-browser-check", cfg["url"]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                status_var.set(f"Could not open browser: {e}")
                open_btn.config(state="normal")
                return
            status_var.set("Sign in, then click 'I've signed in \u2713' above.")
            done_btn.config(state="normal")

        open_btn.config(command=_on_open)

        tk.Button(btn_row, text="Skip",
                  command=self._next,
                  bg="#3b3b6b", fg="#ccc",
                  font=("Helvetica", 9),
                  relief="flat", padx=10, pady=8,
                  ).pack(side="left")

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