#!/usr/bin/env python3
"""pm_task — interface TaskProvider (gestionnaire de tickets agnostique) + backend Redmine.

P1 (RM2543) de la généralisation providers (CDC RM2530 [[Cdc-rm2530-providers-par-projet]]).

Sépare deux natures que `redmine_utils` mélangeait :
  * **opérations génériques** sur les tickets (fetch / list / search / note / create /
    parent) — que tout task manager sait faire → contrat `TaskProvider` ;
  * **spécificités Redmine** (custom fields, time_entries, tag IA, mapping statuts↔NORMS,
    référence) → restent dans `redmine_utils` / au-dessus de l'interface, exposées par
    `RedmineTaskProvider` derrière des **capabilities** (elles ne généralisent PAS aux
    Issues GitLab/GitHub — cf. CDC §2.3, « ne pas ré-implémenter Redmine »).

**Backend unique en P1 : Redmine.** `RedmineTaskProvider` **délègue à `redmine_utils`**
(iso-comportement strict, creds globaux actuels). Le choix d'instance par projet passe
par le registre P0 (`pm_registry`) ; la résolution des creds *par instance* est P4/RM2546.
Un 2e backend (Issues) est P2/RM2544.

Migration des consommateurs : incrémentale. Ce module est **additif** — `redmine_utils`
reste la couche I/O Redmine bas niveau (implémentation de `RedmineTaskProvider`).
"""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redmine_utils as _ru
from pm_registry import resolve_instance


class TaskProviderError(Exception):
    """Backend de task manager non supporté / incohérent."""


@dataclass(frozen=True)
class TaskCapabilities:
    """Ce que le backend sait faire au-delà du contrat générique minimal."""
    custom_fields: bool = False     # champs personnalisés (CF Redmine)
    time_tracking: bool = False     # saisies de temps (time_entries)
    wiki: bool = False              # wiki intégré
    full_text_search: bool = False  # recherche plein-texte serveur
    parent_link: bool = False       # parent natif (sous-tâches)
    ia_tag: bool = False            # tag IA (mutex tickets PM/purs)


class TaskProvider:
    """Contrat générique d'un gestionnaire de tickets.

    Les méthodes du contrat lèvent NotImplementedError par défaut ; un backend
    concret les implémente. Les extras propres à un backend (ex. time_entries
    Redmine) vivent sur la sous-classe et sont gardés par `capabilities`.
    """
    name = "base"
    capabilities = TaskCapabilities()

    def __init__(self, instance=None):
        # pm_registry.Instance retenue (None en usage direct mono-instance).
        self.instance = instance

    # ── lecture ──────────────────────────────────────────────────────────
    def fetch_issue(self, issue_id, include=None):
        raise NotImplementedError

    def list_issues(self, params=None, limit=25):
        raise NotImplementedError

    def search_issues(self, query, limit=15):
        raise NotImplementedError

    # ── écriture ─────────────────────────────────────────────────────────
    def add_note(self, issue_id, note):
        raise NotImplementedError

    def create_issue(self, **kw):
        raise NotImplementedError

    def set_parent(self, issue_id, parent_id):
        raise NotImplementedError


class RedmineTaskProvider(TaskProvider):
    """Backend Redmine — délègue à `redmine_utils` (iso-comportement)."""
    name = "redmine"
    capabilities = TaskCapabilities(
        custom_fields=True, time_tracking=True, wiki=True,
        full_text_search=True, parent_link=True, ia_tag=True,
    )

    # ── contrat générique (délégation stricte) ───────────────────────────
    def fetch_issue(self, issue_id, include=None):
        return _ru.fetch_issue(issue_id, include=include)

    def list_issues(self, params=None, limit=25):
        return _ru.list_issues(params=params, limit=limit)

    def search_issues(self, query, limit=15):
        return _ru.search_issues(query, limit=limit)

    def add_note(self, issue_id, note):
        return _ru.add_issue_note(issue_id, note)

    def create_issue(self, **kw):
        # kwargs Redmine (project_id, tracker_id, priority_id, subject, …).
        # Le contrat générique sera resserré quand un 2e backend l'imposera (P2).
        return _ru.create_redmine_issue(**kw)

    def set_parent(self, issue_id, parent_id):
        return _ru.set_issue_parent(issue_id, parent_id)

    # ── extras Redmine (hors contrat générique ; gardés par capabilities) ─
    def update_fields(self, issue_id, **kw):
        return _ru.update_issue_fields(issue_id, **kw)

    def create_time_entry(self, issue_id, **kw):
        return _ru.create_time_entry(issue_id, **kw)

    def list_time_entries(self, params=None, limit=100):
        return _ru.list_time_entries(params=params, limit=limit)

    def set_ia_tag(self, issue_id, value="IA"):
        return _ru.set_issue_ia_tag(issue_id, value)


