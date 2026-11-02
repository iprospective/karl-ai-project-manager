"""Acces a la knowledge PM sans dependance a mmi-kb (RM3609).

Trois modes, par ordre de dependance croissante :

- ``local``    : les documents Markdown de ``<core>/knowledge/`` ;
- ``snapshot`` : un bundle KB versionne (manifest + entities.jsonl + views/*.json) ;
- ``remote``   : l'API ``kb.iprospective.fr``, avec repli snapshot/local.

Le mode par defaut est ``local`` : PM demarre et travaille sans KB installe.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

MODES = ("local", "snapshot", "remote")


class KnowledgeError(Exception):
    """Erreur d'usage, jamais un plantage de PM."""


def _read_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    try:
        data = yaml.safe_load(text[4:end]) or {} if yaml else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, text[end + 4:].lstrip("\n")


def _first_heading(body: str) -> str:
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


@dataclass
class LocalDoc:
    id: str
    title: str
    body: str
    path: str
    meta: dict[str, Any] = field(default_factory=dict)
    tool: str = ""

    def public(self, body: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "tool": self.tool,
            "meta": self.meta,
        }
        if body:
            data["body"] = self.body
        return data


class KnowledgeStore:
    def __init__(
        self,
        mode: str | None = None,
        local: Path | None = None,
        snapshot: Path | None = None,
        url: str | None = None,
        token: str | None = None,
    ):
        self.mode = (mode or os.environ.get("PM_KB_MODE") or "local").lower()
        if self.mode not in MODES:
            raise KnowledgeError(f"mode knowledge inconnu : {self.mode} (attendu : {', '.join(MODES)})")
        self.local = Path(local or os.environ.get("PM_KB_LOCAL") or Path(__file__).resolve().parents[1] / "knowledge")
        self.snapshot = Path(
            snapshot
            or os.environ.get("PM_KB_SNAPSHOT")
            or self.local / "kb-snapshot"
        )
        self.url = (url or os.environ.get("PM_KB_URL") or "https://kb.iprospective.fr").rstrip("/")
        self.token = token or os.environ.get("PM_KB_TOKEN", "")

    # ---------------------------------------------------------------- local
    def _local_docs(self) -> list[LocalDoc]:
        if not self.local.is_dir():
            return []
        docs = []
        for path in sorted(self.local.rglob("*.md")):
            if path.name == "INDEX.md":
                continue
            rel = str(path.relative_to(self.local))
            text = path.read_text(encoding="utf-8", errors="replace")
            meta, body = _read_frontmatter(text)
            title = str(meta.get("title") or _first_heading(body) or path.stem)
            doc_id = str(meta.get("id") or f"local:{rel.removesuffix('.md')}")
            tool = str(meta.get("tool") or meta.get("product") or rel.split("/", 1)[0])
            docs.append(LocalDoc(doc_id, title, body, rel, meta, tool))
        return docs

    # ------------------------------------------------------------- snapshot
    def _manifest(self) -> dict[str, Any]:
        path = self.snapshot / "manifest.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _snapshot_entities(self) -> list[dict[str, Any]]:
        path = self.snapshot / "entities.jsonl"
        if not path.is_file():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    # --------------------------------------------------------------- remote
    def _remote(self, endpoint: str) -> Any:
        request = urllib.request.Request(self.url + endpoint, headers={"Accept": "application/json"})
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    # ------------------------------------------------------------------ API
    def get(self, doc_id: str, body: bool = True) -> dict[str, Any] | None:
        if self.mode == "remote":
            try:
                return self._remote(f"/entities/{quote(doc_id, safe='')}")
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                pass
        if self.mode in ("snapshot", "remote"):
            for row in self._snapshot_entities():
                if row.get("id") == doc_id:
                    return row
        for doc in self._local_docs():
            if doc.id == doc_id or doc.path.removesuffix(".md") == doc_id:
                return doc.public(body=body)
        return None

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        needle = query.lower()
        rows = []
        if self.mode in ("snapshot", "remote"):
            for row in self._snapshot_entities():
                text = " ".join(str(row.get(key, "")) for key in ("id", "title", "summary", "body"))
                if needle in text.lower():
                    rows.append({"id": row.get("id"), "title": row.get("title", "")})
        if not rows or self.mode == "local":
            for doc in self._local_docs():
                text = f"{doc.id} {doc.title} {doc.body}"
                if needle in text.lower():
                    rows.append({"id": doc.id, "title": doc.title})
        return rows[:limit]

    def view(self, name: str, filters: dict[str, str] | None = None) -> dict[str, Any]:
        path = self.snapshot / "views" / f"{name}.json"
        if self.mode in ("snapshot", "remote") and path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data
            except (OSError, json.JSONDecodeError):
                pass
        if self.mode == "remote":
            query = "&".join(f"{key}={quote(value)}" for key, value in (filters or {}).items() if value)
            try:
                return self._remote(f"/views/{quote(name)}{('?' + query) if query else ''}")
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                pass
        return {
            "schema": "pm-kb.local/v1",
            "view": name,
            "items": [
                doc.public()
                for doc in self._local_docs()
                if (not filters or not filters.get("tool") or doc.tool == filters["tool"])
            ],
        }

    def info(self) -> dict[str, Any]:
        manifest = self._manifest()
        return {
            "mode": self.mode,
            "local": str(self.local),
            "snapshot": str(self.snapshot),
            "url": self.url,
            "snapshot_commit": manifest.get("knowledge_commit"),
            "snapshot_schema": manifest.get("schema"),
            "snapshot_available": (self.snapshot / "manifest.json").is_file(),
        }
