"""
Reads session cookies directly from the Edge browser's SQLite cookie database.
This lets the bot inherit the user's real authenticated session without
ever touching a login page, completely bypassing PerimeterX.
"""

import os
import json
import shutil
import sqlite3
import base64
import ctypes
import ctypes.wintypes
from pathlib import Path

_EDGE_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
_LOCAL_STATE    = _EDGE_USER_DATA / "Local State"
_TMP_COOKIES    = Path(os.environ.get("TEMP", "")) / "_pkb_cookies_tmp.db"


def _find_cookies_db() -> Path:
    """
    Find the Edge cookies DB for the profile that has the most cookies
    (handles non-Default profile names like 'Profile 1').
    """
    candidates = []
    for profile_dir in _EDGE_USER_DATA.iterdir():
        db = profile_dir / "Network" / "Cookies"
        if db.exists():
            candidates.append(db)
    if not candidates:
        raise FileNotFoundError(
            "Edge cookie database not found. "
            "Make sure Edge is installed and has been opened at least once."
        )
    # Prefer the profile with the most cookies (most likely the active one)
    return max(candidates, key=lambda p: p.stat().st_size)


_COOKIES_DB = _EDGE_USER_DATA / "Default" / "Network" / "Cookies"


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
        raise RuntimeError("DPAPI decryption failed — are you running as the correct user?")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


def _get_aes_key() -> bytes:
    """Return the AES-256 master key used to encrypt Edge cookie values."""
    if not _LOCAL_STATE.exists():
        raise FileNotFoundError("Edge Local State file not found. Is Microsoft Edge installed?")
    with open(_LOCAL_STATE, "r", encoding="utf-8") as f:
        state = json.load(f)
    enc_key_b64 = state.get("os_crypt", {}).get("encrypted_key", "")
    if not enc_key_b64:
        raise ValueError("Could not find encrypted_key in Edge Local State.")
    enc_key = base64.b64decode(enc_key_b64)
    # First 5 bytes are the literal string "DPAPI" — strip them
    return _dpapi_decrypt(enc_key[5:])


def _decrypt_cookie_value(enc_value: bytes, key: bytes) -> str:
    """Decrypt a single cookie value (AES-256-GCM or legacy DPAPI)."""
    if enc_value[:3] in (b"v10", b"v11"):
        # AES-256-GCM: [3 bytes version][12 bytes nonce][ciphertext+16 byte tag]
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce      = enc_value[3:15]
        ciphertext = enc_value[15:]
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
    else:
        # Legacy DPAPI-encrypted value (older Edge versions)
        return _dpapi_decrypt(enc_value).decode("utf-8")


def extract_cookies(domains: list) -> list:
    """
    Extract cookies for the given domain(s) from Edge's cookie database.

    Returns a list of dicts compatible with Playwright's context.add_cookies().
    Edge must be CLOSED before calling this (SQLite WAL lock).

    Example:
        cookies = extract_cookies([".target.com", "target.com"])
    """
    if not _EDGE_USER_DATA.exists():
        raise FileNotFoundError(
            "Edge cookie database not found. "
            "Make sure Edge is installed and has been opened at least once."
        )

    cookies_db = _find_cookies_db()
    key = _get_aes_key()

    # Copy the DB so we don't hold a lock on Edge's live file
    shutil.copy2(cookies_db, _TMP_COOKIES)
    # Also copy WAL/SHM files if present (needed for consistent reads)
    for ext in ("-wal", "-shm"):
        src = Path(str(cookies_db) + ext)
        if src.exists():
            shutil.copy2(src, Path(str(_TMP_COOKIES) + ext))

    cookies = []
    try:
        conn = sqlite3.connect(f"file:{_TMP_COOKIES}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Match any host that ends with one of the given domain strings
        # e.g. "target.com" matches ".target.com", "www.target.com", etc.
        conditions = " OR ".join("host_key LIKE ?" for _ in domains)
        patterns   = [f"%{d.lstrip('.')}" for d in domains]
        rows = conn.execute(
            f"SELECT host_key, name, encrypted_value, path, expires_utc, "
            f"is_secure, is_httponly FROM cookies "
            f"WHERE {conditions}",
            patterns,
        ).fetchall()
        conn.close()

        for row in rows:
            try:
                value = _decrypt_cookie_value(bytes(row["encrypted_value"]), key)
            except Exception:
                continue  # skip cookies we can't decrypt

            # Playwright wants domain with leading dot for host cookies
            domain = row["host_key"]
            if not domain.startswith("."):
                domain = "." + domain

            # Edge stores expiry as microseconds since Jan 1, 1601.
            # Convert to Unix timestamp (seconds since Jan 1, 1970).
            expires_utc = row["expires_utc"]
            if expires_utc and expires_utc > 0:
                # 11644473600 seconds between 1601-01-01 and 1970-01-01
                expires = (expires_utc / 1_000_000) - 11_644_473_600
            else:
                expires = -1  # session cookie

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
            try:
                f.unlink()
            except Exception:
                pass

    return cookies
