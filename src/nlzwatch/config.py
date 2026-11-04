"""clubs.yaml und filters.yaml laden."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from .models import Club, Source

DEFAULT_DEFAULTS = {
    "request_delay_seconds": 1.5,
    "timeout_seconds": 25,
    "retries": 3,
    "respect_robots": True,
}


def project_root() -> Path:
    """Wurzel des Repos, unabhaengig vom Arbeitsverzeichnis."""
    env = os.environ.get("NLZWATCH_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_clubs(path: Path = None) -> Tuple[List[Club], Dict[str, Any]]:
    """Vereine und globale Vorgaben aus clubs.yaml lesen."""
    path = path or (project_root() / "clubs.yaml")
    raw = load_yaml(path)
    defaults = dict(DEFAULT_DEFAULTS)
    defaults.update(raw.get("defaults") or {})

    clubs: List[Club] = []
    seen_ids = set()
    for entry in raw.get("clubs") or []:
        sources = []
        for s in entry.get("sources") or []:
            sid = s.get("id")
            if not sid:
                raise ValueError("Quelle ohne id bei Verein {}".format(entry.get("name")))
            if sid in seen_ids:
                raise ValueError("Doppelte Quellen-id: {}".format(sid))
            seen_ids.add(sid)
            sources.append(Source(
                id=sid,
                label=s.get("label") or sid,
                adapter=s.get("adapter") or "generic_html",
                url=s.get("url") or "",
                enabled=bool(s.get("enabled", True)),
                params=dict(s.get("params") or {}),
                empty_ok=list(s.get("empty_ok") or []),
                manual=bool(s.get("manual", False)),
                manual_reason=str(s.get("manual_reason") or ""),
                manual_hint=str(s.get("manual_hint") or ""),
            ))
        clubs.append(Club(
            name=entry.get("name") or "",
            short=entry.get("short") or "",
            sources=sources,
            speculative=dict(entry.get("speculative") or {}),
            keywords={
                str(k): list(v or [])
                for k, v in (entry.get("keywords") or {}).items()
            },
        ))
    return clubs, defaults


def load_filters(path: Path = None) -> Dict[str, Any]:
    path = path or (project_root() / "filters.yaml")
    return load_yaml(path)
