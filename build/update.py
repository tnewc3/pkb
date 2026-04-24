"""
Pokémon Card Bot — Updater
Pulls latest files without reinstalling everything.
"""

import shutil
import os
from pathlib import Path

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA")) / "PokemonCardBot"

BOT_FILES = [
    "pokemon_bot_gui.py",
    "login_wizard.py",
    "playwright_manager.py",
    "session_guard.py",
    "settings_screen.py",
    "link_finder.py",
    "stock_checker.py",
    "cart_manager.py",
    "atc.py",
    "retry_worker.py",
    "captcha_handler.py",
    "captcha_solver.py",
    "stealth_setup.py",
    "notifier.py",
    "config.py",
    "proxy_manager.py",
    "proxy_panel.py",
]


def update():
    print("=" * 45)
    print("  Pokémon Card Bot — Updater")
    print("=" * 45)

    if not INSTALL_DIR.exists():
        print("❌ Bot not installed. Run installer.py first.")
        return

    src     = Path(__file__).parent.parent
    updated = 0
    skipped = 0

    for fname in BOT_FILES:
        src_file = src / fname
        dst_file = INSTALL_DIR / fname
        if not src_file.exists():
            print(f"  ⚠️  Not found: {fname}")
            skipped += 1
            continue
        shutil.copy2(src_file, dst_file)
        print(f"  ✅ Updated: {fname}")
        updated += 1

    print()
    print(f"✅ Updated {updated} files, skipped {skipped}.")
    input("Press Enter to exit...")


if __name__ == "__main__":
    update()