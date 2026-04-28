"""
Reads session cookies directly from the Edge browser's SQLite cookie database.
This lets the bot inherit the user's real authenticated session without
ever touching a login page, completely bypassing PerimeterX.
"""

import os
import json
import shutil
import sqlite3
import socket
import subprocess
import time
import base64
import ctypes
import ctypes.wintypes
import urllib.request
from pathlib import Path

_EDGE_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
_LOCAL_STATE    = _EDGE_USER_DATA / "Local State"
_TMP_COOKIES    = Path(os.environ.get("TEMP", "")) / "_pkb_cookies_tmp.db"


class CookieExtractionError(Exception):
    """Raised with a human-readable explanation of why extraction failed."""


def _is_profile_dir(p: Path) -> bool:
    """A real Edge profile directory contains a Preferences file."""
    return p.is_dir() and (p / "Preferences").exists()


def _find_cookies_db_for_domain(domain: str) -> Path:
    """
    Find the Edge cookies DB belonging to the profile that actually contains
    cookies for the given domain. Falls back to largest DB if none match.
    """
    if not _EDGE_USER_DATA.exists():
        raise CookieExtractionError(
            "Edge user data folder not found. "
            "Make sure Microsoft Edge is installed and has been opened at least once."
        )

    candidates = []
    for profile_dir in _EDGE_USER_DATA.iterdir():
        if not _is_profile_dir(profile_dir):
            continue
        db = profile_dir / "Network" / "Cookies"
        if db.exists():
            candidates.append(db)

    if not candidates:
        raise CookieExtractionError(
            "No Edge profiles with a cookie database were found. "
            "Open Edge, sign in, then close it and try again."
        )

    pattern = f"%{domain.lstrip('.')}"
    best = None
    best_count = -1
    for db in candidates:
        try:
            tmp = Path(str(_TMP_COOKIES) + f".scan_{db.parent.parent.name}")
            shutil.copy2(db, tmp)
            try:
                conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
                count = conn.execute(
                    "SELECT COUNT(*) FROM cookies WHERE host_key LIKE ?",
                    (pattern,),
                ).fetchone()[0]
                conn.close()
            finally:
                try: tmp.unlink()
                except Exception: pass
            if count > best_count:
                best_count = count
                best = db
        except Exception:
            continue

    if best is None:
        best = max(candidates, key=lambda p: p.stat().st_size)
    return best


class _DATABLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_decrypt(data: bytes) -> bytes:
    """Decrypt DPAPI-encrypted bytes using the Windows CryptUnprotectData API."""
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in  = _DATABLOB(len(data), buf)
    blob_out = _DATABLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise RuntimeError("DPAPI decryption failed")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


