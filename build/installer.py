"""
Pokémon Card Bot — Windows Installer
Run this once to set everything up.
Double-click install.bat or run: python installer.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
import powershell

APP_NAME    = "Pokemon Card Bot"
APP_VERSION = "1.0.0"

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA")) / "PokemonCardBot"
VENV_DIR    = INSTALL_DIR / "venv"
LAUNCH_BAT  = INSTALL_DIR / "launch.bat"

def get_desktop() -> Path:
    """Get the real Desktop path even on OneDrive-redirected machines."""
    try:
        result = subprocess.run(
            ["powershell", "-command", "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True
        )
        desktop = result.stdout.strip()
        if desktop and Path(desktop).exists():
            return Path(desktop)
    except:
        pass
    # Fallbacks
    for candidate in [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Desktop",
        Path("C:/Users/thomasadmin/Desktop"),
    ]:
        if candidate.exists():
            return candidate
    # Last resort — create it
    fallback = Path(os.environ.get("USERPROFILE", "C:/Users/Public")) / "Desktop"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

PACKAGES = [
    "playwright",
    "requests==2.31.0",
    "plyer==2.1.0",
    "python-dotenv==1.0.1",
    "beautifulsoup4==4.12.3",
    "swiftshadow==2.4.0",
]

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


class Installer:
    def __init__(self):
        self.errors  = []
        self.desktop = get_desktop()
        self.shortcut = self.desktop / "Pokemon Card Bot.bat"

    def run(self):
        print("=" * 55)
        print(f"  {APP_NAME} v{APP_VERSION} — Installer")
        print("=" * 55)
        print()
        print(f"   Desktop detected: {self.desktop}")
        print()

        steps = [
            ("Checking Python version",      self._check_python),
            ("Creating install directory",   self._create_install_dir),
            ("Copying bot files",            self._copy_files),
            ("Creating virtual environment", self._create_venv),
            ("Installing dependencies",      self._install_deps),
            ("Installing Playwright browsers", self._install_browsers),
            ("Creating .env file",           self._create_env),
            ("Creating launcher",            self._create_launcher),
            ("Creating desktop shortcut",    self._create_shortcut),
            ("Creating uninstaller",         self._create_uninstaller),
        ]

        for label, fn in steps:
            self._step(label, fn)

        print()
        if self.errors:
            print("⚠️  Setup completed with warnings:")
            for e in self.errors:
                print(f"   • {e}")
        else:
            print("✅  Installation complete!")

        print()
        print(f"📁 Installed to: {INSTALL_DIR}")
        print(f"🖥️  Desktop shortcut: {self.shortcut}")
        print()
        print("Double-click  'Pokemon Card Bot'  on your desktop to launch.")
        print()
        input("Press Enter to exit...")

    # ── STEPS ────────────────────────────────

    def _check_python(self):
        v = sys.version_info
        if v.major < 3 or (v.major == 3 and v.minor < 11):
            raise RuntimeError(
                f"Python 3.11+ required. You have {v.major}.{v.minor}. "
                f"Download from python.org"
            )
        print(f"   Python {v.major}.{v.minor}.{v.micro} ✅")

    def _create_install_dir(self):
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        print(f"   {INSTALL_DIR}")

    def _copy_files(self):
        src     = Path(__file__).parent.parent  # project root
        copied  = 0
        missing = []

        for fname in BOT_FILES:
            src_file = src / fname
            dst_file = INSTALL_DIR / fname
            if src_file.exists():
                shutil.copy2(src_file, dst_file)
                copied += 1
            else:
                missing.append(fname)

        print(f"   Copied {copied}/{len(BOT_FILES)} files")
        if missing:
            self.errors.append(f"Missing files: {', '.join(missing)}")

    def _create_venv(self):
        if VENV_DIR.exists():
            print("   Virtual environment already exists — skipping.")
            return
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=True, capture_output=True
        )
        print(f"   Created venv at {VENV_DIR}")

    def _install_deps(self):
        pip = VENV_DIR / "Scripts" / "pip.exe"
        print("   Installing packages (this may take a minute)...")
        for pkg in PACKAGES:
            print(f"   → {pkg}")
            result = subprocess.run(
                [str(pip), "install", pkg, "--quiet"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                # Show actual error for debugging
                print(f"   ⚠️  {pkg} warning: {result.stderr[-200:].strip()}")
        print("   All packages installed ✅")

    def _install_browsers(self):
        pw_exe = VENV_DIR / "Scripts" / "playwright.exe"
        if not pw_exe.exists():
            self.errors.append(
                "playwright.exe not found in venv — "
                "run: venv\\Scripts\\playwright install chromium"
            )
            return
        print("   Downloading Chromium (~120MB)...")
        result = subprocess.run(
            [str(pw_exe), "install", "chromium"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            self.errors.append(
                f"Playwright browser install: {result.stderr[:100]}")
        else:
            print("   Chromium installed ✅")

    def _create_env(self):
        env_file = INSTALL_DIR / ".env"
        if env_file.exists():
            print("   .env already exists — skipping.")
            return
        env_file.write_text(
            "# Pokémon Card Bot Settings\n\n"
            "TARGET_EMAIL=\n"
            "TARGET_PASSWORD=\n"
            "WALMART_EMAIL=\n"
            "WALMART_PASSWORD=\n\n"
            "CHECK_INTERVAL=30\n"
            "RETRY_INTERVAL=15\n"
            "SESSION_CHECK_INTERVAL=300\n\n"
            "DEFAULT_BUDGET_LOW=100\n"
            "DEFAULT_BUDGET_HIGH=110\n\n"
            "DISCORD_WEBHOOK_URL=\n"
            "NOTIFY_DESKTOP=true\n"
            "NOTIFY_DISCORD=true\n"
            "NOTIFY_SOUND=true\n\n"
            "2CAPTCHA_API_KEY=\n\n"
            "PROXY_URL=\n"
            "PROXY_FILE=proxies.txt\n"
            "USE_FREE_PROXIES=true\n\n"
            "HEADLESS=false\n"
            "MAX_ITEMS_PER_CATEGORY=10\n"
        )
        print(f"   Created {env_file}")

    def _create_launcher(self):
        python_exe = VENV_DIR / "Scripts" / "python.exe"
        LAUNCH_BAT.write_text(
            f"@echo off\n"
            f"cd /d \"{INSTALL_DIR}\"\n"
            f"\"{python_exe}\" pokemon_bot_gui.py\n"
            f"if %errorlevel% neq 0 pause\n"
        )
        vbs = INSTALL_DIR / "launch_silent.vbs"
        vbs.write_text(
            f'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run chr(34) & "{LAUNCH_BAT}" & chr(34), 0\n'
            f'Set WshShell = Nothing\n'
        )
        print(f"   Created launcher: {LAUNCH_BAT}")

    def _create_shortcut(self):
        python_exe = VENV_DIR / "Scripts" / "python.exe"
        bat_content = (
            f"@echo off\n"
            f"cd /d \"{INSTALL_DIR}\"\n"
            f"\"{python_exe}\" pokemon_bot_gui.py\n"
            f"if %errorlevel% neq 0 pause\n"
        )
        self.shortcut.write_text(bat_content)
        print(f"   Created shortcut: {self.shortcut}")

    def _create_uninstaller(self):
        uninstall = INSTALL_DIR / "uninstall.py"
        uninstall.write_text(
            "import shutil, os\n"
            "from pathlib import Path\n\n"
            f"INSTALL_DIR = Path(r'{INSTALL_DIR}')\n"
            f"SHORTCUT    = Path(r'{self.shortcut}')\n\n"
            "confirm = input('Uninstall Pokemon Card Bot? (y/n): ')\n"
            "if confirm.lower() == 'y':\n"
            "    if SHORTCUT.exists():\n"
            "        SHORTCUT.unlink()\n"
            "    shutil.rmtree(INSTALL_DIR, ignore_errors=True)\n"
            "    print('Uninstalled.')\n"
            "else:\n"
            "    print('Cancelled.')\n"
        )
        print("   Created uninstaller")

    # ── HELPERS ──────────────────────────────

    def _step(self, label: str, fn):
        print(f"▶  {label}...")
        try:
            fn()
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            self.errors.append(f"{label}: {e}")


if __name__ == '__main__':
    Installer().run()
