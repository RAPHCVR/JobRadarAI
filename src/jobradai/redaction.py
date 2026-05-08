from __future__ import annotations

import os
import re
import urllib.parse


SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "app_key",
    "app_id",
    "client_secret",
    "client_id",
    "key",
    "token",
    "access_token",
    "refresh_token",
    "secret",
}


def redact_sensitive(value: str) -> str:
    redacted = value
    for key, secret in os.environ.items():
        upper = key.upper()
        if not secret or len(secret) < 8:
            continue
        if any(marker in upper for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-[REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        redacted,
    )
    return redacted


def redact_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return redact_sensitive(url)

    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    clean_query = urllib.parse.urlencode(
        [
            (key, "[REDACTED]" if key.lower() in SENSITIVE_QUERY_KEYS else value)
            for key, value in query_pairs
        ],
        doseq=True,
    )
    path = _redact_sensitive_path(parsed.netloc, parsed.path)
    rebuilt = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, clean_query, parsed.fragment))
    return redact_sensitive(rebuilt)


def _redact_sensitive_path(host: str, path: str) -> str:
    parts = path.split("/")
    lower_host = host.lower()
    for index, part in enumerate(parts):
        if not part:
            continue
        previous = parts[index - 1].lower() if index > 0 else ""
        if lower_host.endswith("jooble.org") and previous == "api":
            parts[index] = "[REDACTED]"
            continue
        if re.fullmatch(r"sk-[A-Za-z0-9_-]{12,}", part):
            parts[index] = "sk-[REDACTED]"
            continue
        if previous in {"token", "apikey", "api-key", "secret"} and len(part) >= 8:
            parts[index] = "[REDACTED]"
    return "/".join(parts)