def _load_local_state() -> dict:
    if not _LOCAL_STATE.exists():
        raise CookieExtractionError("Edge Local State file not found. Is Microsoft Edge installed?")
    with open(_LOCAL_STATE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_aes_key(state: dict) -> bytes:
    """Return the AES-256 master key used to encrypt v10/v11 cookie values."""
    enc_key_b64 = state.get("os_crypt", {}).get("encrypted_key", "")
    if not enc_key_b64:
        raise CookieExtractionError("Could not find encrypted_key in Edge Local State.")
    enc_key = base64.b64decode(enc_key_b64)
    return _dpapi_decrypt(enc_key[5:])  # skip "DPAPI" prefix


def _get_app_bound_key(state: dict):
    """
    Return the AES-256 key used for v20 (app-bound) cookies, or None if it
    can't be obtained without elevation.

    The app-bound key is stored as base64("APPB" + DPAPI_SYSTEM(DPAPI_USER(key))).
    Decrypting the SYSTEM layer requires running as SYSTEM (or via Edge's
    IElevator COM service). We attempt user-DPAPI only — works on some
    configurations, otherwise returns None.
    """
    enc_b64 = state.get("os_crypt", {}).get("app_bound_encrypted_key", "")
    if not enc_b64:
        return None
    try:
        blob = base64.b64decode(enc_b64)
        if blob[:4] != b"APPB":
            return None
        inner = blob[4:]
        try:
            once = _dpapi_decrypt(inner)
        except Exception:
            return None
        try:
            twice = _dpapi_decrypt(once)
            candidate = twice
        except Exception:
            candidate = once
        if len(candidate) == 32:
            return candidate
        if len(candidate) >= 33:
            return candidate[-32:]
        return None
    except Exception:
        return None


def _decrypt_v10(enc_value: bytes, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce      = enc_value[3:15]
    ciphertext = enc_value[15:]
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")


def _decrypt_v20(enc_value: bytes, key: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce      = enc_value[3:15]
    ciphertext = enc_value[15:]
    plaintext  = AESGCM(key).decrypt(nonce, ciphertext, None)
    # v20 plaintext is prefixed with 32 bytes of metadata before the actual value
    if len(plaintext) > 32:
        return plaintext[32:].decode("utf-8", errors="replace")
    return plaintext.decode("utf-8", errors="replace")


def extract_cookies(domains: list) -> list:
    """
    Extract cookies for the given domain(s) from Edge's cookie database.

    Returns a list of dicts compatible with Playwright's context.add_cookies().
    Edge must be CLOSED before calling this (SQLite WAL lock).
    """
    if not _EDGE_USER_DATA.exists():
        raise CookieExtractionError(
            "Edge cookie database not found. "
            "Make sure Edge is installed and has been opened at least once."
        )

    primary_domain = next((d for d in domains if d), "")
    cookies_db = _find_cookies_db_for_domain(primary_domain)
    state      = _load_local_state()
    aes_key    = _get_aes_key(state)
    abe_key    = _get_app_bound_key(state)

    shutil.copy2(cookies_db, _TMP_COOKIES)
    for ext in ("-wal", "-shm"):
        src = Path(str(cookies_db) + ext)
        if src.exists():
            shutil.copy2(src, Path(str(_TMP_COOKIES) + ext))

    cookies = []
    total_rows      = 0
    fail_v20_no_key = 0
    fail_v20        = 0
    fail_v10        = 0
    fail_other      = 0

    try:
        try:
            conn = sqlite3.connect(f"file:{_TMP_COOKIES}?mode=ro", uri=True)
        except sqlite3.OperationalError as e:
            raise CookieExtractionError(
                "Could not open Edge's cookie database — Edge is probably still running. "
                "Close all msedge.exe processes (check Task Manager) and try again."
            ) from e

        conn.row_factory = sqlite3.Row
        conditions = " OR ".join("host_key LIKE ?" for _ in domains)
        patterns   = [f"%{d.lstrip('.')}" for d in domains]
        rows = conn.execute(
            f"SELECT host_key, name, encrypted_value, path, expires_utc, "
            f"is_secure, is_httponly FROM cookies "
            f"WHERE {conditions}",
            patterns,
        ).fetchall()
        conn.close()

        total_rows = len(rows)

        for row in rows:
            enc = bytes(row["encrypted_value"])
            prefix = enc[:3]
            try:
                if prefix in (b"v10", b"v11"):
                    value = _decrypt_v10(enc, aes_key)
                elif prefix == b"v20":
                    if abe_key is None:
                        fail_v20_no_key += 1
                        continue
                    value = _decrypt_v20(enc, abe_key)
                else:
                    value = _dpapi_decrypt(enc).decode("utf-8")
            except Exception:
                if prefix == b"v20":
                    fail_v20 += 1
                elif prefix in (b"v10", b"v11"):
                    fail_v10 += 1
                else:
                    fail_other += 1
                continue

            domain = row["host_key"]
            if not domain.startswith("."):
                domain = "." + domain

            expires_utc = row["expires_utc"]
            if expires_utc and expires_utc > 0:
                expires = (expires_utc / 1_000_000) - 11_644_473_600
            else:
                expires = -1

            cookies.append({
                "name":     row["name"],
                "value":    value,
                "domain":   domain,
                "path":     row["path"] or "/",
                "secure":   bool(row["is_secure"]),
                "httpOnly": bool(row["is_httponly"]),
                "expires":  expires,
            })
    finally:
        for f in [_TMP_COOKIES,
                  Path(str(_TMP_COOKIES) + "-wal"),
                  Path(str(_TMP_COOKIES) + "-shm")]:
            try: f.unlink()
            except Exception: pass

    if total_rows > 0 and not cookies:
        if fail_v20_no_key > 0:
            # Fall back to launching Edge with CDP and asking it for cookies.
            try:
                cdp_cookies = _extract_cookies_via_cdp(domains, cookies_db.parent.parent)
            except Exception as cdp_err:
                raise CookieExtractionError(
                    f"Found {total_rows} cookies but they use App-Bound "
                    f"Encryption (v20). The CDP fallback also failed:\n"
                    f"  {cdp_err}\n\n"
                    f"Try: close Edge completely (check Task Manager for "
                    f"msedge.exe), then retry import."
                ) from cdp_err
            if cdp_cookies:
                return cdp_cookies
            raise CookieExtractionError(
                f"Found {total_rows} encrypted cookies but Edge returned none "
                f"via CDP. Sign into Target in Edge again, close Edge, retry."
            )
        if fail_v20 > 0 or fail_v10 > 0:
            raise CookieExtractionError(
                f"Found {total_rows} cookies but decryption failed "
                f"(v10/v11 fails: {fail_v10}, v20 fails: {fail_v20}, "
                f"other fails: {fail_other}).\n"
                f"Sign out and back into Edge, then retry."
            )

    return cookies


# ---------------------------------------------------------------------------
# CDP fallback: when v20 cookies can't be decrypted (App-Bound Encryption),
# launch Edge headless against the real profile and ask Edge itself for the
# cookies via the DevTools Protocol. Edge handles its own decryption.
# ---------------------------------------------------------------------------

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _find_edge_exe() -> str:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    raise CookieExtractionError("msedge.exe not found in standard install paths.")


def _extract_cookies_via_cdp(domains: list, profile_dir: Path) -> list:
    """
    Launch Edge headlessly with the user's real profile + a remote debugging
    port, then use Playwright's CDP client to read decrypted cookies.

    `profile_dir` is the profile directory (e.g. .../User Data/Default), so its
    parent is the user-data-dir and its name is the profile name.
    """
    edge_exe       = _find_edge_exe()
    user_data_dir  = profile_dir.parent
    profile_name   = profile_dir.name
    port           = _free_port()

    # Use a temp data root with a copy of the profile so we don't fight with
    # an open Edge instance and don't disturb the user's real profile state.
    # However, cookies live INSIDE the profile, so we must copy them in.
    proc = subprocess.Popen(
        [
            edge_exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile_name}",
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-gpu",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    try:
        # Wait for CDP endpoint
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise CookieExtractionError(
                "Edge did not start on the debug port. "
                "Close all Edge windows (and msedge.exe in Task Manager) and retry."
            )

        from playwright.sync_api import sync_playwright
        urls = []
        for d in domains:
            d = d.lstrip(".")
            urls.append(f"https://{d}")
            urls.append(f"https://www.{d}")

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            try:
                if not browser.contexts:
                    return []
                ctx = browser.contexts[0]
                raw = ctx.cookies(urls)
            finally:
                try: browser.close()
                except Exception: pass

        # Playwright cookies are already in the right shape — just normalize.
        out = []
        for c in raw:
            domain = c.get("domain", "")
            if not domain.startswith("."):
                domain = "." + domain
            out.append({
                "name":     c.get("name", ""),
                "value":    c.get("value", ""),
                "domain":   domain,
                "path":     c.get("path", "/") or "/",
                "secure":   bool(c.get("secure", False)),
                "httpOnly": bool(c.get("httpOnly", False)),
                "expires":  c.get("expires", -1),
            })
        return out
    finally:
        try: proc.terminate()
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception:
            try: proc.kill()
            except Exception: pass
