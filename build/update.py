"""
Pokémon Card Bot — Auto Updater
Downloads the latest bot files from GitHub without reinstalling.
Double-click update.bat or run: python update.py
"""

import os
import sys
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

REPO_OWNER = "tnewc3"
REPO_NAME  = "pkb"
BRANCH     = "main"
RAW_BASE   = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/pkb"

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA")) / "PokemonCardBot"
VENV_DIR    = INSTALL_DIR / "venv"

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
    "update.py",
    "version.txt",
]


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "PokemonCardBot-Updater/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "PokemonCardBot-Updater/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


class Updater:
    def __init__(self):
        self.errors = []

    def run(self):
        print("=" * 55)
        print("  Pokemon Card Bot — Auto Updater")
        print("=" * 55)
        print()

        if not INSTALL_DIR.exists():
            print("  Bot is not installed. Run installer.py first.")
            print()
            input("Press Enter to exit...")
            sys.exit(1)

        local_ver = self._read_local_version()
        print(f"  Installed version : {local_ver}")
        print("  Checking GitHub for updates...")

        try:
            remote_ver = _fetch_text(f"{RAW_BASE}/version.txt").strip()
        except Exception as e:
            print(f"\n  Could not reach GitHub: {e}")
            print("  Check your internet connection and try again.")
            print()
            input("Press Enter to exit...")
            sys.exit(1)

        print(f"  Latest version    : {remote_ver}")
        print()

        if local_ver == remote_ver:
            print("  You are already up to date!")
            print()
            input("Press Enter to exit...")
            return

        print(f"  New version available: {remote_ver}")
        confirm = input("  Download and install update? (y/n): ").strip().lower()
        if confirm != "y":
            print("\n  Update cancelled.")
            print()
            input("Press Enter to exit...")
            return

        print()

        steps = [
            ("Downloading bot files",    self._update_files),
            ("Updating pip packages",    self._update_packages),
        ]

        for label, fn in steps:
            self._step(label, fn)

        print()
        if self.errors:
            print("  Completed with warnings:")
            for e in self.errors:
                print(f"   • {e}")
        else:
            print(f"  Successfully updated to v{remote_ver}!")

        print()
        print("  Restart the bot to use the new version.")
        print()
        input("Press Enter to exit...")

    # ── HELPERS ──────────────────────────────────────────────────────────────

    def _read_local_version(self) -> str:
        ver_file = INSTALL_DIR / "version.txt"
        if ver_file.exists():
            return ver_file.read_text(encoding="utf-8").strip()
        return "unknown"

    def _update_files(self):
        updated = 0
        failed  = []

        for fname in BOT_FILES:
            url = f"{RAW_BASE}/{fname}"
            dst = INSTALL_DIR / fname
            try:
                data = _fetch_bytes(url)
                # Write atomically so a partial download never corrupts the live file
                tmp = dst.with_suffix(dst.suffix + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(dst)
                updated += 1
            except Exception as e:
                failed.append(fname)
                self.errors.append(f"{fname}: {e}")

        print(f"   Updated {updated}/{len(BOT_FILES)} files")
        if failed:
            print(f"   Could not update: {', '.join(failed)}")

    def _update_packages(self):
        pip = VENV_DIR / "Scripts" / "pip.exe"
        if not pip.exists():
            self.errors.append("pip not found in venv — skipping package update")
            return

        try:
            reqs_text = _fetch_text(
                f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/pkb/requirements.txt"
            )
        except Exception:
            print("   Could not fetch requirements.txt — skipping package update")
            return

        tmp_reqs = INSTALL_DIR / "_requirements_update.txt"
        tmp_reqs.write_text(reqs_text, encoding="utf-8")
        try:
            result = subprocess.run(
                [str(pip), "install", "-r", str(tmp_reqs), "--upgrade", "--quiet"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                self.errors.append(f"pip upgrade: {result.stderr[-300:].strip()}")
            else:
                print("   Packages up to date")
        finally:
            tmp_reqs.unlink(missing_ok=True)

    def _step(self, label: str, fn):
        print(f"  Running: {label}...")
        try:
            fn()
        except Exception as e:
            print(f"   Failed: {e}")
            self.errors.append(f"{label}: {e}")


if __name__ == "__main__":
    Updater().run()