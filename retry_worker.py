import threading
from playwright_manager import PlaywrightManager
from cart_manager import CartManager
from atc import add_to_cart
from notifier import notify_cart_success
from config import DISCORD_WEBHOOK, RETRY_INTERVAL


class RetryWorker:
    def __init__(self, product: dict, pw: PlaywrightManager,
                 cart: CartManager, on_success, on_log):
        self.product    = product
        self.pw         = pw
        self.cart       = cart
        self.on_success = on_success
        self.on_log     = on_log
        self._stop      = threading.Event()
        self._thread    = threading.Thread(
            target=self._run, daemon=True,
            name=f"Retry:{product['name'][:20]}"
        )

    def start(self): self._thread.start()
    def stop(self):  self._stop.set()

    def _run(self):
        name = self.product["name"][:45]
        self.on_log(f"🔄 Retrying: {name}")

        while not self._stop.is_set():
            success = add_to_cart(self.pw, self.product, self.on_log)
            if success:
                self.cart.mark_added(self.product)
                self.on_log(f"✅ Added to cart: {name}")
                notify_cart_success(self.product, DISCORD_WEBHOOK)
                self.on_success(self.product)
                return
            self.on_log(f"⏳ Retry in {RETRY_INTERVAL}s — {name}")
            self._stop.wait(RETRY_INTERVAL)

        self.on_log(f"🛑 Cancelled: {name}")