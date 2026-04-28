"""
Pokémon Card Bot — Windows Uninstaller
Removes all files, the virtual environment, and the desktop shortcut.
Double-click uninstall.bat or run: python uninstaller.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

APP_NAME    = "Pokemon Card Bot"
APP_VERSION = "1.0.0"

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA")) / "PokemonCardBot"


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
    except Exception:
        pass
    for candidate in [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Desktop",
    ]:
        if candidate.exists():
            return candidate
    return Path(os.environ.get("USERPROFILE", "C:/Users/Public")) / "Desktop"


class Uninstaller:
    def __init__(self):
        self.errors   = []
        self.desktop  = get_desktop()
        self.shortcut = self.desktop / "Pokemon Card Bot.bat"

    def run(self):
        print("=" * 55)
        print(f"  {APP_NAME} v{APP_VERSION} — Uninstaller")
        print("=" * 55)
        print()

        if not INSTALL_DIR.exists():
            print(f"  Nothing to remove — {INSTALL_DIR} does not exist.")
            print()
            input("Press Enter to exit...")
            sys.exit(0)

        print(f"  Install directory : {INSTALL_DIR}")
        print(f"  Desktop shortcut  : {self.shortcut}")
        print()

        keep_config = self._ask_keep_config()
        print()

        confirm = input("  Are you sure you want to uninstall? (y/n): ").strip().lower()
        if confirm != "y":
            print()
            print("  Uninstall cancelled.")
            print()
            input("Press Enter to exit...")
            sys.exit(0)

        print()

        steps = [
            ("Removing desktop shortcut", self._remove_shortcut),
            ("Removing Start Menu entry", self._remove_start_menu),
        ]

        if keep_config:
            steps.append(("Removing bot files (keeping user config)", self._remove_files_keep_config))
        else:
            steps.append(("Removing install directory", self._remove_install_dir))

        for label, fn in steps:
            self._step(label, fn)

        print()
        if self.errors:
            print("  Completed with warnings:")
            for e in self.errors:
                print(f"   • {e}")
        else:
            print("  Uninstall complete!")

        if keep_config and INSTALL_DIR.exists():
            print()
            print(f"  Your config was kept at: {INSTALL_DIR / '.env'}")

        print()
        input("Press Enter to exit...")

    # ── PROMPTS ──────────────────────────────────────────────────────────────

    def _ask_keep_config(self) -> bool:
        """Ask whether to preserve the .env config file."""
        env_file = INSTALL_DIR / ".env"
        if not env_file.exists():
            return False
        print("  A .env config file with your settings was found.")
        answer = input("  Keep your config file? (y/n): ").strip().lower()
        return answer == "y"

    # ── STEPS ────────────────────────────────────────────────────────────────

    def _remove_shortcut(self):
        if self.shortcut.exists():
            self.shortcut.unlink()
            print(f"   Removed {self.shortcut}")
        else:
            print("   Desktop shortcut not found — skipping.")

    def _remove_start_menu(self):
        start_menu = (
            Path(os.environ.get("APPDATA", ""))
            / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Pokemon Card Bot"
        )
        if start_menu.exists():
            shutil.rmtree(start_menu, ignore_errors=True)
            print(f"   Removed {start_menu}")
        else:
            print("   Start Menu entry not found — skipping.")

    def _remove_install_dir(self):
        if INSTALL_DIR.exists():
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)
            if INSTALL_DIR.exists():
                raise RuntimeError(
                    f"Could not fully remove {INSTALL_DIR}. "
                    "Close any open files or terminals using it and try again."
                )
            print(f"   Removed {INSTALL_DIR}")
        else:
            print("   Install directory not found — skipping.")

    def _remove_files_keep_config(self):
        """Remove everything except .env."""
        if not INSTALL_DIR.exists():
            print("   Install directory not found — skipping.")
            return

        kept = []
        removed_count = 0

        for item in list(INSTALL_DIR.iterdir()):
            if item.name == ".env":
                kept.append(item.name)
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink()
                removed_count += 1
            except Exception as e:
                self.errors.append(f"Could not remove {item.name}: {e}")

        print(f"   Removed {removed_count} items, kept: {', '.join(kept)}")

    # ── HELPERS ──────────────────────────────────────────────────────────────

    def _step(self, label: str, fn):
        print(f"  Running: {label}...")
        try:
            fn()
        except Exception as e:
            print(f"   Failed: {e}")
            self.errors.append(f"{label}: {e}")


if __name__ == "__main__":
    Uninstaller().run()
