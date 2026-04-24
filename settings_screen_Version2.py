import tkinter as tk
from tkinter import ttk, messagebox
import os
from dotenv import set_key, dotenv_values

ENV_FILE = ".env"


class SettingsManager:
    DEFAULTS = {
        "TARGET_EMAIL":           "",
        "TARGET_PASSWORD":        "",
        "WALMART_EMAIL":          "",
        "WALMART_PASSWORD":       "",
        "CHECK_INTERVAL":         "30",
        "RETRY_INTERVAL":         "15",
        "SESSION_CHECK_INTERVAL": "300",
        "DEFAULT_BUDGET_LOW":     "100",
        "DEFAULT_BUDGET_HIGH":    "110",
        "DISCORD_WEBHOOK_URL":    "",
        "2CAPTCHA_API_KEY":       "",
        "PROXY_URL":              "",
        "HEADLESS":               "false",
        "MAX_ITEMS_PER_CATEGORY": "10",
        "NOTIFY_DESKTOP":         "true",
        "NOTIFY_DISCORD":         "true",
        "NOTIFY_SOUND":           "true",
    }

    def __init__(self):
        self._values    = {}
        self._listeners = []
        self.load()

    def load(self):
        on_disk = dotenv_values(ENV_FILE) if os.path.exists(ENV_FILE) else {}
        for key, default in self.DEFAULTS.items():
            self._values[key] = on_disk.get(key, default)

    def save(self, new_values: dict):
        for key, value in new_values.items():
            self._values[key] = str(value)
            set_key(ENV_FILE, key, str(value))
        for cb in self._listeners:
            try:
                cb(new_values)
            except Exception as e:
                print(f"Settings listener error: {e}")

    def get(self, key: str, fallback="") -> str:
        return self._values.get(key, self.DEFAULTS.get(key, fallback))

    def get_int(self, key: str, fallback: int = 0) -> int:
        try:
            return int(self._values.get(key, fallback))
        except:
            return fallback

    def get_bool(self, key: str, fallback: bool = True) -> bool:
        return self._values.get(key, str(fallback)).lower() == "true"

    def on_change(self, cb):
        self._listeners.append(cb)

    def as_budget_range(self) -> tuple:
        return (
            self.get_int("DEFAULT_BUDGET_LOW",  100),
            self.get_int("DEFAULT_BUDGET_HIGH", 110),
        )


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, settings: SettingsManager,
                 on_save_callback=None):
        super().__init__(parent)
        self.settings         = settings
        self.on_save_callback = on_save_callback
        self.title("⚙️  Settings")
        self.geometry("640x600")
        self.resizable(False, True)
        self.configure(bg="#1a1a2e")
        self.grab_set()
        self._vars = {}
        self._build_ui()
        self._populate()

    def _build_ui(self):
        hdr = tk.Frame(self, bg="#16213e", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙️  Settings",
                 font=("Helvetica", 16, "bold"),
                 fg="#e94560", bg="#16213e").pack(side="left", padx=20)
        tk.Label(hdr, text="Saved to  .env",
                 font=("Helvetica", 9),
                 fg="#666", bg="#16213e").pack(side="right", padx=20)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("S.TNotebook",     background="#1a1a2e", borderwidth=0)
        style.configure("S.TNotebook.Tab", background="#16213e",
                        foreground="#a8dadc", padding=[14,6])
        style.map("S.TNotebook.Tab",
                  background=[("selected","#0f3460")],
                  foreground=[("selected","white")])

        self.nb = ttk.Notebook(self, style="S.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=10, pady=6)

        self._t_accounts      = self._make_tab("👤 Accounts")
        self._t_behaviour     = self._make_tab("🤖 Behaviour")
        self._t_notifications = self._make_tab("🔔 Notifications")
        self._t_advanced      = self._make_tab("🔧 Advanced")

        self._build_accounts()
        self._build_behaviour()
        self._build_notifications()
        self._build_advanced()
        self._build_footer()

    def _make_tab(self, title: str) -> tk.Frame:
        outer  = tk.Frame(self.nb, bg="#1a1a2e")
        self.nb.add(outer, text=title)
        canvas = tk.Canvas(outer, bg="#1a1a2e", highlightthickness=0)
        sb     = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner  = tk.Frame(canvas, bg="#1a1a2e")
        inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return inner

    # ── TABS ─────────────────────────────────

    def _build_accounts(self):
        p = self._t_accounts
        self._section(p, "🎯 Target")
        self._field(p, "Email",    "TARGET_EMAIL")
        self._field(p, "Password", "TARGET_PASSWORD", secret=True)
        self._spacer(p)
        self._section(p, "🛒 Walmart")
        self._field(p, "Email",    "WALMART_EMAIL")
        self._field(p, "Password", "WALMART_PASSWORD", secret=True)
        self._spacer(p)
        self._note(p, "💡 Used for auto re-login when sessions expire.\n"
                      "   Stored only in your local .env file.")

    def _build_behaviour(self):
        p = self._t_behaviour
        self._section(p, "⏱️  Timing")
        self._slider(p, "Stock Check Interval",   "CHECK_INTERVAL",
                     10, 120, "sec",
                     "How often to check product pages for stock.")
        self._slider(p, "Retry Interval",          "RETRY_INTERVAL",
                     5, 60, "sec",
                     "Wait between failed add-to-cart retries.")
        self._slider(p, "Session Check Interval", "SESSION_CHECK_INTERVAL",
                     60, 900, "sec",
                     "How often the session guard checks you are logged in.")
        self._spacer(p)
        self._section(p, "💰 Default Budget (no toggle active)")
        self._range_field(p, "Min $", "DEFAULT_BUDGET_LOW",
                             "Max $", "DEFAULT_BUDGET_HIGH",
                          "Cart range when no budget toggle is selected.")
        self._spacer(p)
        self._section(p, "📦 Display")
        self._slider(p, "Max Items Per Category", "MAX_ITEMS_PER_CATEGORY",
                     5, 50, "items",
                     "How many products to show per category panel.")

    def _build_notifications(self):
        p = self._t_notifications
        self._section(p, "🖥️  Desktop")
        self._toggle(p, "Enable desktop popups", "NOTIFY_DESKTOP")
        self._spacer(p)
        self._section(p, "🔊 Sound")
        self._toggle(p, "Enable sound beeps",    "NOTIFY_SOUND")
        self._spacer(p)
        self._section(p, "💬 Discord")
        self._toggle(p, "Enable Discord notifications", "NOTIFY_DISCORD")
        self._field(p, "Webhook URL", "DISCORD_WEBHOOK_URL")
        self._spacer(p)
        tk.Button(p, text="🧪 Send Test Message",
                  command=self._test_discord,
                  bg="#5865f2", fg="white",
                  font=("Helvetica", 10, "bold"),
                  relief="flat", padx=14, pady=8
                  ).pack(anchor="w", padx=20, pady=4)
        self._note(p,
            "💡 Discord → Server Settings → Integrations → "
            "Webhooks → New Webhook")

    def _build_advanced(self):
        p = self._t_advanced
        self._section(p, "🔑 2Captcha")
        self._field(p, "API Key", "2CAPTCHA_API_KEY", secret=True)
        tk.Button(p, text="🧪 Test 2Captcha Balance",
                  command=self._test_2captcha,
                  bg="#f5a623", fg="#1a1a2e",
                  font=("Helvetica", 10, "bold"),
                  relief="flat", padx=14, pady=8
                  ).pack(anchor="w", padx=20, pady=6)
        self._spacer(p)
        self._section(p, "🌐 Proxy")
        self._field(p, "Proxy URL", "PROXY_URL",
                    placeholder="http://user:pass@host:port")
        self._note(p, "💡 Leave blank for no proxy.\n"
                      "   Format: http://user:password@host:port")
        self._spacer(p)
        self._section(p, "🖥️  Browser")
        self._toggle(p, "Run browser headless (hidden)", "HEADLESS")
        self._note(p, "⚠️  Keep OFF while testing so you can solve CAPTCHAs.")
        self._spacer(p)
        self._section(p, "🗑️  Reset")
        tk.Button(p, text="🔄 Reset All to Defaults",
                  command=self._reset_defaults,
                  bg="#e94560", fg="white",
                  font=("Helvetica", 10),
                  relief="flat", padx=14, pady=8
                  ).pack(anchor="w", padx=20, pady=6)

    def _build_footer(self):
        f = tk.Frame(self, bg="#16213e", pady=10)
        f.pack(fill="x", side="bottom")
        self._unsaved_lbl = tk.Label(f, text="",
                                     font=("Helvetica", 9),
                                     fg="#facc15", bg="#16213e")
        self._unsaved_lbl.pack(side="left", padx=20)
        tk.Button(f, text="❌ Cancel", command=self.destroy,
                  bg="#3b3b6b", fg="#ccc",
                  font=("Helvetica", 10), relief="flat",
                  padx=14, pady=8).pack(side="right", padx=8)
        tk.Button(f, text="💾 Save Settings", command=self._save,
                  bg="#4ade80", fg="#1a1a2e",
                  font=("Helvetica", 11, "bold"),
                  relief="flat", padx=20, pady=8).pack(side="right", padx=8)

    # ── WIDGETS ──────────────────────────────

    def _section(self, p, title):
        tk.Label(p, text=title, font=("Helvetica", 11, "bold"),
                 fg="#a8dadc", bg="#1a1a2e").pack(anchor="w", padx=20, pady=(16,2))
        ttk.Separator(p).pack(fill="x", padx=20, pady=(0,8))

    def _spacer(self, p, h=8):
        tk.Frame(p, bg="#1a1a2e", height=h).pack()

    def _note(self, p, text):
        tk.Label(p, text=text, font=("Helvetica", 9),
                 fg="#666", bg="#1a1a2e",
                 justify="left", anchor="w"
                 ).pack(anchor="w", padx=20, pady=(2,8))

    def _field(self, p, label, key, secret=False, placeholder=""):
        row = tk.Frame(p, bg="#1a1a2e")
        row.pack(fill="x", padx=20, pady=3)
        tk.Label(row, text=label, font=("Helvetica",10),
                 fg="#ccc", bg="#1a1a2e",
                 width=22, anchor="w").pack(side="left")
        var = tk.StringVar()
        self._vars[key] = var
        ent = tk.Entry(row, textvariable=var,
                       show="●" if secret else "",
                       font=("Helvetica",10),
                       bg="#16213e", fg="white",
                       insertbackground="white", relief="flat",
                       highlightthickness=1,
                       highlightbackground="#3b3b6b",
                       highlightcolor="#a8dadc", width=36)
        ent.pack(side="left", ipady=5)
        if secret:
            sv = tk.BooleanVar(value=False)
            tk.Checkbutton(row, text="Show", variable=sv,
                           command=lambda: ent.config(show="" if sv.get() else "●"),
                           bg="#1a1a2e", fg="#666",
                           activebackground="#1a1a2e",
                           selectcolor="#16213e",
                           font=("Helvetica",8)).pack(side="left", padx=6)
        var.trace_add("write", lambda *_: self._mark_unsaved())

    def _slider(self, p, label, key, mn, mx, unit="", note=""):
        row = tk.Frame(p, bg="#1a1a2e")
        row.pack(fill="x", padx=20, pady=4)
        tk.Label(row, text=label, font=("Helvetica",10),
                 fg="#ccc", bg="#1a1a2e",
                 width=30, anchor="w").pack(side="left")
        var = tk.IntVar()
        self._vars[key] = var
        lbl = tk.Label(row, text=f"{var.get()} {unit}",
                       font=("Helvetica",10,"bold"),
                       fg="#f5a623", bg="#1a1a2e", width=10)
        lbl.pack(side="right")
        def _upd(*_):
            lbl.config(text=f"{var.get()} {unit}")
            self._mark_unsaved()
        ttk.Scale(row, from_=mn, to=mx, orient="horizontal",
                  variable=var,
                  command=lambda v: (var.set(int(float(v))), _upd())
                  ).pack(side="left", fill="x", expand=True, padx=8)
        if note:
            self._note(p, note)

    def _range_field(self, p, ll, kl, lh, kh, note=""):
        row = tk.Frame(p, bg="#1a1a2e")
        row.pack(fill="x", padx=20, pady=4)
        for label, key in [(ll, kl), (lh, kh)]:
            tk.Label(row, text=label, font=("Helvetica",10),
                     fg="#ccc", bg="#1a1a2e").pack(side="left", padx=(0,4))
            var = tk.StringVar()
            self._vars[key] = var
            tk.Entry(row, textvariable=var,
                     font=("Helvetica",10),
                     bg="#16213e", fg="white",
                     insertbackground="white", relief="flat",
                     highlightthickness=1,
                     highlightbackground="#3b3b6b",
                     highlightcolor="#a8dadc",
                     width=8).pack(side="left", ipady=5, padx=(0,20))
            var.trace_add("write", lambda *_: self._mark_unsaved())
        if note:
            self._note(p, note)

    def _toggle(self, p, label, key):
        row = tk.Frame(p, bg="#1a1a2e")
        row.pack(fill="x", padx=20, pady=4)
        var = tk.BooleanVar()
        self._vars[key] = var
        tk.Label(row, text=label, font=("Helvetica",10),
                 fg="#ccc", bg="#1a1a2e",
                 width=36, anchor="w").pack(side="left")
        btn = tk.Button(row, text="OFF ❌",
                        command=lambda: var.set(not var.get()),
                        bg="#3b3b6b", fg="#ccc",
                        font=("Helvetica",9,"bold"),
                        relief="flat", padx=10, pady=4, width=8)
        btn.pack(side="left")
        def _upd(*_):
            btn.config(
                text="ON ✅"  if var.get() else "OFF ❌",
                bg="#4ade80"  if var.get() else "#3b3b6b",
                fg="#1a1a2e"  if var.get() else "#ccc",
            )
            self._mark_unsaved()
        var.trace_add("write", _upd)

    # ── POPULATE ─────────────────────────────

    def _populate(self):
        for key, var in self._vars.items():
            val = self.settings.get(key, "")
            if isinstance(var, tk.BooleanVar):
                var.set(str(val).lower() == "true")
            elif isinstance(var, tk.IntVar):
                try:
                    var.set(int(val))
                except:
                    var.set(0)
            else:
                var.set(val)
        self._unsaved_lbl.config(text="")

    # ── SAVE ─────────────────────────────────

    def _save(self):
        new_values = {}
        for key, var in self._vars.items():
            if isinstance(var, tk.BooleanVar):
                new_values[key] = str(var.get()).lower()
            elif isinstance(var, tk.IntVar):
                new_values[key] = str(var.get())
            else:
                new_values[key] = var.get().strip()

        errors = self._validate(new_values)
        if errors:
            messagebox.showerror("Validation Error",
                                 "\n".join(errors), parent=self)
            return

        self.settings.save(new_values)
        self._unsaved_lbl.config(text="✅ Saved!", fg="#4ade80")
        if self.on_save_callback:
            self.on_save_callback(new_values)
        self.after(1200, self.destroy)

    def _validate(self, v: dict) -> list:
        errors = []
        try:
            lo, hi = int(v.get("DEFAULT_BUDGET_LOW", 0)), \
                     int(v.get("DEFAULT_BUDGET_HIGH", 0))
            if lo >= hi:
                errors.append("Budget: Min must be less than Max.")
        except:
            errors.append("Budget: Must be whole numbers.")
        for key, label in [
            ("CHECK_INTERVAL",        "Stock Check Interval"),
            ("RETRY_INTERVAL",        "Retry Interval"),
            ("SESSION_CHECK_INTERVAL","Session Check Interval"),
        ]:
            try:
                if int(v.get(key, 0)) < 5:
                    errors.append(f"{label} must be ≥ 5 seconds.")
            except:
                errors.append(f"{label} must be a number.")
        webhook = v.get("DISCORD_WEBHOOK_URL", "")
        if webhook and not webhook.startswith(
                "https://discord.com/api/webhooks/"):
            errors.append("Discord webhook must start with "
                          "https://discord.com/api/webhooks/")
        return errors

    def _mark_unsaved(self):
        self._unsaved_lbl.config(text="⚠️  Unsaved changes", fg="#facc15")

    def _test_discord(self):
        import requests
        url = self._vars.get("DISCORD_WEBHOOK_URL")
        url = url.get().strip() if url else ""
        if not url:
            messagebox.showwarning("No Webhook",
                "Enter a webhook URL first.", parent=self)
            return
        try:
            r = requests.post(url, json={
                "content": "✅ Pokémon Card Bot — test notification!"
            }, timeout=8)
            if r.status_code in (200, 204):
                messagebox.showinfo("Success",
                    "✅ Test message sent!", parent=self)
            else:
                messagebox.showerror("Failed",
                    f"Status {r.status_code}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _test_2captcha(self):
        import requests
        key = self._vars.get("2CAPTCHA_API_KEY")
        key = key.get().strip() if key else ""
        if not key:
            messagebox.showwarning("No Key",
                "Enter your 2Captcha API key first.", parent=self)
            return
        try:
            r = requests.post("https://api.2captcha.com/getBalance",
                              json={"clientKey": key}, timeout=10)
            data = r.json()
            if data.get("errorId") == 0:
                messagebox.showinfo("Balance",
                    f"✅ Balance: ${data.get('balance', 0):.4f} USD",
                    parent=self)
            else:
                messagebox.showerror("Error",
                    data.get("errorDescription"), parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _reset_defaults(self):
        if messagebox.askyesno("Reset",
            "Reset ALL settings to defaults?\n"
            "This clears credentials, keys, and all customisations.",
            parent=self):
            self.settings.save(self.settings.DEFAULTS.copy())
            self._populate()
            self._unsaved_lbl.config(text="✅ Reset.", fg="#4ade80")