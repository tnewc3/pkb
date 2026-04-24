import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os
from proxy_manager import ProxyManager
from config import PROXY_FILE, PROXY_URL, USE_FREE_PROXIES


class ProxyPanel(tk.Frame):
    """
    Self-contained proxy status panel that can be embedded
    anywhere in the GUI as a tab or frame.

    Features:
    - Enable/Disable toggle (pauses proxy use instantly)
    - Live proxy pool table (url, status, response time)
    - Add/remove proxies manually
    - Health check all button
    - Auto-refresh toggle
    - Free proxy fetch button (swiftshadow)
    - Per-proxy ban check against Target + Walmart
    """

    REFRESH_INTERVAL = 60  # seconds between auto-refresh

    def __init__(self, parent, proxy_mgr: ProxyManager,
                 on_toggle, on_log, **kwargs):
        super().__init__(parent, bg="#1a1a2e", **kwargs)
        self.proxy_mgr   = proxy_mgr
        self.on_toggle   = on_toggle   # callable(enabled: bool)
        self.on_log      = on_log

        self._enabled        = tk.BooleanVar(value=USE_FREE_PROXIES)
        self._auto_refresh   = tk.BooleanVar(value=False)
        self._refresh_thread = None
        self._stop_refresh   = threading.Event()

        self._build()
        self._refresh_table()

    # ── BUILD ─────────────────────────────────

    def _build(self):
        # ── HEADER ROW
        hdr = tk.Frame(self, bg="#16213e", pady=8)
        hdr.pack(fill="x")

        tk.Label(hdr, text="📡 Proxy Manager",
                 font=("Helvetica", 13, "bold"),
                 fg="#a8dadc", bg="#16213e").pack(side="left", padx=15)

        # Master enable/disable toggle
        self._toggle_btn = tk.Button(
            hdr,
            text="",
            command=self._toggle_proxy,
            font=("Helvetica", 11, "bold"),
            relief="flat", padx=16, pady=6, width=14
        )
        self._toggle_btn.pack(side="left", padx=10)
        self._update_toggle_btn()

        # Pool summary
        self._summary_lbl = tk.Label(
            hdr, text="Pool: —",
            font=("Helvetica", 10),
            fg="#a8dadc", bg="#16213e"
        )
        self._summary_lbl.pack(side="left", padx=10)

        # Current proxy in use
        self._current_lbl = tk.Label(
            hdr, text="Active: none",
            font=("Helvetica", 9),
            fg="#facc15", bg="#16213e"
        )
        self._current_lbl.pack(side="left", padx=10)

        # ── ACTION BUTTONS ROW
        btn_row = tk.Frame(self, bg="#1a1a2e", pady=6)
        btn_row.pack(fill="x", padx=10)

        buttons = [
            ("🔍 Health Check All", self._health_check_all,  "#0f3460", "#a8dadc"),
            ("🌐 Fetch Free Proxies",self._fetch_free,        "#0f3460", "#4ade80"),
            ("🗑️  Clear Dead",       self._clear_dead,        "#0f3460", "#f87171"),
            ("🔄 Reload File",       self._reload_file,       "#0f3460", "#facc15"),
        ]
        for label, cmd, bg, fg in buttons:
            tk.Button(btn_row, text=label, command=cmd,
                      bg=bg, fg=fg,
                      font=("Helvetica", 9, "bold"),
                      relief="flat", padx=10, pady=6
                      ).pack(side="left", padx=4)

        # Auto-refresh toggle
        auto_frame = tk.Frame(btn_row, bg="#1a1a2e")
        auto_frame.pack(side="right", padx=10)

        tk.Label(auto_frame, text="Auto-refresh:",
                 font=("Helvetica", 9), fg="#666",
                 bg="#1a1a2e").pack(side="left")

        self._auto_btn = tk.Button(
            auto_frame, text="OFF",
            command=self._toggle_auto_refresh,
            bg="#3b3b6b", fg="#ccc",
            font=("Helvetica", 9, "bold"),
            relief="flat", padx=8, pady=4, width=5
        )
        self._auto_btn.pack(side="left", padx=4)

        # ── ADD PROXY ROW
        add_row = tk.Frame(self, bg="#1a1a2e", pady=4)
        add_row.pack(fill="x", padx=10)

        tk.Label(add_row, text="Add proxy:",
                 font=("Helvetica", 9), fg="#666",
                 bg="#1a1a2e").pack(side="left")

        self._add_var = tk.StringVar()
        tk.Entry(add_row, textvariable=self._add_var,
                 font=("Helvetica", 9),
                 bg="#16213e", fg="white",
                 insertbackground="white",
                 relief="flat",
                 highlightthickness=1,
                 highlightbackground="#3b3b6b",
                 highlightcolor="#a8dadc",
                 width=45
                 ).pack(side="left", padx=6, ipady=4)

        tk.Label(add_row, text="http://user:pass@host:port",
                 font=("Helvetica", 8), fg="#444",
                 bg="#1a1a2e").pack(side="left")

        tk.Button(add_row, text="➕ Add",
                  command=self._add_proxy,
                  bg="#4ade80", fg="#1a1a2e",
                  font=("Helvetica", 9, "bold"),
                  relief="flat", padx=10, pady=4
                  ).pack(side="left", padx=4)

        # ── PROXY TABLE
        table_frame = tk.Frame(self, bg="#1a1a2e")
        table_frame.pack(fill="both", expand=True, padx=10, pady=6)

        # Columns
        cols = ("proxy", "status", "ping", "target", "walmart", "actions")
        self._tree = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            height=14
        )

        # Style
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Proxy.Treeview",
                         background="#16213e",
                         foreground="#ccc",
                         rowheight=26,
                         fieldbackground="#16213e",
                         borderwidth=0)
        style.configure("Proxy.Treeview.Heading",
                         background="#0f3460",
                         foreground="#a8dadc",
                         relief="flat",
                         font=("Helvetica", 9, "bold"))
        style.map("Proxy.Treeview",
                  background=[("selected", "#0f3460")],
                  foreground=[("selected", "white")])
        self._tree.configure(style="Proxy.Treeview")

        # Column headers + widths
        col_config = {
            "proxy":   ("Proxy URL",   300),
            "status":  ("Status",       80),
            "ping":    ("Ping",         70),
            "target":  ("Target",       80),
            "walmart": ("Walmart",      80),
            "actions": ("",             80),
        }
        for col, (heading, width) in col_config.items():
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, anchor="w")

        # Scrollbar
        sb = ttk.Scrollbar(table_frame, orient="vertical",
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Row tags for colour coding
        self._tree.tag_configure("alive",    foreground="#4ade80")
        self._tree.tag_configure("dead",     foreground="#f87171")
        self._tree.tag_configure("checking", foreground="#facc15")
        self._tree.tag_configure("untested", foreground="#888")

        # Right-click context menu
        self._ctx_menu = tk.Menu(self, tearoff=0, bg="#16213e",
                                 fg="white", relief="flat")
        self._ctx_menu.add_command(label="✅ Test this proxy",
                                   command=self._ctx_test)
        self._ctx_menu.add_command(label="🎯 Check vs Target",
                                   command=lambda: self._ctx_ban_check("target"))
        self._ctx_menu.add_command(label="🛒 Check vs Walmart",
                                   command=lambda: self._ctx_ban_check("walmart"))
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="🗑️  Remove",
                                   command=self._ctx_remove)
        self._tree.bind("<Button-3>", self._show_ctx_menu)

        # ── BOTTOM STATUS BAR
        status_bar = tk.Frame(self, bg="#0f3460", pady=4)
        status_bar.pack(fill="x")
        self._status_lbl = tk.Label(
            status_bar, text="Ready.",
            font=("Courier", 8),
            fg="#a8dadc", bg="#0f3460"
        )
        self._status_lbl.pack(side="left", padx=10)

    # ── TOGGLE ───────────────────────────────

    def _toggle_proxy(self):
        self._enabled.set(not self._enabled.get())
        self._update_toggle_btn()
        enabled = self._enabled.get()
        self.on_toggle(enabled)
        state = "ENABLED ✅" if enabled else "DISABLED ❌"
        self.on_log(f"📡 Proxy {state}")
        self._set_status(f"Proxy {state}")

    def _update_toggle_btn(self):
        if self._enabled.get():
            self._toggle_btn.config(
                text="📡 Proxy ON ✅",
                bg="#4ade80", fg="#1a1a2e"
            )
        else:
            self._toggle_btn.config(
                text="📡 Proxy OFF ❌",
                bg="#3b3b6b", fg="#ccc"
            )

    def is_enabled(self) -> bool:
        return self._enabled.get()

    # ── TABLE ────────────────────────────────

    def _refresh_table(self):
        """Rebuild the proxy table from current pool state."""
        for row in self._tree.get_children():
            self._tree.delete(row)

        proxies = self.proxy_mgr._proxies
        dead    = self.proxy_mgr._dead
        current = getattr(self.proxy_mgr, "_current_proxy", None)

        for proxy in proxies:
            is_dead    = proxy in dead
            is_current = proxy == current
            status     = "💀 Dead" if is_dead else ("▶ Active" if is_current else "⏳ Untested")
            tag        = "dead" if is_dead else ("alive" if is_current else "untested")

            short = proxy[:55] + "…" if len(proxy) > 55 else proxy
            self._tree.insert("", "end",
                iid=proxy,
                values=(short, status, "—", "—", "—", "Test"),
                tags=(tag,)
            )

        self._update_summary()
        self._update_current_label()

    def _update_summary(self):
        counts = self.proxy_mgr.count()
        self._summary_lbl.config(
            text=f"Pool: {counts['alive']} alive  "
                 f"💀 {counts['dead']} dead  "
                 f"📋 {counts['total']} total"
        )

    def _update_current_label(self):
        current = getattr(self.proxy_mgr, "_current_proxy", None)
        if current:
            short = current[:45] + "…" if len(current) > 45 else current
            self._current_lbl.config(text=f"Active: {short}")
        else:
            self._current_lbl.config(
                text="Active: direct connection" if not self._enabled.get()
                else "Active: none"
            )

    def _set_row_status(self, proxy: str, status: str,
                         ping: str, tag: str):
        """Update a single row in place."""
        try:
            vals = list(self._tree.item(proxy, "values"))
            vals[1] = status
            vals[2] = ping
            self._tree.item(proxy, values=vals, tags=(tag,))
        except:
            pass

    def _set_row_ban(self, proxy: str, retailer: str, result: str):
        """Update Target or Walmart ban column."""
        col_idx = {"target": 3, "walmart": 4}.get(retailer)
        if col_idx is None:
            return
        try:
            vals = list(self._tree.item(proxy, "values"))
            vals[col_idx] = result
            self._tree.item(proxy, values=vals)
        except:
            pass

    # ── ACTIONS ──────────────────────────────

    def _health_check_all(self):
        self._set_status("⏳ Health checking all proxies...")
        threading.Thread(target=self._run_health_check_all,
                         daemon=True).start()

    def _run_health_check_all(self):
        proxies = list(self.proxy_mgr._proxies)
        for proxy in proxies:
            self.after(0, lambda p=proxy: self._set_row_status(
                p, "⏳ Testing...", "—", "checking"))
            ok, ping = self._test_proxy_timed(proxy)
            if ok:
                self.proxy_mgr._dead.discard(proxy)
                self.after(0, lambda p=proxy, ms=ping: self._set_row_status(
                    p, "✅ Alive", f"{ms}ms", "alive"))
            else:
                self.proxy_mgr.mark_dead(proxy)
                self.after(0, lambda p=proxy: self._set_row_status(
                    p, "💀 Dead", "—", "dead"))

        self.after(0, self._update_summary)
        self.after(0, lambda: self._set_status(
            f"✅ Health check done — "
            f"{self.proxy_mgr.count()['alive']} alive"))
        self.on_log(f"📡 Health check: "
                    f"{self.proxy_mgr.count()['alive']} alive, "
                    f"{self.proxy_mgr.count()['dead']} dead")

    def _fetch_free(self):
        self._set_status("⏳ Fetching free proxies via swiftshadow...")
        threading.Thread(target=self._run_fetch_free, daemon=True).start()

    def _run_fetch_free(self):
        try:
            from swiftshadow.classes import ProxyInterface
            swift = ProxyInterface(
                countries=["US"],
                protocol="http",
                autoRotate=True,
            )
            fetched = []
            for _ in range(20):
                try:
                    p   = swift.get()
                    url = p.as_string()
                    if url and url not in self.proxy_mgr._proxies:
                        fetched.append(url)
                        self.proxy_mgr._proxies.append(url)
                except:
                    break

            self.proxy_mgr._build_cycle()
            self.after(0, self._refresh_table)
            self.after(0, lambda: self._set_status(
                f"✅ Fetched {len(fetched)} new free proxies."))
            self.on_log(f"🌐 Fetched {len(fetched)} free proxies.")
        except ImportError:
            self.after(0, lambda: self._set_status(
                "❌ swiftshadow not installed — pip install swiftshadow"))
        except Exception as e:
            self.after(0, lambda: self._set_status(f"❌ Fetch error: {e}"))

    def _clear_dead(self):
        before = len(self.proxy_mgr._proxies)
        self.proxy_mgr._proxies = [
            p for p in self.proxy_mgr._proxies
            if p not in self.proxy_mgr._dead
        ]
        self.proxy_mgr._dead.clear()
        self.proxy_mgr._build_cycle()
        removed = before - len(self.proxy_mgr._proxies)
        self._refresh_table()
        self._set_status(f"🗑️  Removed {removed} dead proxies.")
        self.on_log(f"🗑️  Cleared {removed} dead proxies.")

    def _reload_file(self):
        self._set_status("🔄 Reloading proxy file...")
        threading.Thread(target=self._run_reload, daemon=True).start()

    def _run_reload(self):
        self.proxy_mgr.reload()
        self.after(0, self._refresh_table)
        self.after(0, lambda: self._set_status(
            f"✅ Reloaded — {self.proxy_mgr.count()['total']} proxies."))

    def _add_proxy(self):
        raw = self._add_var.get().strip()
        if not raw:
            return
        url = raw if raw.startswith("http") else f"http://{raw}"
        if url in self.proxy_mgr._proxies:
            self._set_status("⚠️  Proxy already in pool.")
            return
        self.proxy_mgr._proxies.append(url)
        self.proxy_mgr._build_cycle()
        self._add_var.set("")
        self._refresh_table()
        self._set_status(f"➕ Added: {url[:50]}")
        self.on_log(f"➕ Proxy added: {url[:50]}")

    # ── CONTEXT MENU ─────────────────────────

    def _show_ctx_menu(self, event):
        row = self._tree.identify_row(event.y)
        if row:
            self._tree.selection_set(row)
            self._ctx_menu.post(event.x_root, event.y_root)

    def _selected_proxy(self) -> str | None:
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _ctx_test(self):
        proxy = self._selected_proxy()
        if not proxy:
            return
        self._set_row_status(proxy, "⏳ Testing...", "—", "checking")
        threading.Thread(
            target=self._run_single_test,
            args=(proxy,), daemon=True
        ).start()

    def _run_single_test(self, proxy: str):
        ok, ping = self._test_proxy_timed(proxy)
        if ok:
            self.proxy_mgr._dead.discard(proxy)
            self.after(0, lambda: self._set_row_status(
                proxy, "✅ Alive", f"{ping}ms", "alive"))
        else:
            self.proxy_mgr.mark_dead(proxy)
            self.after(0, lambda: self._set_row_status(
                proxy, "💀 Dead", "—", "dead"))
        self.after(0, self._update_summary)

    def _ctx_ban_check(self, retailer: str):
        proxy = self._selected_proxy()
        if not proxy:
            return
        col = 3 if retailer == "target" else 4
        threading.Thread(
            target=self._run_ban_check,
            args=(proxy, retailer), daemon=True
        ).start()

    def _run_ban_check(self, proxy: str, retailer: str):
        self.after(0, lambda: self._set_row_ban(
            proxy, retailer, "⏳..."))
        banned = self.proxy_mgr.check_if_banned(proxy, retailer)
        result = "❌ Banned" if banned else "✅ OK"
        self.after(0, lambda: self._set_row_ban(proxy, retailer, result))
        store = retailer.capitalize()
        self.on_log(f"📡 {store} ban check — {proxy[:40]}: {result}")

    def _ctx_remove(self):
        proxy = self._selected_proxy()
        if not proxy:
            return
        if messagebox.askyesno("Remove Proxy",
                               f"Remove this proxy?\n{proxy[:60]}",
                               parent=self):
            try:
                self.proxy_mgr._proxies.remove(proxy)
            except ValueError:
                pass
            self.proxy_mgr._dead.discard(proxy)
            self.proxy_mgr._build_cycle()
            self._refresh_table()
            self._set_status(f"🗑️  Removed: {proxy[:40]}")

    # ── AUTO REFRESH ─────────────────────────

    def _toggle_auto_refresh(self):
        self._auto_refresh.set(not self._auto_refresh.get())
        if self._auto_refresh.get():
            self._auto_btn.config(text="ON", bg="#4ade80", fg="#1a1a2e")
            self._stop_refresh.clear()
            self._refresh_thread = threading.Thread(
                target=self._auto_refresh_loop, daemon=True)
            self._refresh_thread.start()
        else:
            self._auto_btn.config(text="OFF", bg="#3b3b6b", fg="#ccc")
            self._stop_refresh.set()

    def _auto_refresh_loop(self):
        while not self._stop_refresh.wait(self.REFRESH_INTERVAL):
            self.after(0, self._health_check_all)

    # ── HELPERS ──────────────────────────────

    def _test_proxy_timed(self, proxy: str) -> tuple[bool, int]:
        """Test proxy and return (alive, ping_ms)."""
        import time, requests as req
        try:
            start = time.time()
            r = req.get(
                "https://httpbin.org/ip",
                proxies={"http": proxy, "https": proxy},
                timeout=6
            )
            ms = int((time.time() - start) * 1000)
            return r.status_code == 200, ms
        except:
            return False, 0

    def _set_status(self, msg: str):
        self.after(0, lambda: self._status_lbl.config(text=msg))