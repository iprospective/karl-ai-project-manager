#!/usr/bin/env python3
"""pm_forge — abstraction de forge git (GitLab / Gogs / GitHub) — RM2498 (T2).

Découple le PM de GitLab : les scripts (pm-mr, pm-protect, pm-promote…) appellent
une interface `Forge` unique ; l'implémentation est choisie d'après le remote.

Séparation des responsabilités :
  - `pm_forge` = primitives *forge* (résoudre projet, créer/merger/lire une PR,
    appel API, parse remote, tokens, capabilities). RIEN de spécifique au PM.
  - les scripts appelants = *politique PM* (garde tripwire #13, rollback sha:null,
    CF Redmine, idempotence, transitions de statut).

`GitlabForge` reproduit EXACTEMENT le comportement historique de pm-mr (RM1871) :
résolution par ID numérique (anti-%2F Apache, match exact path_with_namespace
RM2219), attente de mergeabilité async, conservation de la branche source.

Capabilities : certaines forges n'ont pas d'API pull request (Gogs) →
`caps.pull_request_api == False` ⇒ l'appelant DÉGRADE (flux « lien compare »)
au lieu d'échouer.
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


class ForgeError(Exception):
    pass


# ── Structures légères ────────────────────────────────────────────────────────
class ProjectRef:
    """Projet résolu. `id` = id numérique (GitLab) ou None (Gogs/GitHub : owner/repo suffit)."""
    def __init__(self, id, path, raw=None):
        self.id = id
        self.path = path            # path_with_namespace / owner/repo
        self.raw = raw or {}


class PrRef:
    """Pull/Merge Request (ou lien de création si la forge n'a pas d'API PR)."""
    def __init__(self, iid, source, target, web_url, state=None, sha=None,
                 raw=None, is_compare_link=False):
        self.iid = iid                       # numéro (None si compare-link)
        self.source = source
        self.target = target
        self.web_url = web_url               # URL PR, ou URL « compare » (Gogs)
        self.state = state
        self.sha = sha
        self.raw = raw or {}
        self.is_compare_link = is_compare_link


class Capabilities:
    def __init__(self, pull_request_api, async_merge_status, access_level_model):
        self.pull_request_api = pull_request_api      # POST/merge PR par API ?
        self.async_merge_status = async_merge_status  # detailed_merge_status (GitLab) ?
        self.access_level_model = access_level_model   # "gitlab" | "gitea" | "github"


# ── Parse remote / détection de forge ─────────────────────────────────────────
def parse_remote(url):
    """(hint, repo_path) depuis une URL de remote. `hint` = alias/host servant à
    choisir la forge. Gère alias SSH `gitlab:owner/repo`, `git@host:owner/repo`,
    `ssh://git@host:port/owner/repo`, `https://host/owner/repo`."""
    s = url.strip()
    if s.endswith(".git"):
        s = s[:-4]
    if s.startswith(("http://", "https://", "ssh://")):
        u = urllib.parse.urlparse(s)
        return (u.hostname or ""), u.path.lstrip("/")
    if ":" in s:                                    # scp-like / alias : host:owner/repo
        host, path = s.split(":", 1)
        if "@" in host:                             # git@host → host
            host = host.split("@", 1)[1]
        return host, path.lstrip("/")
    return "", s.lstrip("/")


def forge_name(hint):
    """Nom de forge depuis un hint (alias ou hostname). None si indéterminé."""
    h = (hint or "").lower()
    if "gogs" in h:
        return "gogs"
    if "github" in h:
        return "github"
    if "gitlab" in h:
        return "gitlab"
    return None


def _git_remote_url(repo, remote="origin"):
    r = subprocess.run(["git", "-C", str(repo), "remote", "get-url", remote],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ForgeError(f"remote '{remote}' introuvable dans {repo}")
    return r.stdout.strip()


def _git_config_forge(repo):
    """Lit `pm.forge` (git config local du dépôt). '' si absent."""
    r = subprocess.run(["git", "-C", str(repo), "config", "--get", "pm.forge"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def get_forge(repo=".", remote="origin", url=None, forge=None):
    """Fabrique : instancie la bonne forge pour le dépôt.

    Priorité de sélection (nécessaire car un remote Gogs tunnelé en
    `ssh://gogs@localhost:28022/…` n'est PAS détectable par son host) :
      1. `forge=` explicite (appelant) ;
      2. env `PM_FORGE` (gitlab|gogs|github) ;
      3. `git config pm.forge` du dépôt (signal persistant, posé au clonage) ;
      4. détection d'après le host/alias du remote (défaut : GitLab, inchangé)."""
    if url is None:
        url = _git_remote_url(repo, remote)
    hint, repo_path = parse_remote(url)
    name = (forge or os.environ.get("PM_FORGE") or _git_config_forge(repo)
            or forge_name(hint) or "").lower()
    impls = {"gitlab": GitlabForge, "gogs": GogsForge, "github": GithubForge}
    if name not in impls:
        raise ForgeError(
            f"forge non reconnue depuis le remote '{url}' (hint '{hint}'). "
            f"Précise-la : `git config pm.forge gogs`, ou PM_FORGE=gitlab|gogs|github.")
    return impls[name](repo_path)


# ── Base commune ──────────────────────────────────────────────────────────────
class Forge:
    """Interface. Les implémentations concrètes surchargent ce qui les concerne."""
    name = "?"

    def __init__(self, repo_path):
        self.repo_path = repo_path

    @property
    def capabilities(self):
        raise NotImplementedError

    def token(self, role):
        raise NotImplementedError

    def resolve_project(self, token):
        raise NotImplementedError

    def find_open_pr(self, project, source, target, token):
        raise NotImplementedError

    def get_pr(self, project, iid, token):
        raise NotImplementedError

    def create_pr(self, project, source, target, title, description, token):
        raise NotImplementedError

    def merge_pr(self, project, iid, token, squash=False, keep_source=True):
        raise NotImplementedError

    def close_pr(self, project, iid, token):
        raise NotImplementedError

    def compare_url(self, source, target):
        raise NotImplementedError


# ── GitLab (iso-comportement pm-mr / RM1871) ──────────────────────────────────
class GitlabForge(Forge):
    name = "gitlab"
    DEFAULT_HOST = "gitlab.iprospective.fr"
    TOKEN_ENV = {"manager": "GITLAB_MANAGER_TOKEN", "worker": "GITLAB_WORKER_TOKEN"}

    def __init__(self, repo_path):
        super().__init__(repo_path)
        self.base = (os.environ.get("GITLAB_URL") or f"https://{self.DEFAULT_HOST}").rstrip("/")
        self.api_base = self.base + "/api/v4"

    @property
    def capabilities(self):
        return Capabilities(pull_request_api=True, async_merge_status=True,
                            access_level_model="gitlab")

    def token(self, role):
        var = self.TOKEN_ENV[role]
        tok = os.environ.get(var)
        if not tok:
            raise ForgeError(f"{var} absent du .env du PM (PAT karl-{role}, scope api).")
        return tok

    def api(self, method, path, token, fields=None):
        """(status, parsed_json|None, raw). Jamais d'exception sur 4xx/5xx."""
        url = path if path.startswith("http") else self.api_base + path
        data = urllib.parse.urlencode(fields, doseq=True).encode() if fields else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("PRIVATE-TOKEN", token)
        if data:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
                status = r.status
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            status = e.code
        except Exception as e:
            return 0, None, str(e)
        try:
            return status, json.loads(raw), raw
        except Exception:
            return status, None, raw

    def _list_projects_paged(self, token):
        page, acc = 1, []
        while True:
            st, data, raw = self.api("GET", f"/projects?membership=true&simple=true"
                                            f"&per_page=100&page={page}", token)
            if st != 200 or not isinstance(data, list):
                raise ForgeError(f"énumération projets (HTTP {st}) : {raw[:200]}")
            acc += data
            if len(data) < 100:
                return acc
            page += 1

    def resolve_project(self, token):
        """ID numérique par match EXACT de path_with_namespace (RM2219, anti-%2F)."""
        repo_path = self.repo_path
        seg = repo_path.rstrip("/").split("/")[-1]
        st, data, _ = self.api("GET", f"/projects?search={urllib.parse.quote(seg)}"
                                      f"&per_page=100&membership=true", token)
        cands = data if (st == 200 and isinstance(data, list)) else []
        exact = [p for p in cands if p.get("path_with_namespace") == repo_path]
        if not exact:
            cands = self._list_projects_paged(token)
            exact = [p for p in cands if p.get("path_with_namespace") == repo_path]
        if len(exact) == 1:
            p = exact[0]
            return ProjectRef(p["id"], p["path_with_namespace"], p)
        homonyms = sorted({p["path_with_namespace"] for p in cands if p.get("path") == seg})
        raise ForgeError(
            f"projet '{repo_path}' — {len(exact)} match exact (attendu 1), pas de "
            f"fallback basename (RM2219). Homonymes '{seg}' : {', '.join(homonyms) or 'aucun'}.")

    def _pr_from(self, mr):
        return PrRef(mr.get("iid"), mr.get("source_branch"), mr.get("target_branch"),
                     mr.get("web_url"), state=mr.get("state"), sha=mr.get("sha"), raw=mr)

    def find_open_pr(self, project, source, target, token):
        st, lst, _ = self.api("GET",
            f"/projects/{project.id}/merge_requests?source_branch={urllib.parse.quote(source)}"
            f"&target_branch={urllib.parse.quote(target)}&state=opened", token)
        mr = lst[0] if (st == 200 and isinstance(lst, list) and lst) else None
        return self._pr_from(mr) if mr else None

    def get_pr(self, project, iid, token):
        st, mr, raw = self.api("GET", f"/projects/{project.id}/merge_requests/{iid}", token)
        if st != 200 or not mr:
            raise ForgeError(f"MR !{iid} introuvable (HTTP {st}).")
        return self._pr_from(mr)

    def create_pr(self, project, source, target, title, description, token):
        st, mr, raw = self.api("POST", f"/projects/{project.id}/merge_requests", token, fields={
            "source_branch": source, "target_branch": target,
            "title": title, "description": description,
            "remove_source_branch": "false",
        })
        if not mr:  # corps vide/ambigu → re-GET pour confirmer
            pr = self.find_open_pr(project, source, target, token)
            if pr:
                return pr
            raise ForgeError(f"création MR (HTTP {st}) : {raw[:200]}")
        return self._pr_from(mr)

    def wait_mergeable(self, project, iid, token, attempts=8, delay=2.0):
        base = f"/projects/{project.id}/merge_requests/{iid}"
        last = None
        for i in range(attempts):
            st, mr, _ = self.api("GET", base, token)
            if not mr:
                raise ForgeError(f"MR !{iid} introuvable pendant l'attente (HTTP {st}).")
            dms, ms = mr.get("detailed_merge_status"), mr.get("merge_status")
            last = dms or ms
            if dms == "mergeable" or (dms is None and ms == "can_be_merged"):
                return self._pr_from(mr)
            if dms in ("conflict", "broken_status") or ms == "cannot_be_merged":
                hint = " — conflit à résoudre."
                if mr.get("sha") is None:
                    hint = (" — `sha:null` : la branche source n'existe pas sur ce projet "
                            "(MR créée au mauvais endroit ? cf. RM2219).")
                raise ForgeError(f"MR !{iid} non mergeable ({last}){hint}")
            if i < attempts - 1:
                time.sleep(delay)
        raise ForgeError(f"MR !{iid} toujours non mergeable après {attempts} tentatives "
                         f"(dernier état : {last}).")

    def merge_pr(self, project, iid, token, squash=False, keep_source=True):
        base = f"/projects/{project.id}/merge_requests/{iid}"
        self.wait_mergeable(project, iid, token)
        fields = {"should_remove_source_branch": "false" if keep_source else "true"}
        if squash:
            fields["squash"] = "true"
        st, res, raw = self.api("PUT", base + "/merge", token, fields=fields)
        state = res.get("state") if res else None
        if state != "merged":
            st2, mr2, _ = self.api("GET", base, token)
            state = mr2.get("state") if mr2 else None
        if state != "merged":
            raise ForgeError(f"merge MR !{iid} (HTTP {st}, state={state}) : {raw[:200]}")
        return state

    def close_pr(self, project, iid, token):
        self.api("PUT", f"/projects/{project.id}/merge_requests/{iid}", token,
                 fields={"state_event": "close"})

    def compare_url(self, source, target):
        # GitLab a une API PR ; le compare web reste dispo mais inutilisé ici.
        return f"{self.base}/{self.repo_path}/-/compare/{target}...{source}"


# ── Gogs (pas d'API PR → flux « lien compare ») ───────────────────────────────
class GogsForge(Forge):
    name = "gogs"

    def __init__(self, repo_path):
        super().__init__(repo_path)
        self.base = (os.environ.get("GOGS_URL") or "").rstrip("/")

    @property
    def capabilities(self):
        # ⚠ Gogs v1 n'expose AUCUN endpoint pull request (vérifié RM2410/RM5557).
        return Capabilities(pull_request_api=False, async_merge_status=False,
                            access_level_model="gitea")

    def token(self, role):
        # Optionnel : le flux « lien-compare » n'appelle aucune API Gogs (pas d'API
        # PR) et le push utilise l'auth git du dépôt (clé SSH / helper), pas ce token.
        return os.environ.get("GOGS_TOKEN", "")

    def resolve_project(self, token):
        # Gogs adresse par owner/repo directement (ni id numérique, ni %2F).
        return ProjectRef(None, self.repo_path, {"owner_repo": self.repo_path})

    def compare_url(self, source, target):
        if not self.base:
            raise ForgeError("GOGS_URL absent : impossible de construire l'URL compare.")
        return f"{self.base}/{self.repo_path}/compare/{target}...{source}"

    def create_pr(self, project, source, target, title, description, token):
        # Dégradation : pas d'API PR. On renvoie le lien de création (compare),
        # l'appelant l'affiche / le pose en CF ; l'ouverture reste un geste web humain.
        return PrRef(None, source, target, self.compare_url(source, target),
                     state="compare", is_compare_link=True)

    def find_open_pr(self, project, source, target, token):
        return None  # pas d'API PR → pas de détection d'idempotence côté forge

    def merge_pr(self, project, iid, token, squash=False, keep_source=True):
        raise ForgeError("Gogs n'a pas d'API de merge de PR — merge web manuel.")


# ── GitHub (vraie API pull request — RM2501/T5) ───────────────────────────────
class GithubForge(Forge):
    """GitHub — vraie API PR. Adressage par owner/repo (pas d'id numérique, comme
    Gogs). Auth Bearer, corps JSON (≠ GitLab en form-urlencoded). États GitHub
    (open/closed + booléen merged) normalisés en opened/closed/merged (comme GitLab),
    pour que la politique PM de pm-mr reste inchangée."""
    name = "github"

    def __init__(self, repo_path):
        super().__init__(repo_path)
        self.api_base = (os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
        self.web_base = (os.environ.get("GITHUB_URL") or "https://github.com").rstrip("/")

    @property
    def capabilities(self):
        return Capabilities(pull_request_api=True, async_merge_status=False,
                            access_level_model="github")

    def token(self, role):
        tok = os.environ.get("GITHUB_TOKEN")
        if not tok:
            raise ForgeError("GITHUB_TOKEN absent (PAT GitHub, scope repo).")
        return tok

    def api(self, method, path, token, fields=None):
        """(status, parsed_json|None, raw). Corps JSON, auth Bearer. Jamais d'exception sur 4xx/5xx."""
        url = path if path.startswith("http") else self.api_base + path
        data = json.dumps(fields).encode() if fields is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
                status = r.status
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            status = e.code
        except Exception as e:
            return 0, None, str(e)
        try:
            return status, json.loads(raw), raw
        except Exception:
            return status, None, raw

    def resolve_project(self, token):
        # GitHub adresse par owner/repo ; on vérifie l'existence (et le droit d'accès).
        st, data, _ = self.api("GET", f"/repos/{self.repo_path}", token)
        if st != 200 or not isinstance(data, dict):
            raise ForgeError(f"projet GitHub '{self.repo_path}' introuvable (HTTP {st}).")
        return ProjectRef(None, self.repo_path, data)

    @staticmethod
    def _state(pr):
        if pr.get("merged") or pr.get("merged_at"):
            return "merged"
        return "opened" if pr.get("state") == "open" else "closed"

    def _pr_from(self, pr):
        return PrRef(pr.get("number"), (pr.get("head") or {}).get("ref"),
                     (pr.get("base") or {}).get("ref"), pr.get("html_url"),
                     state=self._state(pr), sha=(pr.get("head") or {}).get("sha"), raw=pr)

    def find_open_pr(self, project, source, target, token):
        st, lst, _ = self.api("GET",
            f"/repos/{project.path}/pulls?state=open&base={urllib.parse.quote(target)}", token)
        # Le filtre `head` de GitHub attend `owner:branch` (cross-repo) → on filtre
        # en Python sur la branche source pour rester robuste en same-repo.
        if isinstance(lst, list):
            for pr in lst:
                if (pr.get("head") or {}).get("ref") == source \
                        and (pr.get("base") or {}).get("ref") == target:
                    return self._pr_from(pr)
        return None

    def get_pr(self, project, iid, token):
        st, pr, _ = self.api("GET", f"/repos/{project.path}/pulls/{iid}", token)
        if st != 200 or not pr:
            raise ForgeError(f"PR #{iid} introuvable (HTTP {st}).")
        return self._pr_from(pr)

    def create_pr(self, project, source, target, title, description, token):
        st, pr, raw = self.api("POST", f"/repos/{project.path}/pulls", token, fields={
            "head": source, "base": target, "title": title, "body": description or "",
        })
        if st in (200, 201) and isinstance(pr, dict) and pr.get("number"):
            return self._pr_from(pr)
        existing = self.find_open_pr(project, source, target, token)  # déjà ouverte ?
        if existing:
            return existing
        raise ForgeError(f"création PR (HTTP {st}) : {raw[:200]}")

    def merge_pr(self, project, iid, token, squash=False, keep_source=True):
        # GitHub ne supprime PAS la branche source au merge (suppression séparée) →
        # keep_source respecté par défaut. (Mergeabilité async non pollée en v1.)
        st, res, raw = self.api("PUT", f"/repos/{project.path}/pulls/{iid}/merge", token,
                                fields={"merge_method": "squash" if squash else "merge"})
        if st == 200 and isinstance(res, dict) and res.get("merged"):
            return "merged"
        raise ForgeError(f"merge PR #{iid} (HTTP {st}) : {raw[:200]}")

    def close_pr(self, project, iid, token):
        self.api("PATCH", f"/repos/{project.path}/pulls/{iid}", token, fields={"state": "closed"})

    def compare_url(self, source, target):
        return f"{self.web_base}/{self.repo_path}/compare/{target}...{source}"
