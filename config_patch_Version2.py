# Add to config.py:
PROXY_URL        = os.getenv("PROXY_URL",        "")
PROXY_FILE       = os.getenv("PROXY_FILE",       "proxies.txt")
USE_FREE_PROXIES = os.getenv("USE_FREE_PROXIES", "true").lower() == "true"