import requests as req
from config import DISCORD_WEBHOOK, NOTIFY_DESKTOP, NOTIFY_DISCORD, NOTIFY_SOUND


def _beep():
    if not NOTIFY_SOUND:
        return
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 400)
    except:
        print("\a\a\a")


def _desktop(title: str, message: str, timeout: int = 15):
    if not NOTIFY_DESKTOP:
        return
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=timeout)
    except:
        pass


def _discord(message: str, webhook: str = DISCORD_WEBHOOK):
    if not NOTIFY_DISCORD or not webhook:
        return
    try:
        req.post(webhook, json={"content": message}, timeout=5)
    except:
        pass


def notify_cart_success(product: dict, discord_webhook: str = DISCORD_WEBHOOK):
    name  = product["name"]
    price = product.get("price", "?")
    store = product.get("retailer", "").capitalize()

    _desktop(
        title=f"🎴 Added to Cart — {store}!",
        message=f"{name[:60]}\n${price} — GO CHECKOUT NOW!"
    )
    _beep()
    _discord(
        f"🚨 **ADDED TO CART** 🚨\n"
        f"**{store}** — {name}\n"
        f"💰 ${price}\n"
        f"🛒 **GO CHECKOUT NOW:** {product['url']}",
        webhook=discord_webhook
    )


def notify_captcha(product: dict, discord_webhook: str = DISCORD_WEBHOOK):
    store = product.get("retailer", "").capitalize()
    name  = product["name"][:50]

    _desktop(
        title=f"🔒 CAPTCHA on {store} — Solve it!",
        message=f"Bot paused for: {name}\n"
                f"Solve the CAPTCHA in the browser window.",
        timeout=30
    )
    try:
        import winsound
        for _ in range(5):
            winsound.Beep(500, 300)
    except:
        print("\a\a\a\a\a")

    _discord(
        f"🔒 **CAPTCHA DETECTED** — **{store}**\n"
        f"Product: {name}\n"
        f"⚠️ Open the bot browser and solve it to resume.",
        webhook=discord_webhook
    )


def notify_session_expired(retailer: str, discord_webhook: str = DISCORD_WEBHOOK):
    store = retailer.capitalize()

    _desktop(
        title=f"⚠️ {store} Session Expired",
        message=f"Bot paused for {store}.\n"
                f"Click Re-Login in the bot window.",
        timeout=20
    )
    try:
        import winsound
        winsound.Beep(800, 500)
    except:
        print("\a\a")

    _discord(
        f"⚠️ **SESSION EXPIRED** — **{store}**\n"
        f"Open the bot and click **Re-Login** to resume.",
        webhook=discord_webhook
    )