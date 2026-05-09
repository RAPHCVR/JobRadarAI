from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class Job:
    source: str
    source_type: str
    title: str
    company: str
    url: str
    location: str = ""
    country: str = ""
    remote: bool = False
    description: str = ""
    posted_at: str = ""
    deadline: str = ""
    salary: str = ""
    salary_currency: str = ""
    salary_period: str = ""
    salary_min_annual_eur: float | None = None
    salary_max_annual_eur: float | None = None
    salary_normalized_annual_eur: float | None = None
    employment_type: str = ""
    ats: str = ""
    apply_url: str = ""
    tags: list[str] = field(default_factory=list)
    language_check: str = "unknown"
    remote_location_validity: str = "unknown"
    required_years: float | None = None
    experience_check: str = "unknown"
    experience_evidence: str = ""
    raw_id: str = ""
    market: str = "unknown"
    score: float = 0.0
    score_parts: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def stable_id(self) -> str:
        base = "|".join(
            [
                self.source.lower().strip(),
                self.company.lower().strip(),
                self.title.lower().strip(),
                self.url.lower().strip(),
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stable_id"] = self.stable_id
        return data


@dataclass(slots=True)
class SourceRun:
    name: str
    ok: bool
    count: int = 0
    skipped: bool = False
    reason: str = ""
