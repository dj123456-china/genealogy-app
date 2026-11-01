import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, status

from app.core.config import settings


PBKDF2_ITERATIONS = 310_000
REGISTRATION_TOKEN_TTL_SECONDS = 10 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "jti": secrets.token_urlsafe(24),
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.access_token_expire_minutes * 60,
    }
    header = _encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _encode(json.dumps(payload, separators=(",", ":")).encode())
    message = f"{header}.{body}".encode("ascii")
    signature = _encode(hmac.new(settings.secret_key.encode(), message, hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def decode_access_token(token: str) -> dict:
    try:
        if len(token) > 4096:
            raise ValueError
        header, body, signature = token.split(".")
        message = f"{header}.{body}".encode("ascii")
        expected = _encode(hmac.new(settings.secret_key.encode(), message, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        token_header = json.loads(_decode(header))
        if token_header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError
        payload = json.loads(_decode(body))
        if not isinstance(payload, dict) or not (int(time.time()) < int(payload["exp"]) <= 253402300799) or not (1 <= int(payload["sub"]) <= 2147483647):
            raise ValueError
        return payload
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")


def create_registration_token(phone: str, verification_id: int) -> str:
    """Create a short-lived proof that a phone SMS was verified for registration.

    This is deliberately separate from the access token.  It contains only the
    verified phone and the local SMS record id, and expires quickly.  The
    registration route consumes the referenced record, making the proof
    single-use even if the client retries the request.
    """

    payload = {
        "purpose": "phone_registration",
        "phone": phone,
        "verification_id": str(verification_id),
        "exp": int(time.time()) + REGISTRATION_TOKEN_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(8),
    }
    body = _encode(json.dumps(payload, separators=(",", ":")).encode())
    message = f"reg.{body}".encode("ascii")
    signature = _encode(hmac.new(settings.secret_key.encode(), message, hashlib.sha256).digest())
    return f"reg.{body}.{signature}"


def decode_registration_token(token: str) -> dict:
    """Decode and validate a phone registration proof.

    ``ValueError`` is intentionally raised for all malformed, expired, or
    wrongly signed values so callers can return a normal validation error.
    """

    try:
        prefix, body, signature = token.split(".", 2)
        if prefix != "reg":
            raise ValueError
        message = f"reg.{body}".encode("ascii")
        expected = _encode(hmac.new(settings.secret_key.encode(), message, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(_decode(body))
        if not isinstance(payload, dict) or payload.get("purpose") != "phone_registration":
            raise ValueError
        if int(payload["exp"]) < int(time.time()):
            raise ValueError
        if not payload.get("phone") or not payload.get("verification_id"):
            raise ValueError
        return payload
    except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError("注册凭证无效或已过期")


def token_fingerprint(token: str) -> str:
    """数据库只保存令牌的 SHA-256 指纹。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
