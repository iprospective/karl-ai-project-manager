#!/usr/bin/env python3
"""pm-env-audit — audit hebdomadaire de TOUS les environnements (RM3163).

Incident fondateur (2026-09-14, calyclay/calymix) : 7 commits poussés sur la branche RM2264
**après** le merge de sa MR, et un document de RM1937 (juillet), n'ont jamais atteint `master`.
Personne ne l'a vu pendant un mois : les branches suivantes sont parties sans, une correction
validée est « revenue », des docs périmés ont dû être repris à la main. Décision Mathieu : un
audit **outillé, hebdomadaire, avec historique des contrôles** — consigné **dans chaque projet**.

Ce que l'audit signale, pour chaque workspace PM-tracké (`/zfs/workspaces/<client>/<projet>/`,
layout RM1993 `repos/*.git` + `envs/*`, ou layout historique = un repo à la racine) :

  BRANCHE   commits présents sur une branche (locale ou distante) et **absents PAR CONTENU** de
            la branche d'intégration (`git cherry`, pas seulement l'ancêtre — un cherry-pick
            compte comme intégré). Gravité d'après l'**état réel de la MR** (API forge, v2) :
            MR mergée et commits postérieurs → ÉLEVÉE (le cas RM2264) ; MR ouverte → info ;
            MR fermée sans merge → moyenne ; sans MR : ticket fermé / en MEP → ÉLEVÉE, sinon
            moyenne. Forge injoignable (`--no-forge`, token absent) → repli sur le statut du ticket.
  SALE      fichiers non commités dans un env, avec l'âge du plus ancien (mtime) —
            alerte au-delà de `--max-age` jours (défaut 7).
  RETARD    branche d'intégration locale en retard sur le remote.
  STASH     entrées de stash oubliées dans le bare.
  FERMÉ     worktree d'un ticket `ferme` encore présent : **obsolète** (propre et intégré → à
            nettoyer : `pm-env-gc --apply --workspace <ws>`, ou `pm-env-gc --all` pour tout le parc)
            ou **à traiter** (modifs non commitées → ÉLEVÉE ; commits non intégrés → voir BRANCHE).
  REMOTE    fetch impossible (remote injoignable ou clé absente) — avec `--fetch`.

Consignation (v2) — **dans le dépôt de données de chaque projet** (`<workspace>/.mmi-pm/env-audit/`,
commit + push direct : un core n'a pas de MR) :
  history.md              une ligne par audit (date, fetch, anomalies par gravité, Δ vs précédent)
  YYYY-MM-DD_HHMM.md      le détail (anomalies + nouvelles / résolues depuis l'audit précédent),
                          écrit seulement s'il y a au moins une anomalie ou un changement
  last.json               l'état courant (clés d'anomalies) qui permet le Δ au tour suivant
Le repo PM ne garde qu'une **synthèse globale** locale : `var/env-audit/history.jsonl` (`--last`).
`pm-doctor` **lit** cette consignation (audit absent ou > 7 j → avertissement, ÉLEVÉE ouverte →
erreur) sans relancer l'audit : c'est lui le point d'entrée quotidien, l'audit reste le tour hebdo.
Par défaut seules les **branches de tickets** (`<RMid>-…`) et les branches locales sont examinées
par contenu ; les autres branches distantes (miroirs amont, `develop`, releases…) sont comptées
sans être parcourues (`--all-branches` pour tout examiner — lent sur un gros dépôt).
Les dépôts de CODE ne sont jamais modifiés (lecture seule ; `--fetch` ne touche que `origin/*`).
Code retour : 0 = rien d'élevé, 2 = au moins une anomalie ÉLEVÉE.

Usage :
    pm-env-audit.py                      # tous les workspaces, refs locales (rapide)
    pm-env-audit.py --fetch              # rafraîchit origin/* d'abord (recommandé, hebdo)
    pm-env-audit.py --workspace calyclay/calymix
    pm-env-audit.py --last               # date et bilan du dernier audit (global, ou du workspace)
    pm-env-audit.py --json               # sortie machine
    pm-env-audit.py --no-consign         # ne rien écrire dans les projets (essai)
    pm-env-audit.py --all-branches       # examiner aussi les branches distantes hors convention
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402

WORKSPACES_ROOT = Path(os.environ.get("PM_WORKSPACES_ROOT", "/zfs/workspaces"))
TICKET_RE = re.compile(r"^(\d+)-")
FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
MR_URL_RE = re.compile(r"https?://\S+?/(?:-/)?(?:merge_requests|pull|pulls)/\d+")
# La branche par défaut du remote (origin/HEAD) passe en tête : sur calicote/dolibarr, `origin/dev`
# est une branche morte de 2023 (524 commits) et l'intégration réelle est `develop` (126 000).
INTEGRATION_CANDIDATES = ("origin/dev", "origin/develop", "origin/main", "origin/master")
INTEGRATION_NAMES = ("dev", "develop", "main", "master")
CLOSED_LIKE = {"ferme", "a_mep", "en_mep"}
HIGH, MED, LOW = "ÉLEVÉE", "moyenne", "info"
ORDER = {HIGH: 0, MED: 1, LOW: 2}
AUDIT_DIRNAME = "env-audit"

# ----------------------------------------------------------------------------- git
# Jamais d'invite interactive : un remote qui demande un mot de passe ou une passphrase échoue
# (→ REMOTE) au lieu de bloquer l'audit de 45 workspaces.
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0",
           "GIT_SSH_COMMAND": os.environ.get("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=15")}
CHERRY_MAX = int(os.environ.get("PM_ENV_AUDIT_CHERRY_MAX", "1500"))


TRACE = os.environ.get("PM_ENV_AUDIT_TRACE")   # =1 : commandes git > 1 s sur stderr (profilage)


def git(args, cwd, timeout=60):
    t0 = time.time()
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                              timeout=timeout, env=GIT_ENV)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "timeout")
    finally:
        if TRACE and time.time() - t0 > 1:
            print(f"    [{time.time() - t0:5.1f} s] git -C {Path(cwd).name} {' '.join(args)[:90]}", file=sys.stderr)


def ref_exists(repo: Path, ref: str) -> bool:
    return git(["rev-parse", "--verify", "-q", ref + "^{commit}"], repo).returncode == 0


def integration_refs(repo: Path) -> list[str]:
    """Branches d'intégration du dépôt, la branche par défaut du remote (origin/HEAD) d'abord."""
    head = git(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], repo).stdout.strip()
    cands = ([head] if head else []) + list(INTEGRATION_CANDIDATES)
    out = []
    for r in cands:
        if r not in out and ref_exists(repo, r):
            out.append(r)
    return out


def ahead_count(repo: Path, upstream: str, branch: str) -> int:
    """Commits de `branch` non ancêtres de `upstream` (rapide ; 0 ⇒ inutile de lancer cherry)."""
    r = git(["rev-list", "--count", f"{upstream}..{branch}"], repo)
    return int(r.stdout.strip() or 0) if r.returncode == 0 else -1


def patch_ids(repo: Path, range_: str, timeout=120) -> set[str] | None:
    """Patch-id (stables) des commits d'une plage `a..b` — ce que `git cherry` recalcule à chaque
    appel pour le côté intégration. None si indisponible (timeout, erreur)."""
    t0 = time.time()
    try:
        log = subprocess.Popen(["git", "-C", str(repo), "log", "--format=%H", "-p", range_],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=GIT_ENV)
        r = subprocess.run(["git", "-C", str(repo), "patch-id", "--stable"], stdin=log.stdout,
                           capture_output=True, text=True, timeout=timeout, env=GIT_ENV)
        log.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        try:
            log.kill()
        except Exception:
            pass
        return None
    finally:
        if TRACE and time.time() - t0 > 1:
            print(f"    [{time.time() - t0:5.1f} s] patch-id {Path(repo).name} {range_[:60]}", file=sys.stderr)
    if r.returncode != 0:
        return None
    return {line.split()[0] for line in r.stdout.splitlines() if line.strip()}


class ContentIndex:
    """Par (dépôt, branche d'intégration) : patch-id des commits de l'intégration depuis la
    divergence la plus ancienne demandée — calculés UNE fois par dépôt et non par branche
    (`git cherry` refaisait ce travail pour chacune : 5 s × 39 branches sur dolibarr)."""

    def __init__(self, repo: Path, up: str):
        self.repo, self.up, self.base, self.ids = repo, up, None, None

    def ensure(self, base: str) -> bool:
        if self.ids is not None and (self.base == base or
                                     git(["merge-base", "--is-ancestor", self.base, base], self.repo).returncode == 0):
            return True
        ids = patch_ids(self.repo, f"{base}..{self.up}")
        if ids is None:
            return False
        self.base, self.ids = base, ids
        return True


_INDEX: dict[tuple[str, str], ContentIndex] = {}


def missing_count(repo: Path, integ: list[str], ref: str) -> tuple[int, bool]:
    """(commits de `ref` absents de l'intégration, vérifié par contenu ?). Ancêtre d'abord (rapide) ;
    par contenu ensuite (patch-id, équivalent de `git cherry` : un cherry-pick compte comme intégré),
    sauf si l'intégration a trop avancé depuis la divergence, ou si la branche elle-même a trop de
    commits propres à diffuser (`CHERRY_MAX` des deux côtés — vieux fork jamais rebasé sur un dépôt
    énorme : le coût de `patch-id` est proportionnel au nombre de commits, pas à leur ancienneté),
    ou si le calcul échoue — on rend alors le compte par ancêtre, signalé comme tel."""
    ahead = {}
    for up in integ:                                   # la principale d'abord : 0 ⇒ inutile d'aller plus loin
        ahead[up] = ahead_count(repo, up, ref)
        if ahead[up] == 0:
            return 0, True
    best_up = min(ahead, key=lambda u: ahead[u] if ahead[u] >= 0 else 10**9)
    mb = git(["merge-base", best_up, ref], repo).stdout.strip()
    behind = ahead_count(repo, ref, best_up) if mb else -1   # commits de l'intégration depuis la divergence
    if mb and 0 <= behind <= CHERRY_MAX and 0 <= ahead[best_up] <= CHERRY_MAX:
        idx = _INDEX.setdefault((str(repo), best_up), ContentIndex(repo, best_up))
        mine = patch_ids(repo, f"{best_up}..{ref}", timeout=60)
        if mine is not None and idx.ensure(mb):
            return len(mine - idx.ids), True
    return max(ahead[best_up], 0), False


def last_commit_date(repo: Path, ref: str) -> str:
    r = git(["log", "-1", "--format=%cs", ref], repo)
    return r.stdout.strip() if r.returncode == 0 else "?"


# ----------------------------------------------------------------------------- PM / forge
def task_info(cfg, rm_id: int) -> dict:
    """{status, mr_urls} lus dans le frontmatter de la fiche RM<id> (None/[] si inconnue)."""
    tf = cfg.find_task(rm_id)
    if not tf:
        return {"status": None, "mr_urls": []}
    m = FM_RE.search(tf.read_text(encoding="utf-8", errors="replace"))
    fm = m.group(1) if m else ""
    st = re.search(r"^status:\s*(\S+)", fm, re.MULTILINE)
    urls = []
    for u in MR_URL_RE.findall(fm):
        u = u.rstrip("'\"")
        if u not in urls:
            urls.append(u)
    return {"status": st.group(1) if st else None, "mr_urls": urls}


def _fetch_mr_state(url: str) -> dict:
    """État réel d'une MR par l'API de la forge (pm_forge). Jamais d'exception :
    {"state": opened|merged|closed|locked, "iid", "source", "target", "merged_at"} ou {"error"}."""
    try:
        from pm_forge import get_forge_from_pr_url
        forge, iid = get_forge_from_pr_url(url)
        token = forge.token("worker")
        project = forge.resolve_project(token)
        pr = forge.get_pr(project, iid, token)
        return {"state": pr.state, "iid": pr.iid, "source": pr.source, "target": pr.target,
                "merged_at": (pr.raw or {}).get("merged_at")}
    except Exception as e:  # réseau, token absent, forge inconnue… → repli sur le ticket
        return {"error": str(e).splitlines()[0][:120] if str(e) else type(e).__name__}


_MR_CACHE: dict[str, dict] = {}


def mr_state(url: str, enabled: bool) -> dict:
    if not enabled:
        return {"error": "forge non interrogée (--no-forge)"}
    if url not in _MR_CACHE:
        _MR_CACHE[url] = _fetch_mr_state(url)
    return _MR_CACHE[url]


def branch_severity(short: str, n: int, rm_id, ti: dict, use_forge: bool) -> tuple[str, str, dict]:
    """(gravité, explication, mr_info) pour une branche avec `n` commits non intégrés."""
    mrs = [dict(mr_state(u, use_forge), url=u) for u in ti["mr_urls"]]
    known = [m for m in mrs if "state" in m and (not m.get("source") or m["source"] == short)]
    if not known:  # aucune MR sur CETTE branche : on prend celles du ticket telles quelles
        known = [m for m in mrs if "state" in m]
    opened = [m for m in known if m["state"] in ("opened", "locked")]
    merged = [m for m in known if m["state"] == "merged"]
    closed = [m for m in known if m["state"] == "closed"]
    info = {"mr": known[0]["url"] if known else (ti["mr_urls"][0] if ti["mr_urls"] else None)}
    if opened:
        return LOW, f"MR !{opened[0]['iid']} ouverte", dict(info, mr=opened[0]["url"], mr_state="opened")
    if merged:
        when = (merged[0].get("merged_at") or "")[:10]
        return HIGH, (f"MR !{merged[0]['iid']} mergée{' le ' + when if when else ''} — "
                      f"{n} commit(s) postérieurs au merge (cas RM2264)"), dict(info, mr=merged[0]["url"], mr_state="merged")
    if closed:
        return MED, f"MR !{closed[0]['iid']} fermée sans merge", dict(info, mr=closed[0]["url"], mr_state="closed")
    # pas d'état de MR connu → le ticket décide
    if ti["status"] in CLOSED_LIKE:
        return HIGH, f"ticket {ti['status']} — commits postérieurs au merge ? (cas RM2264)", info
    if not ti["mr_urls"]:
        return MED, ("aucune MR renseignée sur le ticket" if rm_id else "branche sans ticket"), info
    err = next((m["error"] for m in mrs if "error" in m), "")
    return LOW, f"MR renseignée, état non vérifié ({err})", dict(info, mr_state=None)


# ----------------------------------------------------------------------------- envs
def dirty_files(wt: Path) -> list[tuple[str, float]]:
    """[(chemin, âge en jours)] des fichiers modifiés / non suivis d'un worktree."""
    r = git(["status", "--porcelain", "--untracked-files=normal"], wt)
    out = []
    now = time.time()
    for line in r.stdout.splitlines():
        rel = line[3:].strip().strip('"')
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        p = wt / rel
        try:
            age = (now - p.stat().st_mtime) / 86400.0 if p.exists() else 0.0
        except OSError:
            age = 0.0
        out.append((rel, age))
    return out


def worktrees(bare: Path) -> list[dict]:
    out = git(["worktree", "list", "--porcelain"], bare).stdout
    entries, cur = [], {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                entries.append(cur)
            cur = {"path": line.split(" ", 1)[1]}
        elif line == "bare":
            cur["bare"] = True
        elif line.startswith("branch "):
            cur["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
    if cur:
        entries.append(cur)
    return [e for e in entries if not e.get("bare")]


def discover_workspaces(only: str | None, root: Path = WORKSPACES_ROOT) -> list[Path]:
    ws = []
    for client in sorted(root.iterdir()):
        if not client.is_dir() or client.name.startswith("."):
            continue
        for proj in sorted(client.iterdir()):
            if not proj.is_dir() or not (proj / ".mmi-pm").exists():
                continue
            if only and f"{client.name}/{proj.name}" != only:
                continue
            ws.append(proj)
    return ws


def repos_of(ws: Path) -> list[tuple[Path, str]]:
    """[(repo git à interroger, libellé)] : bares du layout RM1993, ou la racine (legacy)."""
    if (ws / "repos").is_dir():
        return [(b, b.name) for b in sorted((ws / "repos").glob("*.git"))]
    if (ws / ".git").exists():
        return [(ws, ws.name)]
    return []


def audit_repo(cfg, ws: Path, repo: Path, label: str, fetch: bool, max_age: float,
               use_forge: bool = True, all_branches: bool = False) -> list[dict]:
    findings: list[dict] = []
    wsname = f"{ws.parent.name}/{ws.name}"

    def add(kind, sev, what, key=None, **extra):
        findings.append({"workspace": wsname, "repo": label, "type": kind, "gravite": sev, "quoi": what,
                         "cle": f"{kind}|{label}|{key or what}", **extra})

    if fetch:
        r = git(["fetch", "--prune", "--quiet", "origin"], repo, timeout=120)
        if r.returncode != 0:
            add("REMOTE", MED, f"fetch impossible : {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'erreur'}",
                key="fetch")
    integ = integration_refs(repo)
    if not integ:
        add("REMOTE", LOW, "aucune branche d'intégration connue (origin/dev|main|master)", key="integration")
        return findings
    # 1. branches (distantes + locales) avec des commits absents par contenu de l'intégration
    seen = set()
    hors_convention = 0
    # un seul parcours par branche d'intégration (`--no-merged`) au lieu d'un rev-list par branche :
    # ne restent que les refs non contenues dans AUCUNE intégration
    refs = None
    for up in integ:
        names = git(["for-each-ref", f"--no-merged={up}", "--format=%(refname:short)",
                     "refs/remotes/origin", "refs/heads"], repo, timeout=120).stdout.split()
        refs = names if refs is None else [r for r in refs if r in set(names)]
    for ref in refs or []:
        short = ref.replace("origin/", "")
        if short in ("HEAD", *INTEGRATION_NAMES) or ref.endswith("/HEAD"):
            continue
        if short in seen:                      # la locale après la distante : même nom, on ne teste qu'une fois
            continue
        seen.add(short)
        if not all_branches and ref.startswith("origin/") and not TICKET_RE.match(short):
            hors_convention += 1               # miroir amont, release… : compté, pas parcouru (coût)
            continue
        n, by_content = missing_count(repo, integ, ref)
        if n <= 0:
            continue
        m = TICKET_RE.match(short)
        rm_id = int(m.group(1)) if m else None
        ti = task_info(cfg, rm_id) if rm_id else {"status": None, "mr_urls": []}
        sev, why, mr = branch_severity(short, n, rm_id, ti, use_forge)
        how = "" if by_content else " (par ancêtre, contenu non vérifié)"
        add("BRANCHE", sev, f"{ref} : {n} commit(s) absents de {'/'.join(i.replace('origin/', '') for i in integ)}{how} — {why}",
            key=short, branche=ref, commits=n, par_contenu=by_content, dernier=last_commit_date(repo, ref),
            ticket=rm_id, statut=ti["status"], **mr)
    if hors_convention:
        add("BRANCHE", LOW, f"{hors_convention} branche(s) distante(s) hors convention RM non examinée(s) (--all-branches)",
            key="hors-convention")
    # 2. stash oubliés — `git stash list` se tait dans un bare (« must be run in a work tree ») :
    # on lit le reflog de refs/stash, partagé par tous les worktrees du dépôt.
    if ref_exists(repo, "refs/stash"):
        st = git(["log", "-g", "--format=%cs %gs", "refs/stash"], repo).stdout.strip().splitlines()
        if st:
            oldest = min(l[:10] for l in st)
            add("STASH", MED, f"{len(st)} entrée(s) de stash (la plus ancienne : {oldest}) — dernière : {st[0][11:80]}",
                key="stash", entrees=len(st), plus_ancienne=oldest)
    # 3. worktrees : fichiers sales, intégration en retard, tickets fermés
    for wt in worktrees(repo):
        path = Path(wt["path"])
        if not path.exists():
            add("FERMÉ", LOW, f"worktree fantôme (dossier absent) : {path.name} → `git worktree prune`", key=path.name)
            continue
        branch = wt.get("branch", "(détaché)")
        dirty = dirty_files(path)
        if dirty:
            oldest = max(a for _, a in dirty)
            sev = HIGH if oldest > max_age * 3 else (MED if oldest > max_age else LOW)
            add("SALE", sev, f"{path.name} ({branch}) : {len(dirty)} fichier(s) non commités, le plus ancien a {oldest:.0f} j",
                key=path.name, worktree=path.name, fichiers=len(dirty), age_max_j=round(oldest, 1))
        if branch in INTEGRATION_NAMES and ref_exists(repo, f"origin/{branch}"):
            behind = git(["rev-list", "--count", f"{branch}..origin/{branch}"], repo).stdout.strip()
            if behind and behind != "0":
                add("RETARD", MED if int(behind) > 20 else LOW,
                    f"{path.name} : `{branch}` en retard de {behind} commit(s) sur origin/{branch}", key=path.name)
        m = TICKET_RE.match(branch)
        if m and task_info(cfg, int(m.group(1))).get("status") == "ferme":
            head = git(["rev-parse", "HEAD"], path).stdout.strip()
            integrated = any(git(["merge-base", "--is-ancestor", head, up], repo).returncode == 0 for up in integ)
            if dirty:
                add("FERMÉ", HIGH, f"{path.name} : ticket RM{m.group(1)} fermé mais {len(dirty)} modif(s) non commitée(s) — "
                    f"à récupérer (commit + MR) ou à jeter avant nettoyage", key=path.name, nettoyable=False)
            elif not integrated:
                add("FERMÉ", MED, f"{path.name} : ticket RM{m.group(1)} fermé, commits non intégrés (voir BRANCHE) — "
                    f"nettoyage après merge", key=path.name, nettoyable=False)
            else:
                add("FERMÉ", LOW, f"{path.name} : ticket RM{m.group(1)} fermé, env obsolète (propre, intégré) → "
                    f"`pm-env-gc --apply --workspace {ws}`", key=path.name, nettoyable=True)
    return findings


# ----------------------------------------------------------------------------- consignation par projet
HISTORY_HEADER = (
    "# Audits des environnements\n\n"
    "Une ligne par contrôle `pm-env-audit` (RM3163). Le détail n'est écrit que s'il y a une anomalie ou un\n"
    "changement depuis le contrôle précédent. Δ = anomalies nouvelles / résolues.\n\n"
    "| Date | Fetch | ÉLEVÉE | moyenne | info | Δ | Détail |\n"
    "|---|---|---|---|---|---|---|\n")


def audit_dir(ws: Path) -> Path:
    return (ws / ".mmi-pm").resolve() / AUDIT_DIRNAME


def consign_workspace(ws: Path, findings: list[dict], when: datetime, fetch: bool,
                      commit: bool = True) -> dict:
    """Écrit history.md (+ détail si utile) dans le core du projet et le committe. Retourne
    {"nouvelles": [...], "resolues": [...], "detail": Path|None}."""
    d = audit_dir(ws)
    d.mkdir(parents=True, exist_ok=True)
    last_p, hist_p = d / "last.json", d / "history.md"
    prev = None
    if last_p.exists():
        try:
            prev = json.loads(last_p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = None
    keys = {f["cle"]: f for f in findings}
    prev_keys = set(prev.get("cles", [])) if prev else set()
    nouvelles = sorted(k for k in keys if k not in prev_keys)
    resolues = sorted(k for k in prev_keys if k not in keys)
    changed = prev is None or bool(nouvelles or resolues)
    grav = {k: sum(1 for f in findings if f["gravite"] == k) for k in (HIGH, MED, LOW)}
    stamp = when.strftime("%Y-%m-%d_%H%M")
    date_h = when.strftime("%Y-%m-%d %H:%M")
    detail_p = None
    paths = [hist_p, last_p]
    if findings or changed:
        detail_p = d / f"{stamp}.md"
        lines = [f"# Audit des environnements — {date_h}", "",
                 f"Workspace `{ws.parent.name}/{ws.name}` — {'avec' if fetch else 'sans'} fetch — "
                 f"{len(findings)} anomalie(s) : {grav[HIGH]} élevée(s), {grav[MED]} moyenne(s), {grav[LOW]} info.", ""]
        if findings:
            lines += ["## Anomalies", "", "| Gravité | Type | Dépôt | Quoi |", "|---|---|---|---|"]
            for f in sorted(findings, key=lambda f: (ORDER[f["gravite"]], f["type"], f["repo"])):
                mr = f" — MR : {f['mr']}" if f.get("mr") else ""
                lines.append(f"| {f['gravite']} | {f['type']} | {f['repo']} | {f['quoi'].replace('|', '¦')}{mr} |")
            lines.append("")
        prev_date = prev.get("date") if prev else None
        lines += [f"## Depuis l'audit précédent ({prev_date or 'aucun'})", ""]
        if not prev:
            lines.append("Premier audit consigné dans ce projet.")
        elif not nouvelles and not resolues:
            lines.append("Aucun changement.")
        else:
            for k in nouvelles:
                lines.append(f"- **nouvelle** : {keys[k]['quoi'].replace('|', '¦')}")
            for k in resolues:
                lines.append(f"- résolue : {prev.get('libelles', {}).get(k, k)}")
        lines.append("")
        detail_p.write_text("\n".join(lines), encoding="utf-8")
        paths.append(detail_p)
    if not hist_p.exists():
        hist_p.write_text(HISTORY_HEADER, encoding="utf-8")
    delta = f"+{len(nouvelles)} / −{len(resolues)}" if prev else "premier"
    link = f"[détail]({detail_p.name})" if detail_p else "—"
    with hist_p.open("a", encoding="utf-8") as fh:
        fh.write(f"| {date_h} | {'oui' if fetch else 'non'} | {grav[HIGH]} | {grav[MED]} | {grav[LOW]} | {delta} | {link} |\n")
    last_p.write_text(json.dumps({"date": date_h, "cles": sorted(keys), "par_gravite": grav,
                                  "libelles": {k: f["quoi"] for k, f in keys.items()}},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    if commit:
        try:
            from pm_git import autocommit
            autocommit(paths, f"pm(env-audit): {date_h} {len(findings)} anomalie(s) "
                              f"({grav[HIGH]} élevée(s), {delta})")
        except Exception as e:  # la consignation ne doit jamais faire échouer l'audit
            print(f"⚠ {ws.parent.name}/{ws.name} : commit de l'audit impossible ({e})", file=sys.stderr)
    return {"nouvelles": [keys[k]["quoi"] for k in nouvelles],
            "resolues": [prev.get("libelles", {}).get(k, k) for k in resolues] if prev else [],
            "detail": detail_p}


def last_of_workspace(ws: Path) -> str | None:
    hist = audit_dir(ws) / "history.md"
    if not hist.exists():
        return None
    rows = [l for l in hist.read_text(encoding="utf-8").splitlines() if l.startswith("| 20")]
    return rows[-1] if rows else None


# ----------------------------------------------------------------------------- synthèse globale (repo PM)
def history_path(cfg) -> Path:
    root = Path(getattr(cfg, "pm_dir", Path(__file__).resolve().parent.parent))
    p = root / "var" / AUDIT_DIRNAME / "history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def show_last(cfg, workspace: str | None) -> int:
    if workspace:
        wss = discover_workspaces(workspace)
        if not wss:
            print(f"workspace inconnu : {workspace}")
            return 1
        row = last_of_workspace(wss[0])
        if not row:
            print(f"{workspace} : aucun audit consigné — lancer `pm-env-audit.py --fetch --workspace {workspace}`")
            return 1
        date = row.split("|")[1].strip()
        age = (datetime.now() - datetime.strptime(date, "%Y-%m-%d %H:%M")).days
        print(f"{workspace} — dernier audit : {date} (il y a {age} j) — {audit_dir(wss[0]) / 'history.md'}")
        print(f"  {row}")
        if age > 7:
            print("⚠ plus de 7 jours : audit hebdomadaire à relancer")
        return 0
    p = history_path(cfg)
    if not p.exists() or not p.read_text().strip():
        print("aucun audit enregistré — lancer `pm-env-audit.py --fetch`")
        return 1
    last = json.loads(p.read_text().strip().splitlines()[-1])
    age = (datetime.now() - datetime.fromisoformat(last["date"])).days
    print(f"dernier audit : {last['date']} (il y a {age} j) — {last['workspaces']} workspace(s), "
          f"{last['anomalies']} anomalie(s) : {last['par_gravite']}"
          f"{' — ' + str(last['duree_s']) + ' s' if last.get('duree_s') is not None else ''}")
    if age > 7:
        print("⚠ plus de 7 jours : audit hebdomadaire à relancer")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit hebdomadaire des environnements (RM3163)")
    ap.add_argument("--workspace", help="client/projet — sinon tous")
    ap.add_argument("--fetch", action="store_true", help="git fetch --prune sur chaque repo avant l'audit")
    ap.add_argument("--max-age", type=float, default=7.0, help="âge (jours) au-delà duquel un fichier non commité est signalé")
    ap.add_argument("--no-forge", action="store_true", help="ne pas interroger la forge (gravité d'après le ticket seul)")
    ap.add_argument("--all-branches", action="store_true",
                    help="examiner par contenu TOUTES les branches distantes (défaut : branches de tickets et locales)")
    ap.add_argument("--no-consign", action="store_true", help="ne rien écrire dans les projets (ni commit)")
    ap.add_argument("--no-commit", action="store_true", help="consigner dans les projets sans committer")
    ap.add_argument("--no-history", action="store_true", help="ne rien enregistrer nulle part (essai)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--last", action="store_true", help="date et bilan du dernier audit (global, ou du --workspace)")
    ap.add_argument("-v", "--verbose", action="store_true", help="progression et durée par workspace (stderr)")
    args = ap.parse_args()
    cfg = PMConfig.load()
    if args.last:
        return show_last(cfg, args.workspace)
    when = datetime.now()
    t0 = time.time()
    findings: list[dict] = []
    deltas: dict[str, dict] = {}
    wss = discover_workspaces(args.workspace)
    consign = not (args.no_consign or args.no_history)
    for ws in wss:
        tw = time.time()
        fw: list[dict] = []
        for repo, label in repos_of(ws):
            fw.extend(audit_repo(cfg, ws, repo, label, args.fetch, args.max_age,
                                 use_forge=not args.no_forge, all_branches=args.all_branches))
        findings.extend(fw)
        name = f"{ws.parent.name}/{ws.name}"
        if consign:
            deltas[name] = consign_workspace(ws, fw, when, args.fetch, commit=not args.no_commit)
        if args.verbose:
            print(f"· {name:<40} {len(fw):>2} anomalie(s)  {time.time() - tw:5.1f} s", file=sys.stderr)
    findings.sort(key=lambda f: (ORDER[f["gravite"]], f["workspace"], f["type"]))
    par_grav = {k: sum(1 for f in findings if f["gravite"] == k) for k in (HIGH, MED, LOW)}
    nouvelles = sum(len(d["nouvelles"]) for d in deltas.values())
    resolues = sum(len(d["resolues"]) for d in deltas.values())
    entry = {"date": when.isoformat(timespec="minutes"), "workspaces": len(wss), "fetch": args.fetch,
             "duree_s": round(time.time() - t0, 1),
             "anomalies": len(findings), "par_gravite": par_grav,
             "par_type": {t: sum(1 for f in findings if f["type"] == t) for t in sorted({f["type"] for f in findings})},
             "nouvelles": nouvelles, "resolues": resolues,
             "elevees": [f"{f['workspace']} {f['repo']} : {f['quoi']}" for f in findings if f["gravite"] == HIGH][:20]}
    if not args.no_history:
        with history_path(cfg).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if args.json:
        print(json.dumps({"bilan": entry, "anomalies": findings,
                          "changements": {k: {"nouvelles": v["nouvelles"], "resolues": v["resolues"]}
                                          for k, v in deltas.items() if v["nouvelles"] or v["resolues"]}},
                         ensure_ascii=False, indent=2))
    else:
        print(f"Audit des environnements — {entry['date']} — {len(wss)} workspace(s), {entry['duree_s']} s"
              f"{' (fetch)' if args.fetch else ' (refs locales : lancer --fetch pour un vrai point)'}")
        if not findings:
            print("  ✓ rien à signaler")
        for f in findings:
            print(f"  [{f['gravite']:<7}] {f['type']:<7} {f['workspace']:<34} {f['repo']:<28} {f['quoi']}")
        if consign:
            print(f"\nDepuis l'audit précédent : {nouvelles} nouvelle(s), {resolues} résolue(s)")
            for name, d in deltas.items():
                for q in d["nouvelles"]:
                    print(f"  + {name:<34} {q}")
                for q in d["resolues"]:
                    print(f"  − {name:<34} {q}")
        nettoyables = sorted({f["workspace"] for f in findings if f.get("nettoyable")})
        if nettoyables:
            print(f"\nEnvs obsolètes (ticket fermé, propre, intégré) : "
                  f"{sum(1 for f in findings if f.get('nettoyable'))} dans {len(nettoyables)} workspace(s) "
                  f"→ `pm-env-gc --all` (dry-run) puis `pm-env-gc --all --apply`")
        print(f"\n{len(findings)} anomalie(s) : {par_grav}"
              f"{' — consigné dans <workspace>/.mmi-pm/' + AUDIT_DIRNAME + '/' if consign else ''}"
              f" — synthèse : {history_path(cfg)}")
    return 2 if par_grav[HIGH] else 0


if __name__ == "__main__":
    sys.exit(main())
