"""Password hashes with scrypt from the standard library. A hash takes about 50 ms:
call these through `asyncio.to_thread`, never inside a `db.write` function."""

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${key.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt, _, key = stored.partition("$")
    try:
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    except ValueError:
        return False
    return hmac.compare_digest(got.hex(), key)
