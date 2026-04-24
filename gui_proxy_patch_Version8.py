# In PokemonBotGUI._build_ui() — add a new notebook tab after cart_tab:

self.proxy_tab = tk.Frame(self.nb, bg="#1a1a2e")
self.nb.add(self.proxy_tab, text="📡 Proxies")
self._build_proxy_tab()


# Add this method to PokemonBotGUI:

def _build_proxy_tab(self):
    from proxy_panel  import ProxyPanel
    from proxy_manager import ProxyManager
    from config        import PROXY_FILE, USE_FREE_PROXIES

    # Build (or reuse) the proxy manager
    if not hasattr(self, "proxy_mgr"):
        self.proxy_mgr = ProxyManager(
            proxy_file=PROXY_FILE,
            use_free=USE_FREE_PROXIES
        )

    self.proxy_panel = ProxyPanel(
        self.proxy_tab,
        proxy_mgr=self.proxy_mgr,
        on_toggle=self._on_proxy_toggle,
        on_log=self._log,
    )
    self.proxy_panel.pack(fill="both", expand=True)


def _on_proxy_toggle(self, enabled: bool):
    """
    Called when the proxy toggle is flipped.
    Hot-swaps the Playwright browser with/without proxy.
    """
    self._log(f"📡 Proxy {'enabled' if enabled else 'disabled'} "
              f"— restarting browser...")

    def _restart():
        # Stop engine while we restart browser
        self.engine.stop()

        # Close current browser
        try:
            self.pw.stop()
        except:
            pass

        # Rebuild PlaywrightManager with updated proxy config
        from config import HEADLESS
        import os

        if enabled:
            proxy = self.proxy_mgr.get()
        else:
            proxy = None

        # Patch the manager's proxy for next launch
        self.pw._force_proxy = proxy

        self.pw = PlaywrightManager(force_proxy=proxy)
        self.pw.start()

        # Rebuild dependent objects
        self.cart          = CartManager(self.pw)
        self.engine.pw     = self.pw
        self.engine.cart   = self.cart
        self.session_guard.pw = self.pw

        self.engine.start()
        self._log(
            f"✅ Browser restarted — "
            f"proxy {'ON: ' + str(proxy)[:40] if proxy else 'OFF (direct)'}"
        )

    threading.Thread(target=_restart, daemon=True).start()