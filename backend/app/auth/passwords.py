import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 10
    require_letter: bool = True
    require_digit: bool = True
    require_special: bool = True


DEFAULT_POLICY = PasswordPolicy()
HASH_NAME = "sha256"
PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16


def validate_password(password: str, policy: PasswordPolicy = DEFAULT_POLICY) -> None:
    if len(password) < policy.min_length:
        raise ValueError(f"password must be at least {policy.min_length} characters")
    if policy.require_letter and not any(ch.isalpha() for ch in password):
        raise ValueError("password must include a letter")
    if policy.require_digit and not any(ch.isdigit() for ch in password):
        raise ValueError("password must include a number")
    if policy.require_special and not any(not ch.isalnum() for ch in password):
        raise ValueError("password must include a special character")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        HASH_NAME, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    encoded_salt = base64.b64encode(salt).decode("ascii")
    encoded_hash = base64.b64encode(dk).decode("ascii")
    return f"pbkdf2_{HASH_NAME}${PBKDF2_ITERATIONS}${encoded_salt}${encoded_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, encoded_salt, encoded_hash = stored_hash.split("$", 3)
    except ValueError:
        return False
    if not scheme.startswith("pbkdf2_"):
        return False
    try:
        iterations_int = int(iterations)
        salt = base64.b64decode(encoded_salt.encode("ascii"))
        expected_hash = base64.b64decode(encoded_hash.encode("ascii"))
    except (ValueError, base64.binascii.Error):
        return False
    candidate = hashlib.pbkdf2_hmac(
        HASH_NAME, password.encode("utf-8"), salt, iterations_int
    )
    return hmac.compare_digest(candidate, expected_hash)
