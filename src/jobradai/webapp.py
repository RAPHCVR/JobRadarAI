from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from jobradai.config import PROJECT_ROOT, load_config


APPLICATION_STATUSES = {
    "to_review",
    "interested",
    "applied",
    "follow_up",
    "interview",
    "offer",
    "rejected",
    "archived",
}
FIT_STATUSES = {"unknown", "strong", "ok", "stretch", "low", "blocked"}
USER_PRIORITIES = {"low", "normal", "high", "urgent"}
PATCHABLE_FIELDS = {
    "application_status",
    "fit_status",
    "user_priority",
    "notes",
    "next_action_at",
    "contact_name",
    "contact_url",
    "application_url",
    "custom_cv",
    "last_contacted_at",
}
SESSION_COOKIE = "jobradar_session"
DEFAULT_LOGIN_ATTEMPTS = 8
DEFAULT_LOGIN_WINDOW_SECONDS = 10 * 60


@dataclass(frozen=True)
class WebAuth:
    password: str
    session_secret: str
    cookie_secure: bool = True
    session_days: int = 7
    api_token: str = ""

    @classmethod
    def from_env(cls) -> "WebAuth | None":
        if os.environ.get("JOBRADAR_WEB_AUTH", "on").lower() in {"0", "off", "false", "no"}:
            return None
        password = os.environ.get("JOBRADAR_WEB_PASSWORD", "")
        session_secret = os.environ.get("JOBRADAR_WEB_SESSION_SECRET", "")
        if not password or not session_secret:
            raise RuntimeError(
                "JOBRADAR_WEB_PASSWORD et JOBRADAR_WEB_SESSION_SECRET sont requis "
                "quand JOBRADAR_WEB_AUTH n'est pas desactive."
            )
        if len(session_secret) < 32:
            raise RuntimeError("JOBRADAR_WEB_SESSION_SECRET doit contenir au moins 32 caracteres.")
        secure = os.environ.get("JOBRADAR_WEB_COOKIE_SECURE", "true").lower() not in {"0", "off", "false", "no"}
        days = int(os.environ.get("JOBRADAR_WEB_SESSION_DAYS", "7"))
        return cls(
            password=password,
            session_secret=session_secret,
            cookie_secure=secure,
            session_days=max(1, min(days, 30)),
            api_token=os.environ.get("JOBRADAR_WEB_API_TOKEN", ""),
        )

    def check_password(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate, self.password)

    def issue_cookie(self) -> str:
        expires_at = int((datetime.now(timezone.utc) + timedelta(days=self.session_days)).timestamp())
        payload = f"{expires_at}.{secrets.token_urlsafe(24)}"
        token = _b64(payload.encode("utf-8")) + "." + self._sign(payload)
        max_age = self.session_days * 24 * 60 * 60
        parts = [
            f"{SESSION_COOKIE}={token}",
            "Path=/",
            f"Max-Age={max_age}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    def clear_cookie(self) -> str:
        parts = [
            f"{SESSION_COOKIE}=",
            "Path=/",
            "Max-Age=0",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self.cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    def validate_cookie(self, token: str) -> bool:
        try:
            encoded_payload, signature = token.split(".", 1)
            payload = _unb64(encoded_payload).decode("utf-8")
            expires_raw, _nonce = payload.split(".", 1)
            expires_at = int(expires_raw)
        except (ValueError, UnicodeDecodeError):
            return False
        if expires_at < int(datetime.now(timezone.utc).timestamp()):
            return False
        return hmac.compare_digest(signature, self._sign(payload))

    def validate_api_token(self, token: str) -> bool:
        return bool(self.api_token) and hmac.compare_digest(token, self.api_token)

    def _sign(self, payload: str) -> str:
        digest = hmac.new(self.session_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
        return _b64(digest)


class LoginRateLimiter:
    def __init__(self, *, max_attempts: int = DEFAULT_LOGIN_ATTEMPTS, window_seconds: int = DEFAULT_LOGIN_WINDOW_SECONDS) -> None:
        self.max_attempts = max(1, max_attempts)
        self.window_seconds = max(60, window_seconds)
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "LoginRateLimiter":
        max_attempts = _int_env("JOBRADAR_WEB_LOGIN_MAX_ATTEMPTS", DEFAULT_LOGIN_ATTEMPTS)
        window_seconds = _int_env("JOBRADAR_WEB_LOGIN_WINDOW_SECONDS", DEFAULT_LOGIN_WINDOW_SECONDS)
        return cls(max_attempts=max_attempts, window_seconds=window_seconds)

    def blocked(self, key: str) -> bool:
        with self._lock:
            failures = self._fresh_failures(key)
            return len(failures) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            failures = self._fresh_failures(key)
            failures.append(time.monotonic())
            self._failures[key] = failures

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def _fresh_failures(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self.window_seconds
        failures = [value for value in self._failures.get(key, []) if value >= cutoff]
        self._failures[key] = failures
        return failures


class WebDataStore:
    def __init__(self, *, root: Path, output_dir: Path | None = None, state_path: Path | None = None) -> None:
        self.root = root.resolve()
        config = load_config(self.root, load_env=False)
        self.output_dir = (output_dir or config.output_dir).resolve()
        self.state_path = (state_path or (self.root / "runs" / "state" / "application_state.json")).resolve()
        self._lock = threading.Lock()

    def summary(self) -> dict[str, Any]:
        queue = self._queue_payload()
        jobs = self.jobs()
        audit = self._read_json(self.output_dir / "audit.json", {})
        link_checks = self._read_json(self.output_dir / "link_checks.json", {})
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_name": queue.get("run_name", ""),
            "current_jobs": queue.get("current_jobs", audit.get("total_jobs", 0)),
            "known_jobs": queue.get("known_jobs", 0),
            "new_jobs": queue.get("new_jobs", 0),
            "missing_this_run": queue.get("missing_this_run", 0),
            "queue_count": len(jobs),
            "vie_queue_count": int(queue.get("vie_queue_count", 0) or 0),
            "queue_status_counts": dict(Counter(str(job.get("presence_status") or "unknown") for job in jobs)),
            "queue_bucket_counts": dict(Counter(str(job.get("queue_bucket") or "unknown") for job in jobs)),
            "application_status_counts": dict(Counter(str(job.get("application_status") or "to_review") for job in jobs)),
            "link_status_counts": dict(Counter(str(job.get("last_link_status") or "not_checked") for job in jobs)),
            "market_counts": dict(Counter(str(job.get("market") or "unknown") for job in jobs)),
            "audit": {
                "sources_ok": (audit.get("source_status") or {}).get("ok", 0) if isinstance(audit, dict) else 0,
                "sources_skipped": (audit.get("source_status") or {}).get("skipped", 0) if isinstance(audit, dict) else 0,
                "source_errors": len((audit.get("source_status") or {}).get("errors", [])) if isinstance(audit, dict) else 0,
                "llm_count": (audit.get("llm_shortlist") or {}).get("count", 0) if isinstance(audit, dict) else 0,
                "link_checked_count": (audit.get("link_checks") or {}).get("checked_count", 0) if isinstance(audit, dict) else 0,
            },
            "cv": self.cv_metadata(),
            "links": {
                "dashboard": "/api/file/dashboard.html",
                "queue_markdown": "/api/file/application_queue.md",
                "vie_queue_markdown": "/api/file/vie_priority_queue.md",
                "messages_markdown": "/api/file/application_messages.md",
                "audit_markdown": "/api/file/audit.md",
                "link_checks_markdown": "/api/file/link_checks.md",
            },
            "link_checks_generated_at": link_checks.get("generated_at", "") if isinstance(link_checks, dict) else "",
        }

    def jobs(self, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
        queue = self._queue_payload()
        messages = self._messages_by_id()
        state = self._state_payload()
        items = queue.get("items", []) if isinstance(queue, dict) else []
        jobs = [
            self._merge_job(item, state.get("items", {}).get(str(item.get("stable_id")), {}), messages)
            for item in items
            if isinstance(item, dict)
        ]
        return filter_jobs(jobs, filters or {})

    def job(self, stable_id: str) -> dict[str, Any] | None:
        for job in self.jobs():
            if str(job.get("stable_id")) == stable_id:
                return job
        return None

    def patch_state(self, stable_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        clean = validate_state_patch(patch)
        with self._lock:
            state = self._state_payload()
            items = state.setdefault("items", {})
            current = items.setdefault(stable_id, {"events": []})
            current.update(clean)
            current["updated_at"] = datetime.now(timezone.utc).isoformat()
            state["updated_at"] = current["updated_at"]
            self._write_state(state)
            return current

    def add_event(self, stable_id: str, event: dict[str, Any]) -> dict[str, Any]:
        event_type = str(event.get("type") or "note").strip()[:80] or "note"
        note = str(event.get("note") or "").strip()[:5000]
        when = str(event.get("at") or datetime.now(timezone.utc).isoformat())[:200]
        entry = {"type": event_type, "note": note, "at": when}
        with self._lock:
            state = self._state_payload()
            items = state.setdefault("items", {})
            current = items.setdefault(stable_id, {"events": []})
            events = current.setdefault("events", [])
            if not isinstance(events, list):
                events = []
                current["events"] = events
            events.append(entry)
            current["updated_at"] = datetime.now(timezone.utc).isoformat()
            state["updated_at"] = current["updated_at"]
            self._write_state(state)
            return entry

    def cv_metadata(self) -> dict[str, Any]:
        pdf = self._cv_pdf()
        tex = self._cv_tex()
        data: dict[str, Any] = {
            "pdf_available": bool(pdf and pdf.exists()),
            "pdf_url": "/api/cv.pdf" if pdf and pdf.exists() else "",
            "tex_available": bool(tex and tex.exists()),
            "tex_url": "/api/cv.tex" if tex and tex.exists() else "",
        }
        if pdf and pdf.exists():
            data["pdf_updated_at"] = datetime.fromtimestamp(pdf.stat().st_mtime, timezone.utc).isoformat()
        if tex and tex.exists():
            text = tex.read_text(encoding="utf-8", errors="replace")
            data["tex_updated_at"] = datetime.fromtimestamp(tex.stat().st_mtime, timezone.utc).isoformat()
            data["tex_excerpt"] = "\n".join(text.splitlines()[:60])
        return data

    def cv_pdf_path(self) -> Path | None:
        pdf = self._cv_pdf()
        return pdf if pdf and pdf.exists() else None

    def cv_tex_path(self) -> Path | None:
        tex = self._cv_tex()
        return tex if tex and tex.exists() else None

    def output_file(self, name: str) -> Path | None:
        allowed = {
            "application_queue.md",
            "vie_priority_queue.md",
            "application_messages.md",
            "dashboard.html",
            "llm_shortlist.md",
            "link_checks.md",
            "graduate_programs.md",
            "audit.md",
            "report.md",
        }
        if name not in allowed:
            return None
        path = (self.output_dir / name).resolve()
        if self.output_dir not in path.parents and path != self.output_dir:
            return None
        return path if path.exists() else None

    def _queue_payload(self) -> dict[str, Any]:
        return self._read_json(self.output_dir / "application_queue.json", {})

    def _messages_by_id(self) -> dict[str, dict[str, Any]]:
        payload = self._read_json(self.output_dir / "application_messages.json", {})
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return {
            str(item.get("stable_id")): item
            for item in items
            if isinstance(item, dict) and item.get("stable_id")
        }

    def _state_payload(self) -> dict[str, Any]:
        payload = self._read_json(self.state_path, {})
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("version", 1)
        payload.setdefault("items", {})
        if not isinstance(payload["items"], dict):
            payload["items"] = {}
        return payload

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def _merge_job(
        self,
        item: dict[str, Any],
        state: dict[str, Any],
        messages: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        stable_id = str(item.get("stable_id") or "")
        merged = dict(item)
        message = messages.get(stable_id, {})
        merged["recruiter_message"] = message.get("message") or item.get("last_recruiter_message") or ""
        merged["application_status"] = state.get("application_status") or "to_review"
        merged["fit_status"] = state.get("fit_status") or "unknown"
        merged["user_priority"] = state.get("user_priority") or "normal"
        merged["notes"] = state.get("notes") or ""
        merged["next_action_at"] = state.get("next_action_at") or ""
        merged["contact_name"] = state.get("contact_name") or ""
        merged["contact_url"] = state.get("contact_url") or ""
        merged["application_url"] = state.get("application_url") or item.get("url") or ""
        merged["custom_cv"] = state.get("custom_cv") or ""
        merged["last_contacted_at"] = state.get("last_contacted_at") or ""
        events = state.get("events") if isinstance(state.get("events"), list) else []
        merged["events"] = events
        merged["state_updated_at"] = state.get("updated_at") or ""
        return merged

    def _cv_pdf(self) -> Path | None:
        candidates = [
            self.root / "runs" / "cv" / "main.pdf",
            self.root / "private" / "main.pdf",
            self.root / "private" / "cv.pdf",
            self.output_dir / "cv.pdf",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def _cv_tex(self) -> Path | None:
        candidates = [
            self.root / "runs" / "cv" / "main.tex",
            self.root / "private" / "main.tex",
            self.output_dir / "cv.tex",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default


def filter_jobs(jobs: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    q = filters.get("q", "").strip().lower()
    bucket = filters.get("bucket", "").strip()
    app_status = filters.get("application_status", "").strip()
    link_status = filters.get("link_status", "").strip()
    market = filters.get("market", "").strip()
    level = filters.get("level", "").strip()
    active = filters.get("active", "").strip()
    if q:
        fields = (
            "title",
            "company",
            "market",
            "location",
            "source",
            "notes",
            "last_application_angle",
            "application_angle",
            "recruiter_message",
            "experience_evidence",
        )
        jobs = [job for job in jobs if any(q in str(job.get(field, "")).lower() for field in fields)]
    if bucket:
        jobs = [job for job in jobs if str(job.get("queue_bucket") or "") == bucket]
    if app_status:
        jobs = [job for job in jobs if str(job.get("application_status") or "") == app_status]
    if link_status:
        jobs = [job for job in jobs if str(job.get("last_link_status") or "") == link_status]
    if market:
        jobs = [job for job in jobs if str(job.get("market") or "") == market]
    if level:
        jobs = [job for job in jobs if str(job.get("last_level_fit") or "") == level]
    if active in {"1", "true", "yes"}:
        jobs = [job for job in jobs if str(job.get("presence_status") or "") == "active"]
    sort = filters.get("sort", "priority")
    if sort == "updated":
        jobs.sort(key=lambda job: str(job.get("state_updated_at") or ""), reverse=True)
    elif sort == "score":
        jobs.sort(key=lambda job: float(job.get("last_combined_score") or job.get("score") or 0), reverse=True)
    else:
        order = {"apply_now": 0, "shortlist": 1, "high_score": 2, "maybe": 3}
        jobs.sort(
            key=lambda job: (
                0 if str(job.get("presence_status") or "") == "active" else 1,
                order.get(str(job.get("queue_bucket") or ""), 9),
                -float(job.get("last_combined_score") or job.get("score") or 0),
            )
        )
    limit = filters.get("limit", "").strip()
    if limit:
        try:
            size = max(1, min(int(limit), 1000))
            jobs = jobs[:size]
        except ValueError:
            pass
    return jobs


def validate_state_patch(patch: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in PATCHABLE_FIELDS:
            continue
        text = "" if value is None else str(value).strip()
        if key == "application_status" and text and text not in APPLICATION_STATUSES:
            raise ValueError(f"application_status invalide: {text}")
        if key == "fit_status" and text and text not in FIT_STATUSES:
            raise ValueError(f"fit_status invalide: {text}")
        if key == "user_priority" and text and text not in USER_PRIORITIES:
            raise ValueError(f"user_priority invalide: {text}")
        if key in {"notes", "contact_url", "application_url"}:
            clean[key] = text[:5000]
        else:
            clean[key] = text[:500]
    return clean


def run_web_app(
    *,
    root: Path = PROJECT_ROOT,
    output_dir: Path | None = None,
    state_path: Path | None = None,
    static_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    auth: WebAuth | None = None,
) -> None:
    store = WebDataStore(root=root, output_dir=output_dir, state_path=state_path)
    static = (static_dir or (root / "web" / "dist")).resolve()
    auth_config = WebAuth.from_env() if auth is None else auth
    handler = make_handler(store=store, static_dir=static, auth=auth_config)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"web=http://{host}:{port}")
    print(f"static={static}")
    print(f"state={store.state_path}")
    print(f"auth={'on' if auth_config else 'off'}")
    server.serve_forever()


def make_handler(*, store: WebDataStore, static_dir: Path, auth: WebAuth | None):
    login_limiter = LoginRateLimiter.from_env() if auth is not None else None

    class JobRadarRequestHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            print(f"{self.address_string()} - {format % args}")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._json({"ok": True})
                return
            if parsed.path == "/api/session":
                self._json({"authenticated": self._authenticated()})
                return
            if parsed.path.startswith("/api/") and not self._authenticated():
                self._error(HTTPStatus.UNAUTHORIZED, "Authentification requise.")
                return
            if parsed.path == "/api/summary":
                self._json(store.summary())
                return
            if parsed.path == "/api/jobs":
                filters = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
                jobs = store.jobs(filters)
                self._json({"items": jobs, "count": len(jobs)})
                return
            if parsed.path.startswith("/api/jobs/"):
                stable_id = unquote(parsed.path.removeprefix("/api/jobs/")).strip("/")
                job = store.job(stable_id)
                if not job:
                    self._error(HTTPStatus.NOT_FOUND, "Offre introuvable.")
                    return
                self._json(job)
                return
            if parsed.path == "/api/cv":
                self._json(store.cv_metadata())
                return
            if parsed.path == "/api/cv.pdf":
                self._send_file(store.cv_pdf_path(), "application/pdf")
                return
            if parsed.path == "/api/cv.tex":
                self._send_file(store.cv_tex_path(), "text/plain; charset=utf-8")
                return
            if parsed.path.startswith("/api/file/"):
                name = unquote(parsed.path.removeprefix("/api/file/"))
                content_type = mimetypes.guess_type(name)[0] or "text/plain"
                if name.endswith(".md"):
                    content_type = "text/markdown; charset=utf-8"
                self._send_file(store.output_file(name), content_type)
                return
            self._serve_static(parsed.path)

        def do_PATCH(self) -> None:
            parsed = urlparse(self.path)
            if not self._origin_allowed():
                self._error(HTTPStatus.FORBIDDEN, "Origine non autorisee.")
                return
            if not self._authenticated():
                self._error(HTTPStatus.UNAUTHORIZED, "Authentification requise.")
                return
            if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/state"):
                stable_id = parsed.path.removeprefix("/api/jobs/").removesuffix("/state").strip("/")
                if not store.job(stable_id):
                    self._error(HTTPStatus.NOT_FOUND, "Offre introuvable.")
                    return
                try:
                    payload = self._read_body()
                    state = store.patch_state(stable_id, payload)
                except ValueError as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                self._json({"state": state, "job": store.job(stable_id)})
                return
            self._error(HTTPStatus.NOT_FOUND, "Route inconnue.")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if not self._origin_allowed():
                self._error(HTTPStatus.FORBIDDEN, "Origine non autorisee.")
                return
            if parsed.path == "/api/login":
                self._login()
                return
            if parsed.path == "/api/logout":
                self._logout()
                return
            if not self._authenticated():
                self._error(HTTPStatus.UNAUTHORIZED, "Authentification requise.")
                return
            if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/events"):
                stable_id = parsed.path.removeprefix("/api/jobs/").removesuffix("/events").strip("/")
                if not store.job(stable_id):
                    self._error(HTTPStatus.NOT_FOUND, "Offre introuvable.")
                    return
                try:
                    event = store.add_event(stable_id, self._read_body())
                except ValueError as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                self._json({"event": event, "job": store.job(stable_id)})
                return
            self._error(HTTPStatus.NOT_FOUND, "Route inconnue.")

        def _login(self) -> None:
            if auth is None:
                self._json({"authenticated": True})
                return
            login_key = self.client_address[0] if self.client_address else "unknown"
            if login_limiter and login_limiter.blocked(login_key):
                self._error(HTTPStatus.TOO_MANY_REQUESTS, "Trop de tentatives. Reessaie plus tard.")
                return
            try:
                payload = self._read_body()
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            password = str(payload.get("password") or "")
            if not auth.check_password(password):
                if login_limiter:
                    login_limiter.record_failure(login_key)
                self._error(HTTPStatus.UNAUTHORIZED, "Mot de passe invalide.")
                return
            if login_limiter:
                login_limiter.record_success(login_key)
            self._json({"authenticated": True}, extra_headers={"Set-Cookie": auth.issue_cookie()})

        def _logout(self) -> None:
            if auth is None:
                self._json({"authenticated": False})
                return
            self._json({"authenticated": False}, extra_headers={"Set-Cookie": auth.clear_cookie()})

        def _authenticated(self) -> bool:
            if auth is None:
                return True
            auth_header = self.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer ") and auth.validate_api_token(auth_header[7:].strip()):
                return True
            for part in self.headers.get("cookie", "").split(";"):
                name, sep, value = part.strip().partition("=")
                if sep and name == SESSION_COOKIE and auth.validate_cookie(value):
                    return True
            return False

        def _origin_allowed(self) -> bool:
            origin = self.headers.get("origin", "").strip()
            if not origin:
                return True
            host = (self.headers.get("x-forwarded-host") or self.headers.get("host") or "").split(",", 1)[0].strip()
            forwarded_proto = (self.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
            proto = forwarded_proto or ("https" if auth and auth.cookie_secure else "http")
            configured = os.environ.get("JOBRADAR_WEB_ALLOWED_ORIGINS", "")
            return origin_allowed(origin=origin, host=host, proto=proto, configured=configured)

        def _serve_static(self, route: str) -> None:
            if not static_dir.exists():
                self._error(HTTPStatus.NOT_FOUND, "Frontend non build. Lance `npm run build` dans web/.")
                return
            relative = route.lstrip("/") or "index.html"
            candidate = (static_dir / relative).resolve()
            if static_dir not in candidate.parents and candidate != static_dir:
                self._error(HTTPStatus.FORBIDDEN, "Chemin interdit.")
                return
            if not candidate.exists() or candidate.is_dir():
                candidate = static_dir / "index.html"
            self._send_file(candidate, mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("Payload JSON invalide.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Payload JSON objet attendu.")
            return payload

        def _send_file(self, path: Path | None, content_type: str) -> None:
            if not path or not path.exists() or not path.is_file():
                self._error(HTTPStatus.NOT_FOUND, "Fichier introuvable.")
                return
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(data)

        def _json(
            self,
            payload: dict[str, Any],
            status: HTTPStatus = HTTPStatus.OK,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._json({"error": message}, status=status)

        def _security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            if auth and auth.cookie_secure and os.environ.get("JOBRADAR_WEB_HSTS", "true").lower() not in {"0", "off", "false", "no"}:
                self.send_header("Strict-Transport-Security", "max-age=15552000; includeSubDomains")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'",
            )

    return JobRadarRequestHandler


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def origin_allowed(*, origin: str, host: str, proto: str, configured: str = "") -> bool:
    if not origin:
        return True
    allowed = {item.strip().rstrip("/") for item in configured.split(",") if item.strip()}
    if host:
        allowed.add(f"{proto}://{host}".rstrip("/"))
    return origin.rstrip("/") in allowed


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default
