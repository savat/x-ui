"""Password hashing, input validation and log redaction."""
import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid

try:
    from argon2 import PasswordHasher
    _ph = PasswordHasher()
except Exception:  # pragma: no cover - fallback only if argon2-cffi is missing
    _ph = None

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
RESERVED = {"root", "admin", "administrator", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail",
            "news", "uucp", "proxy", "www-data", "backup", "list", "irc", "nobody", "sshd", "ubuntu",
            "debian", "systemd", "uvpn", "nginx", "postgres", "mysql"}
HOST_RE = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")


def hash_password(password):
    if _ph is not None:
        return _ph.hash(password)
    salt = os.urandom(16)  # scrypt fallback
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(stored, password):
    try:
        if stored.startswith("scrypt$"):
            _, s, d = stored.split("$")
            dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
            return hmac.compare_digest(dk, base64.b64decode(d))
        if _ph is None:
            return False
        return bool(_ph.verify(stored, password))
    except Exception:
        return False


def validate_username(name):
    if not isinstance(name, str) or not USERNAME_RE.match(name):
        raise ValueError("username must be 1-32 chars: a-z, 0-9, _ or -, starting with a letter")
    if name in RESERVED:
        raise ValueError("username is reserved")
    return name


def validate_password(pw, min_len=8):
    if not isinstance(pw, str) or len(pw) < min_len or len(pw) > 128:
        raise ValueError("password must be %d-128 characters" % min_len)
    if any(ord(c) < 32 or ord(c) == 127 for c in pw):
        raise ValueError("password contains control characters")
    return pw


def validate_host(host):
    if not isinstance(host, str) or not (HOST_RE.match(host) or re.match(r"^[0-9a-fA-F:.]+$", host)):
        raise ValueError("invalid host")
    return host


def gen_uuid():
    return str(uuid.uuid4())


def gen_secret(nbytes=16):
    return secrets.token_urlsafe(nbytes)


_REDACTIONS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\b(zivpn)://\S+", re.I), r"\1://[REDACTED]"),
    (re.compile(r"(?i)\b(pass(?:word)?|passwd|token|secret|auth|key)\b(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1\2[REDACTED]"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "[REDACTED UUID]"),
]


def redact(text):
    for rx, rep in _REDACTIONS:
        text = rx.sub(rep, text)
    return text
