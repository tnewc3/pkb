import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import json
import os
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

from playwright_manager import PlaywrightManager
from cart_manager        import CartManager
from retry_worker        import RetryWorker
from session_guard       import SessionGuard
from settings_screen     import SettingsManager, SettingsWindow
from stock_checker       import check_stock
from link_finder         import discover_links, load_products
from config              import (
    DEFAULT_BUDGET,
    MAX_ITEMS_PER_CATEGORY,
    DISCORD_WEBHOOK,
)

SESSION_FILE  = "sessions.json"
PRODUCTS_FILE = "products.json"

_VERSION_URL  = "https://raw.githubusercontent.com/tnewc3/pkb/main/version.txt"
_INSTALL_DIR  = Path(os.environ.get("LOCALAPPDATA", "")) / "PokemonCardBot"

CATEGORIES = {
    "ETBs":               {"prio": 1, "keywords": ["elite trainer"]},
    "Poster Collections": {"prio": 1, "keywords": ["poster collection"]},
    "Booster Bundles":    {"prio": 1, "keywords": ["booster bundle"]},
    "Pin Collections":    {"prio": 2, "keywords": ["pin collection"]},
    "Blisters":           {"prio": 2, "keywords": ["blister"]},
    "Tins":               {"prio": 2, "keywords": ["tin"]},
    "Singles":            {"prio": 3, "keywords": ["single", "holo", "card"]},
    "Booster Boxes":      {"prio": 4, "keywords": ["booster box", "display box"]},
}

PRIO_COLORS   = {1: "#4ade80", 2: "#facc15", 3: "#fb923c", 4: "#f87171"}
BUDGET_RANGES = {60: (40, 70), 100: (80, 110), 150: (120, 160)}

def categorize_products(products: list) -> dict:
    cat = {c: [] for c in CATEGORIES}
    for p in products:
        nl = p["name"].lower()
        matched = False
        for c, cfg in CATEGORIES.items():
            if any(k in nl for k in cfg["keywords"]):
                cat[c].append(p)
                matched = True
                break
        if not matched:
            cat["ETBs"].append(p)
    return cat

class AutomationEngine:
    def __init__(self, pw, cart, get_categorized,
                 get_budget_range, on_log, on_cart_update):
        self.pw               = pw
        self.cart             = cart
        self.get_categorized  = get_categorized
        self.get_budget_range = get_budget_range
        self.on_log           = on_log
        self.on_cart_update   = on_cart_update
        self.CHECK_INTERVAL   = 30
        self._stop            = threading.Event()
        self._workers         = {}
        self._thread          = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="AutoEngine")
        self._thread.start()
        self.on_log("Automation started.")

    def stop(self):
        self._stop.set()
        for w in self._workers.values():
            w.stop()
        self.on_log("Automation stopped.")

    def add_manual_retry(self, product: dict):
        url = product["url"]
        if url in self._workers:
            self.on_log(f"Already queued: {product['name'][:40]}")
            return
        w = RetryWorker(product, self.pw, self.cart,
                        on_success=self._on_added,
                        on_log=self.on_log)
        self._workers[url] = w
        w.start()

    def _on_added(self, product):
        self._workers.pop(product["url"], None)
        self.on_cart_update()

    def _budget_met(self) -> bool:
        lo, _ = self.get_budget_range()
        return self.cart.local_total() >= lo

    def _sorted_products(self) -> list:
        result = []
        for prio in [1, 2, 3, 4]:
            for cat, cfg in CATEGORIES.items():
                if cfg["prio"] == prio:
                    result.extend(self.get_categorized().get(cat, []))
        return result

    def _run(self):
        while not self._stop.is_set():
            if self._budget_met():
                self.on_log("Budget met - monitoring paused.")
                self._stop.wait(self.CHECK_INTERVAL)
                continue
            for p in self._sorted_products():
                if self._stop.is_set() or self._budget_met():
                    break
                if self.cart.is_in_cart(p["url"]):
                    continue
                if p["url"] in self._workers:
                    continue
                in_stock = check_stock(self.pw, p)
                if in_stock:
                    self.on_log(f"IN STOCK: {p['name'][:45]}")
                    self.add_manual_retry(p)
            self._stop.wait(self.CHECK_INTERVAL)

