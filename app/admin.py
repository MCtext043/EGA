"""Password hashing and signed, short-lived admin sessions."""

import hashlib
import hmac
import secrets
import time


ITERATIONS = 310_000
SESSION_SECONDS = 8 * 60 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected = stored.split("$", 3)
        iterations = int(iterations_text)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= iterations <= 1_000_000:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def make_session(secret: str) -> str:
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def valid_session(token: str | None, secret: str) -> bool:
    if not token or not secret:
        return False
    try:
        timestamp_text, signature = token.split(".", 1)
        timestamp = int(timestamp_text)
        age = time.time() - timestamp
        if age < -60 or age > SESSION_SECONDS:
            return False
        expected = hmac.new(secret.encode(), timestamp_text.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False
