from dotenv import load_dotenv
import os

load_dotenv()

TARGET_EMAIL       = os.getenv("TARGET_EMAIL",       "")
TARGET_PASSWORD    = os.getenv("TARGET_PASSWORD",    "")
WALMART_EMAIL      = os.getenv("WALMART_EMAIL",      "")
WALMART_PASSWORD   = os.getenv("WALMART_PASSWORD",   "")

CHECK_INTERVAL            = int(os.getenv("CHECK_INTERVAL",            30))
RETRY_INTERVAL            = int(os.getenv("RETRY_INTERVAL",            15))
SESSION_CHECK_INTERVAL    = int(os.getenv("SESSION_CHECK_INTERVAL",   300))
MAX_ITEMS_PER_CATEGORY    = int(os.getenv("MAX_ITEMS_PER_CATEGORY",    10))

DEFAULT_BUDGET = (
    int(os.getenv("DEFAULT_BUDGET_LOW",  100)),
    int(os.getenv("DEFAULT_BUDGET_HIGH", 110)),
)

DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK_URL", "")
TWOCAPTCHA_API_KEY = os.getenv("2CAPTCHA_API_KEY",    "")
PROXY_URL          = os.getenv("PROXY_URL",           "")
HEADLESS           = os.getenv("HEADLESS", "false").lower() == "true"

NOTIFY_DESKTOP = os.getenv("NOTIFY_DESKTOP", "true").lower() == "true"
NOTIFY_DISCORD = os.getenv("NOTIFY_DISCORD", "true").lower() == "true"
NOTIFY_SOUND   = os.getenv("NOTIFY_SOUND",   "true").lower() == "true"


def get_credentials() -> dict:
    return {
        "target":  (TARGET_EMAIL,  TARGET_PASSWORD),
        "walmart": (WALMART_EMAIL, WALMART_PASSWORD),
    }