class PokemonBotGUI:
    def __init__(self, root: tk.Tk):
        self.root        = root
        self.root.title("Pokemon Card Bot")
        self.root.configure(bg="#1a1a2e")
        self.root.geometry("1500x950")
        self.root.withdraw()

        self.products    = []
        self.categorized = {}

        self.budget_toggles = {60: False, 100: False, 150: False}
        self.budget_btns    = {}
        self._session_badges = {}

        self.settings = SettingsManager()
        self.pw       = PlaywrightManager()
        self.cart     = CartManager(self.pw)

        self.engine = AutomationEngine(
            pw=self.pw, cart=self.cart,
            get_categorized=lambda: self.categorized,
            get_budget_range=self._active_budget_range,
            on_log=self._log,
            on_cart_update=self._schedule_cart_refresh,
        )

        self.session_guard = SessionGuard(
            pw=self.pw,
            on_session_lost=self._on_session_lost,
            on_session_restored=self._on_session_restored,
            on_log=self._log,
        )

        self.settings.on_change(self._on_settings_changed)
        threading.Thread(target=self._init_playwright, daemon=True).start()
        threading.Thread(target=self._check_for_updates_bg,
                         args=(False,), daemon=True).start()

    def _init_playwright(self):
        # Don't start the CDP browser yet — login wizard opens a clean Chrome
        # instance instead.  pw.start() is called in _on_wizard_complete.
        self.root.after(0, self._show_wizard)

    def _show_wizard(self):
        from login_wizard import LoginWizard
        LoginWizard(self.root,
                    on_complete=self._on_wizard_complete)

    def _on_wizard_complete(self):
        # Now it's safe to start the CDP Chrome — the profile has login cookies.
        threading.Thread(target=self._start_pw_and_launch, daemon=True).start()

    def _start_pw_and_launch(self):
        self._set_status("Starting browser...")
        self.pw.start()
        self.root.after(0, self._finish_launch)

    def _finish_launch(self):
        self.root.deiconify()
        self._build_ui()
        threading.Thread(target=self._load_products, daemon=True).start()
        self.session_guard.start()

    def _active_budget_range(self):
        for b, active in self.budget_toggles.items():
            if active:
                return BUDGET_RANGES[b]
        return self.settings.as_budget_range()

    def _toggle_budget(self, budget: int):
        if self.budget_toggles[budget]:
            self.budget_toggles[budget] = False
        else:
            for b in self.budget_toggles:
                self.budget_toggles[b] = False
            self.budget_toggles[budget] = True
        for b, btn in self.budget_btns.items():
            if self.budget_toggles[b]:
                btn.config(relief="sunken", bg="#a78bfa", fg="#1a1a2e",
                           text=f"Total = ${b} (ON)")
            else:
                btn.config(relief="flat", bg="#3b3b6b", fg="#a78bfa",
                           text=f"Total = ${b}")
        lo, hi = self._active_budget_range()
        self._log(f"Budget -> ${lo}-${hi}")

    def _untoggle_all_budgets(self):
        for b in self.budget_toggles:
            self.budget_toggles[b] = False
        for b, btn in self.budget_btns.items():
            btn.config(relief="flat", bg="#3b3b6b", fg="#a78bfa",
                       text=f"Total = ${b}")
        lo, hi = self.settings.as_budget_range()
        self._log(f"Budget reset -> default ${lo}-${hi}")

    def _build_ui(self):
        top = tk.Frame(self.root, bg="#16213e", pady=8)
        top.pack(fill="x")
        tk.Label(top, text="Pokemon Card Bot",
                 font=("Helvetica", 18, "bold"),
                 fg="#e94560", bg="#16213e").pack(side="left", padx=20)
        self.status_lbl = tk.Label(top, text="Loading...",
                                   font=("Helvetica", 10),
                                   fg="#a8dadc", bg="#16213e")
        self.status_lbl.pack(side="left", padx=10)

        badge_frame = tk.Frame(top, bg="#16213e")
        badge_frame.pack(side="left", padx=10)
        for retailer in ["target", "walmart"]:
            b = tk.Label(badge_frame,
                         text=f"... {retailer.capitalize()}",
                         font=("Helvetica", 9, "bold"),
                         fg="#facc15", bg="#16213e", padx=8)
            b.pack(side="left", padx=4)
            self._session_badges[retailer] = b
        tk.Button(badge_frame, text="Check Sessions",
                  command=lambda: threading.Thread(
                      target=self.session_guard.force_check,
                      daemon=True).start(),
                  bg="#16213e", fg="#a8dadc",
                  font=("Helvetica", 9), relief="flat", padx=6
                  ).pack(side="left", padx=4)

        for text, cmd, bg, fg in [
            ("Start",            self.engine.start,          "#4ade80", "#1a1a2e"),
            ("Stop",             self.engine.stop,           "#e94560", "white"),
            ("Re-Login",         self._relogin,              "#facc15", "#1a1a2e"),
            ("Settings",         self._open_settings,        "#0f3460", "#a8dadc"),
            ("Refresh Products", self._refresh_products,     "#0f3460", "#a8dadc"),
            ("Check Updates",    self._check_for_updates,    "#0f3460", "#a8dadc"),
        ]:
            tk.Button(top, text=text, command=cmd,
                      bg=bg, fg=fg,
                      font=("Helvetica", 10, "bold"),
                      relief="flat", padx=10
                      ).pack(side="right", padx=3)

        cbar = tk.Frame(self.root, bg="#0f3460", pady=6)
        cbar.pack(fill="x")
        tk.Label(cbar, text="Cart Total:",
                 font=("Helvetica", 10, "bold"),
                 fg="white", bg="#0f3460").pack(side="left", padx=15)
        self.cart_total_lbl = tk.Label(cbar, text="${:.2f} ".format(self.cart.local_total()),
                                       font=("Helvetica", 13, "bold"),
                                       fg="#f5a623", bg="#0f3460")
        self.cart_total_lbl.pack(side="left")
        self.cart_count_lbl = tk.Label(cbar, text="(0 items)",
                                       font=("Helvetica", 10),
                                       fg="#a8dadc", bg="#0f3460")
        self.cart_count_lbl.pack(side="left", padx=8)
        tk.Button(cbar, text="Refresh Cart",
                  command=lambda: threading.Thread(
                      target=self._refresh_site_cart, daemon=True).start(),
                  bg="#16213e", fg="#a8dadc",
                  font=("Helvetica", 9), relief="flat", padx=8
                  ).pack(side="right", padx=15)

        leg = tk.Frame(self.root, bg="#16213e", pady=5)
        leg.pack(fill="x")
        for color, desc in [
            ("#4ade80", "PRIO I - ETBs, Posters, Bundles"),
            ("#facc15", "PRIO II - Pins, Tins, Blisters"),
            ("#fb923c", "PRIO III - Singles"),
            ("#f87171", "PRIO IV - Booster Boxes"),
        ]:
            tk.Label(leg, text=f"  {desc}",
                     font=("Helvetica", 9), fg=color, bg="#16213e"
                     ).pack(side="left", padx=12)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)
        s = ttk.Style()
        s.theme_use("default")
        s.configure("TNotebook",     background="#1a1a2e", borderwidth=0)
        s.configure("TNotebook.Tab", background="#16213e",
                    foreground="#a8dadc", padding=[12, 5])
        s.map("TNotebook.Tab",
              background=[("selected", "#0f3460")],
              foreground=[("selected", "white")])

        self.panels_tab = tk.Frame(self.nb, bg="#1a1a2e")
        self.nb.add(self.panels_tab, text="Products")
        self._build_panels_tab()

        self.cart_tab = tk.Frame(self.nb, bg="#1a1a2e")
        self.nb.add(self.cart_tab, text="View Cart")
        self._build_cart_tab()

        self._build_bottom_bar()

    def _build_panels_tab(self):
        c  = tk.Canvas(self.panels_tab, bg="#1a1a2e", highlightthickness=0)
        sb = ttk.Scrollbar(self.panels_tab, orient="vertical", command=c.yview)
        self.panels_frame = tk.Frame(c, bg="#1a1a2e")
        self.panels_frame.bind("<Configure",
            lambda e: c.configure(scrollregion=c.bbox("all")))
        c.create_window((0, 0), window=self.panels_frame, anchor="nw")
        c.configure(yscrollcommand=sb.set)
        c.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        c.bind_all("<MouseWheel>",
            lambda e: c.yview_scroll(-1*(e.delta//120), "units"))

    def _build_cart_tab(self):
        hdr = tk.Frame(self.cart_tab, bg="#16213e", pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Live Cart - Target + Walmart",
                 font=("Helvetica", 12, "bold"),
                 fg="#a8dadc", bg="#16213e").pack(side="left", padx=15)
        tk.Button(hdr, text="Refresh",
                  command=lambda: threading.Thread(
                      target=self._refresh_site_cart, daemon=True).start(),
                  bg="#0f3460", fg="#a8dadc",
                  font=("Helvetica", 10), relief="flat", padx=10
                  ).pack(side="right", padx=15)
        c  = tk.Canvas(self.cart_tab, bg="#1a1a2e", highlightthickness=0)
        sb = ttk.Scrollbar(self.cart_tab, orient="vertical", command=c.yview)
        self.cart_list_frame = tk.Frame(c, bg="#1a1a2e")
        self.cart_list_frame.bind("<Configure",
            lambda e: c.configure(scrollregion=c.bbox("all")))
        c.create_window((0, 0), window=self.cart_list_frame, anchor="nw")
        c.configure(yscrollcommand=sb.set)
        c.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.site_total_lbl = tk.Label(self.cart_tab,
                                       text="Site Cart Total: $0.00",
                                       font=("Helvetica", 12, "bold"),
                                       fg="#f5a623", bg="#1a1a2e")
        self.site_total_lbl.pack(pady=6)

    def _build_bottom_bar(self):
        bar = tk.Frame(self.root, bg="#16213e", pady=10)
        bar.pack(fill="x", side="bottom")

        row1 = tk.Frame(bar, bg="#16213e")
        row1.pack(fill="x", padx=10, pady=3)
        for label, prio, color in [
            ("TRY PRIO I",   1, "#4ade80"),
            ("TRY PRIO II",  2, "#facc15"),
            ("TRY PRIO III", 3, "#fb923c"),
            ("TRY PRIO IV",  4, "#f87171"),
        ]:
            tk.Button(row1, text=label,
                      command=lambda p=prio: self._add_by_priority(p),
                      bg=color, fg="#1a1a2e",
                      font=("Helvetica", 10, "bold"),
                      relief="flat", padx=15, pady=8, width=16
                      ).pack(side="left", padx=8)

        row2 = tk.Frame(bar, bg="#16213e")
        row2.pack(fill="x", padx=10, pady=3)
        for budget in [60, 100, 150]:
            btn = tk.Button(row2, text=f"Total = ${budget}",
                            command=lambda b=budget: self._toggle_budget(b),
                            bg="#3b3b6b", fg="#a78bfa",
                            font=("Helvetica", 10, "bold"),
                            relief="flat", padx=15, pady=8, width=16)
            btn.pack(side="left", padx=8)
            self.budget_btns[budget] = btn
        tk.Button(row2, text="Clear Toggle",
                  command=self._untoggle_all_budgets,
                  bg="#3b3b6b", fg="#ccc",
                  font=("Helvetica", 9), relief="flat",
                  padx=10, pady=8).pack(side="left", padx=4)
        tk.Button(row2, text="ADD ALL",
                  command=self._add_all,
                  bg="#e94560", fg="white",
                  font=("Helvetica", 10, "bold"),
                  relief="flat", padx=15, pady=8, width=16
                  ).pack(side="left", padx=8)

        self.log_box = scrolledtext.ScrolledText(
            bar, height=5,
            bg="#0a0a1a", fg="#a8dadc",
            font=("Courier", 8), relief="flat")
        self.log_box.pack(fill="x", padx=10, pady=(5, 0))

    def _build_category_panels(self):
        for w in self.panels_frame.winfo_children():
            w.destroy()
        max_items = self.settings.get_int("MAX_ITEMS_PER_CATEGORY", 10)
        COLS = 4
        for i, (cat, cfg) in enumerate(CATEGORIES.items()):
            prods = self.categorized.get(cat, [])
            color = PRIO_COLORS[cfg["prio"]]
            panel = tk.Frame(self.panels_frame, bg="#16213e",
                             bd=2, relief="groove", padx=4, pady=4)
            panel.grid(row=i//COLS, column=i%COLS,
                       padx=6, pady=6, sticky="nsew")
            self.panels_frame.grid_columnconfigure(i%COLS, weight=1)

            tk.Label(panel, text=f"{cat}  ({len(prods)} found)",
                     font=("Helvetica", 10, "bold"),
                     fg=color, bg="#16213e", justify="center"
                     ).pack(fill="x", pady=(0, 4))
            ttk.Separator(panel).pack(fill="x")

            if not prods:
                tk.Label(panel,
                         text="No items found.\nClick Refresh.",
                         font=("Helvetica", 9), fg="#555", bg="#16213e",
                         justify="center").pack(pady=10)
            else:
                for p in prods[:max_items]:
                    row = tk.Frame(panel, bg="#16213e")
                    row.pack(fill="x", pady=1)
                    name  = p["name"]
                    short = (name[:34]+"...") if len(name) > 34 else name
                    tk.Label(row,
                             text=f"- {short}  ${p.get('price','?')}",
                             font=("Helvetica", 8), fg="#ccc", bg="#16213e",
                             anchor="w", wraplength=210, justify="left"
                             ).pack(side="left", fill="x", expand=True)
                    tk.Button(row, text="Add",
                              command=lambda prod=p:
                                  self.engine.add_manual_retry(prod),
                              bg="#0f3460", fg=color,
                              font=("Helvetica", 8, "bold"),
                              relief="flat", padx=6
                              ).pack(side="right")

            ttk.Separator(panel).pack(fill="x", pady=2)
            tk.Button(panel, text="ADD ALL",
                      command=lambda ps=prods:
                          [self.engine.add_manual_retry(p) for p in ps],
                      bg=color, fg="#1a1a2e",
                      font=("Helvetica", 9, "bold"),
                      relief="flat", pady=4).pack(fill="x")

    def _refresh_site_cart(self):
        self._log("Fetching live cart...")
        try:
            data = self.cart.fetch_site_cart()
            self.root.after(0, lambda: self._render_site_cart(data))
        except Exception as e:
            self._log(f"Cart fetch error: {e}")

    def _render_site_cart(self, data: dict):
        for w in self.cart_list_frame.winfo_children():
            w.destroy()
        items = data.get("items", [])
        total = data.get("total", 0.0)
        if not items:
            tk.Label(self.cart_list_frame,
                     text="Cart is empty on both sites.",
                     font=("Helvetica", 11), fg="#666", bg="#1a1a2e"
                     ).pack(pady=30)
        else:
            for item in items:
                row = tk.Frame(self.cart_list_frame,
                               bg="#16213e", pady=4, padx=8)
                row.pack(fill="x", padx=10, pady=2)
                rc = "#e94560" if item["retailer"] == "target" else "#0071ce"
                tk.Label(row, text=item["retailer"].capitalize(),
                         font=("Helvetica", 8, "bold"),
                         fg=rc, bg="#16213e", width=7).pack(side="left")
                tk.Label(row, text=item["name"],
                         font=("Helvetica", 9),
                         fg="#ccc", bg="#16213e", anchor="w"
                         ).pack(side="left", fill="x", expand=True)
                tk.Label(row, text=f"${item['price']:.2f}",
                         font=("Helvetica", 9, "bold"),
                         fg="#f5a623", bg="#16213e"
                         ).pack(side="right", padx=10)
        self.site_total_lbl.config(text=f"Site Cart Total: ${total:.2f}")
        self._log(f"Cart: {len(items)} items, ${total:.2f}")

    def _add_by_priority(self, prio: int):
        count = 0
        for cat, cfg in CATEGORIES.items():
            if cfg["prio"] == prio:
                for p in self.categorized.get(cat, []):
                    self.engine.add_manual_retry(p)
                    count += 1
        self._log(f"PRIO {prio}: Queued {count} items.")

    def _add_all(self):
        count = 0
        for prods in self.categorized.values():
            for p in prods:
                self.engine.add_manual_retry(p)
                count += 1
        self._log(f"Queued all {count} items.")

    def _relogin(self):
        from login_wizard import LoginWizard
        # Stop the CDP Chrome so the profile lock is released
        self.session_guard.stop()
        self.engine.stop()
        self.pw.stop()
        LoginWizard(self.root,
                    on_complete=self._on_relogin_complete)

    def _on_relogin_complete(self):
        threading.Thread(target=self._restart_pw, daemon=True).start()

    def _restart_pw(self):
        self._set_status("Restarting browser...")
        self.pw = PlaywrightManager()
        self.cart = CartManager(self.pw)
        self.engine.pw       = self.pw
        self.engine.cart     = self.cart
        self.session_guard.pw = self.pw
        self.pw.start()
        self.root.after(0, self._after_relogin)

    def _after_relogin(self):
        self._set_status("Ready")
        self.session_guard.start()
        self._log("Re-login complete.")

    def _open_settings(self):
        SettingsWindow(self.root, self.settings,
                       on_save_callback=self._on_settings_changed)

    def _on_session_lost(self, retailer: str):
        self.root.after(0,
            lambda: self._update_session_badge(retailer, False))
        if not any(self.session_guard.is_logged_in(r)
                   for r in ["target", "walmart"]):
            self.engine.stop()
            self._log("All sessions expired — bot paused.")
        # Prompt the user to sign back in manually
        name = retailer.capitalize()
        self.root.after(0, lambda: messagebox.showwarning(
            f"{name} Session Expired",
            f"Your {name} session has expired.\n\n"
            f"Click  Re-Login  in the toolbar, then sign in to {name} "
            f"in the browser window that opens.\n\n"
            f"The bot will resume automatically once you're signed in.",
        ))

    def _on_session_restored(self, retailer: str):
        self.root.after(0,
            lambda: self._update_session_badge(retailer, True))
        if not self.engine._thread or not self.engine._thread.is_alive():
            self.engine.start()
            self._log("Session restored - bot resumed.")

    def _update_session_badge(self, retailer: str, ok: bool):
        badge = self._session_badges.get(retailer)
        if badge:
            badge.config(
                text=f"OK {retailer.capitalize()}" if ok
                     else f"EXPIRED {retailer.capitalize()}",
                fg="#4ade80" if ok else "#e94560",
            )

    def _on_settings_changed(self, new_values: dict):
        if "CHECK_INTERVAL" in new_values:
            self.engine.CHECK_INTERVAL = int(new_values["CHECK_INTERVAL"])
            self._log(f"Check interval -> {new_values['CHECK_INTERVAL']}s")
        if "RETRY_INTERVAL" in new_values:
            import retry_worker
            retry_worker.RETRY_INTERVAL = int(new_values["RETRY_INTERVAL"])
            self._log(f"Retry interval -> {new_values['RETRY_INTERVAL']}s")
        if "SESSION_CHECK_INTERVAL" in new_values:
            import session_guard
            session_guard.SESSION_CHECK_INTERVAL = int(
                new_values["SESSION_CHECK_INTERVAL"])
            self._log(f"Session interval -> {new_values['SESSION_CHECK_INTERVAL']}s")
        if "MAX_ITEMS_PER_CATEGORY" in new_values:
            self.root.after(0, self._build_category_panels)
        if "DEFAULT_BUDGET_LOW" in new_values or \
           "DEFAULT_BUDGET_HIGH" in new_values:
            lo, hi = self.settings.as_budget_range()
            self._log(f"Default budget -> ${lo}-${hi}")

    def _load_products(self):
        self._set_status("Loading products...")
        if os.path.exists(PRODUCTS_FILE):
            self.products = load_products()
        else:
            self.products = discover_links()
        self.categorized = categorize_products(self.products)
        total = sum(len(v) for v in self.categorized.values())
        self.root.after(0, self._build_category_panels)
        self._set_status(f"{total} products loaded")
        self._log(f"{total} products across {len(CATEGORIES)} categories.")

    def _refresh_products(self):
        if os.path.exists(PRODUCTS_FILE):
            os.remove(PRODUCTS_FILE)
        threading.Thread(target=self._load_products, daemon=True).start()

    def _schedule_cart_refresh(self):
        self.root.after(0, self._update_local_cart_bar)

    def _update_local_cart_bar(self):
        self.cart_total_lbl.config(text=f"${self.cart.local_total():.2f}")
        self.cart_count_lbl.config(text=f"({self.cart.count()} items)")

    # ── UPDATE CHECK ─────────────────────────────────────────────────────────

    def _check_for_updates(self):
        """Manual check — always shows a result dialog."""
        threading.Thread(target=self._check_for_updates_bg,
                         args=(True,), daemon=True).start()

    def _check_for_updates_bg(self, interactive: bool):
        try:
            req = urllib.request.Request(
                _VERSION_URL,
                headers={"User-Agent": "PokemonCardBot-Updater/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                remote = resp.read().decode().strip()
        except Exception:
            if interactive:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Update Check Failed",
                    "Could not reach the update server.\n"
                    "Check your internet connection and try again.",
                ))
            return

        ver_file = _INSTALL_DIR / "version.txt"
        local = ver_file.read_text(encoding="utf-8").strip() if ver_file.exists() else "unknown"

        if local == remote:
            if interactive:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Up to Date",
                    f"You are running the latest version ({remote}).",
                ))
            return

        self._log(f"[UPDATE] New version available: {remote}  (installed: {local})")

        def _prompt():
            if messagebox.askyesno(
                "Update Available",
                f"A new version is available!\n\n"
                f"  Installed : {local}\n"
                f"  Latest    : {remote}\n\n"
                f"Install now? The bot will close after updating.",
            ):
                self._run_updater()
        self.root.after(0, _prompt)

    def _run_updater(self):
        update_bat = _INSTALL_DIR / "update.bat"
        if not update_bat.exists():
            messagebox.showerror(
                "Updater Not Found",
                f"update.bat was not found in:\n{_INSTALL_DIR}\n\n"
                "Re-run the installer to restore it.",
            )
            return
        subprocess.Popen(
            ["cmd", "/c", str(update_bat)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        self.root.after(500, self.root.destroy)

    # ─────────────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        if hasattr(self, "status_lbl"):
            self.root.after(0, lambda: self.status_lbl.config(text=msg))

    def _log(self, msg: str):
        if hasattr(self, "log_box"):
            self.root.after(0, lambda: (
                self.log_box.insert("end", msg + "\n"),
                self.log_box.see("end")
            ))

if __name__ == "__main__":
    root = tk.Tk()
    app  = PokemonBotGUI(root)
    root.mainloop()