from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from jobradai.redaction import redact_sensitive, redact_url


class HttpError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, timeout: int = 25, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        self.user_agent = "JobRadarAI/0.1 (+local personal job search)"

    def fetch_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> str:
        final_url = self._with_params(url, params)
        safe_final_url = redact_url(final_url)
        req_headers = {"User-Agent": self.user_agent, "Accept": "application/json,text/plain,*/*"}
        if headers:
            req_headers.update(headers)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = urllib.request.Request(final_url, data=body, method=method, headers=req_headers)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(charset, errors="replace")
            except urllib.error.HTTPError as exc:
                last_error = exc
                body = redact_sensitive(exc.read(800).decode("utf-8", errors="replace"))
                message = re.sub(r"\s+", " ", body).strip()
                raise HttpError(f"HTTP failure for {safe_final_url}: HTTP {exc.code} {message}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.7 * (attempt + 1))
                    continue
        raise HttpError(f"HTTP failure for {safe_final_url}: {redact_sensitive(str(last_error))}")

    def fetch_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Any:
        text = self.fetch_text(url=url, params=params, method=method, headers=headers, body=body)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise HttpError(f"Invalid JSON from {redact_url(url)}: {exc}") from exc

    @staticmethod
    def _with_params(url: str, params: dict[str, Any] | None) -> str:
        if not params:
            return url
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        if not clean:
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{urllib.parse.urlencode(clean, doseq=True)}"
