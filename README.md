# 🎴 Pokémon Card Bot (PKB)

Automated Pokémon card monitor and add-to-cart bot for Target and Walmart.

## Features
- Monitors Target + Walmart for Pokémon card restocks
- Auto add-to-cart by priority (ETBs first, Booster Boxes last)
- Budget toggles ($60 / $100 / $150)
- 2Captcha integration with manual fallback
- Session guard with auto re-login
- Rotating proxy support
- Discord + desktop notifications
- Full settings GUI

## Install & Run

### Requirements
- Windows 10/11
- Python 3.11+  →  [python.org](https://python.org)

### First time setup
```
1. Clone or download this repo
2. Double-click  build/install.bat
3. Wait ~2 minutes (downloads Chromium)
4. Double-click "Pokemon Card Bot" on your desktop
```

### Manual run (no installer)
```bash
pip install -r requirements.txt
playwright install chromium
python pokemon_bot_gui.py
```

## Configuration
Edit `.env` or use the ⚙️ Settings panel in the GUI.

| Key | Default | Description |
|---|---|---|
| `TARGET_EMAIL` | — | Target account email |
| `TARGET_PASSWORD` | — | Target account password |
| `WALMART_EMAIL` | — | Walmart account email |
| `WALMART_PASSWORD` | — | Walmart account password |
| `CHECK_INTERVAL` | 30 | Seconds between stock checks |
| `RETRY_INTERVAL` | 15 | Seconds between ATC retries |
| `DEFAULT_BUDGET_LOW` | 100 | Default min cart total |
| `DEFAULT_BUDGET_HIGH` | 110 | Default max cart total |
| `2CAPTCHA_API_KEY` | — | 2captcha.com API key |
| `DISCORD_WEBHOOK_URL` | — | Discord webhook for alerts |
| `USE_FREE_PROXIES` | true | Auto-fetch free proxies |

## Project Structure
```
pkb/
├── pokemon_bot_gui.py      ← entry point
├── login_wizard.py
├── playwright_manager.py
├── session_guard.py
├── settings_screen.py
├── link_finder.py
├── stock_checker.py
├── cart_manager.py
├── atc.py
├── retry_worker.py
├── captcha_handler.py
├── captcha_solver.py
├── stealth_setup.py
├── notifier.py
├── config.py
├── proxy_manager.py
├── proxy_panel.py
├── requirements.txt
├── .env
├── proxies.txt
└── build/
    ├── install.bat
    ├── installer.py
    ├── update.py
    └── create_icon.py
```

## ⚠️ Disclaimer
This bot is for personal educational use only.