class GitlabIssuesTaskProvider(TaskProvider):
    """Backend GitLab Issues — PoC **lecture seule** (P2/RM2544).

    Éprouve l'abstraction face à un backend SANS champs perso ni time-entries : les
    capabilities sont dégradées (custom_fields/time_tracking/ia_tag = False). Réutilise
    `pm_forge.GitlabForge` pour le transport (token + api /api/v4). Un ticket est
    identifié par son **iid dans le projet** (scope projet ≠ id global Redmine) — ce
    décalage de modèle est précisément ce que le PoC met en lumière. Le projet vient
    de `instance.options['repo']` (path_with_namespace) ou de l'argument `repo=`.
    """
    name = "gitlab_issues"
    capabilities = TaskCapabilities(full_text_search=True)  # pas de CF/time/wiki/ia/parent natif

    def __init__(self, instance=None, repo=None, role="worker"):
        super().__init__(instance)
        from pm_forge import GitlabForge
        opts = (instance.options if instance and instance.options else {}) or {}
        repo_path = repo or opts.get("repo") or ""
        if not repo_path:
            raise TaskProviderError(
                "gitlab_issues : 'repo' requis (instance.options.repo ou argument repo=)")
        self._forge = GitlabForge(repo_path)
        self._role = role
        self._token_cache = None
        self._pid = None

    def _token(self):
        if self._token_cache is None:
            self._token_cache = self._forge.token(self._role)
        return self._token_cache

    def _project_id(self):
        if self._pid is None:
            self._pid = self._forge.resolve_project(self._token()).id
        return self._pid

    # ── contrat générique (lecture) ──────────────────────────────────────
    def fetch_issue(self, issue_id, include=None):
        pid = self._project_id()
        st, data, raw = self._forge.api("GET", f"/projects/{pid}/issues/{issue_id}", self._token())
        if st != 200 or not isinstance(data, dict):
            raise TaskProviderError(f"GitLab issue !{issue_id} (projet {pid}) : HTTP {st}")
        return data

    def list_issues(self, params=None, limit=25):
        import urllib.parse
        pid = self._project_id()
        qp = dict(params or {})
        qp.setdefault("per_page", limit)
        qs = urllib.parse.urlencode(qp, doseq=True)
        st, data, raw = self._forge.api("GET", f"/projects/{pid}/issues?{qs}", self._token())
        if st != 200 or not isinstance(data, list):
            raise TaskProviderError(f"GitLab issues (projet {pid}) : HTTP {st}")
        return data

    def search_issues(self, query, limit=15):
        return self.list_issues({"search": query}, limit=limit)

    # ── écriture : hors périmètre PoC (lecture seule) ─────────────────────
    def add_note(self, issue_id, note):
        raise TaskProviderError("gitlab_issues : écriture hors périmètre PoC (P2)")

    def create_issue(self, **kw):
        raise TaskProviderError("gitlab_issues : écriture hors périmètre PoC (P2)")

    def set_parent(self, issue_id, parent_id):
        raise TaskProviderError("gitlab_issues : parent non modélisé (liens GitLab)")


_BACKENDS = {"redmine": RedmineTaskProvider, "gitlab_issues": GitlabIssuesTaskProvider}


def get_task_provider(project_meta=None, registry=None, instance=None):
    """Retourne le `TaskProvider` d'un projet.

    Priorité : `instance` explicite > résolution via `registry`/`project_meta`
    (P0) > défaut Redmine mono-instance (iso-comportement actuel quand aucun
    registre n'est fourni). Lève `TaskProviderError` si le type d'instance
    résolu n'a pas de backend (seul 'redmine' en P1).
    """
    if instance is None and registry is not None:
        instance = resolve_instance(project_meta or {}, "task", registry).instance
    itype = instance.type if instance is not None else "redmine"
    backend = _BACKENDS.get(itype)
    if backend is None:
        raise TaskProviderError(
            f"backend task '{itype}' non supporté en P1 "
            f"(seul 'redmine' ; 2e backend = P2/RM2544)")
    return backend(instance)
