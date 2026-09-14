#!/usr/bin/env python3
"""pm-env-audit — audit hebdomadaire de TOUS les environnements (RM3163).

Incident fondateur (2026-09-14, calyclay/calymix) : 7 commits poussés sur la branche RM2264
**après** le merge de sa MR, et un document de RM1937 (juillet), n'ont jamais atteint `master`.
Personne ne l'a vu pendant un mois : les branches suivantes sont parties sans, une correction
validée est « revenue », des docs périmés ont dû être repris à la main. Décision Mathieu : un
audit **outillé, hebdomadaire, avec historique des contrôles**.

Ce que l'audit signale, pour chaque workspace PM-tracké (`/zfs/workspaces/<client>/<projet>/`,
layout RM1993 `repos/*.git` + `envs/*`, ou layout historique = un repo à la racine) :

  BRANCHE   commits présents sur une branche (locale ou distante) et **absents PAR CONTENU** de
            la branche d'intégration (`git cherry`, pas seulement l'ancêtre — un cherry-pick
            compte comme intégré). Gravité selon le ticket : fermé / en MEP → ÉLEVÉE (le cas
            RM2264 : MR mergée, commits postérieurs oubliés) ; sans MR connue → moyenne ;
            MR renseignée et ticket ouvert → info (MR probablement ouverte, normal).
  SALE      fichiers non commités dans un env, avec l'âge du plus ancien (mtime) —
            alerte au-delà de `--max-age` jours (défaut 7).
  RETARD    branche d'intégration locale en retard sur le remote.
  STASH     entrées de stash oubliées dans le bare.
  FERMÉ     worktree d'un ticket `ferme` encore présent → `pm-env-gc`.
  REMOTE    fetch impossible (remote injoignable ou clé absente) — avec `--fetch`.

Chaque exécution écrit une entrée dans `var/env-audit/history.jsonl` (racine du repo PM) :
date, périmètre, compte d'anomalies par type et gravité — `--last` montre le dernier contrôle
et son ancienneté. Code retour : 0 = rien d'élevé, 2 = au moins une anomalie ÉLEVÉE.

Usage :
    pm-env-audit.py                      # tous les workspaces, refs locales (rapide)
    pm-env-audit.py --fetch              # rafraîchit origin/* d'abord (recommandé, hebdo)
    pm-env-audit.py --workspace calyclay/calymix
    pm-env-audit.py --last               # date et bilan du dernier audit
    pm-env-audit.py --json               # sortie machine
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
INTEGRATION_CANDIDATES = ("origin/dev", "origin/main", "origin/master")
CLOSED_LIKE = {"ferme", "a_mep", "en_mep"}
HIGH, MED, LOW = "ÉLEVÉE", "moyenne", "info"


def git(args, cwd, timeout=60):
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "timeout")


def ref_exists(repo: Path, ref: str) -> bool:
    return git(["rev-parse", "--verify", "-q", ref + "^{commit}"], repo).returncode == 0


def integration_refs(repo: Path) -> list[str]:
    return [r for r in INTEGRATION_CANDIDATES if ref_exists(repo, r)]


def cherry_count(repo: Path, upstream: str, branch: str) -> int:
    """Nombre de commits de `branch` absents PAR CONTENU de `upstream` (git cherry)."""
    r = git(["cherry", upstream, branch], repo)
    if r.returncode != 0:
        return -1
    return sum(1 for line in r.stdout.splitlines() if line.startswith("+"))


def last_commit_date(repo: Path, ref: str) -> str:
    r = git(["log", "-1", "--format=%cs", ref], repo)
    return r.stdout.strip() if r.returncode == 0 else "?"


def task_info(cfg: PMConfig, rm_id: int) -> dict:
    tf = cfg.find_task(rm_id)
    if not tf:
        return {"status": None, "mr": None}
    m = FM_RE.search(tf.read_text(encoding="utf-8", errors="replace"))
    fm = m.group(1) if m else ""
    st = re.search(r"^status:\s*(\S+)", fm, re.MULTILINE)
    mr = re.search(r"^\s*mr_url:\s*(\S+)", fm, re.MULTILINE)
    return {"status": st.group(1) if st else None,
            "mr": None if (not mr or mr.group(1) in ("null", "''", '""')) else mr.group(1)}


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


def discover_workspaces(only: str | None) -> list[Path]:
    ws = []
    for client in sorted(WORKSPACES_ROOT.iterdir()):
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


def audit_repo(cfg: PMConfig, ws: Path, repo: Path, label: str, fetch: bool, max_age: float) -> list[dict]:
    findings: list[dict] = []
    wsname = f"{ws.parent.name}/{ws.name}"

    def add(kind, sev, what, **extra):
        findings.append({"workspace": wsname, "repo": label, "type": kind, "gravite": sev, "quoi": what, **extra})

    if fetch:
        r = git(["fetch", "--prune", "--quiet", "origin"], repo, timeout=120)
        if r.returncode != 0:
            add("REMOTE", MED, f"fetch impossible : {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'erreur'}")
    integ = integration_refs(repo)
    if not integ:
        add("REMOTE", LOW, "aucune branche d'intégration connue (origin/dev|main|master)")
        return findings
    # 1. branches (distantes + locales) avec des commits absents par contenu de l'intégration
    seen = set()
    refs = git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin", "refs/heads"], repo).stdout.split()
    for ref in refs:
        short = ref.replace("origin/", "")
        if short in ("HEAD", "dev", "main", "master") or ref.endswith("/HEAD"):
            continue
        if short in seen:                      # la locale et la distante portent le même contenu ? on ne teste que la distante d'abord
            continue
        seen.add(short)
        # on compare la branche à CHAQUE intégration et on garde le plus petit écart
        n = min((cherry_count(repo, up, ref) for up in integ), default=-1)
        if n <= 0:
            continue
        m = TICKET_RE.match(short)
        rm_id = int(m.group(1)) if m else None
        ti = task_info(cfg, rm_id) if rm_id else {"status": None, "mr": None}
        if ti["status"] in CLOSED_LIKE:
            sev, why = HIGH, f"ticket {ti['status']} — commits postérieurs au merge ? (cas RM2264)"
        elif not ti["mr"]:
            sev, why = MED, "aucune MR renseignée sur le ticket" if rm_id else "branche sans ticket"
        else:
            sev, why = LOW, "MR renseignée (probablement ouverte)"
        add("BRANCHE", sev, f"{ref} : {n} commit(s) absents de {'/'.join(i.replace('origin/', '') for i in integ)} — {why}",
            branche=ref, commits=n, dernier=last_commit_date(repo, ref), ticket=rm_id, statut=ti["status"], mr=ti["mr"])
    # 2. stash oubliés
    st = git(["stash", "list"], repo).stdout.strip().splitlines()
    if st:
        add("STASH", MED, f"{len(st)} entrée(s) de stash : {st[0][:80]}")
    # 3. worktrees : fichiers sales, intégration en retard, tickets fermés
    for wt in worktrees(repo):
        path = Path(wt["path"])
        if not path.exists():
            add("FERMÉ", LOW, f"worktree fantôme (dossier absent) : {path.name} → `git worktree prune`")
            continue
        branch = wt.get("branch", "(détaché)")
        dirty = dirty_files(path)
        if dirty:
            oldest = max(a for _, a in dirty)
            sev = HIGH if oldest > max_age * 3 else (MED if oldest > max_age else LOW)
            add("SALE", sev, f"{path.name} ({branch}) : {len(dirty)} fichier(s) non commités, le plus ancien a {oldest:.0f} j",
                worktree=path.name, fichiers=len(dirty), age_max_j=round(oldest, 1))
        if branch in ("dev", "main", "master") and ref_exists(repo, f"origin/{branch}"):
            behind = git(["rev-list", "--count", f"{branch}..origin/{branch}"], repo).stdout.strip()
            if behind and behind != "0":
                add("RETARD", MED if int(behind) > 20 else LOW, f"{path.name} : `{branch}` en retard de {behind} commit(s) sur origin/{branch}")
        m = TICKET_RE.match(branch)
        if m and task_info(cfg, int(m.group(1)))["status"] == "ferme":
            add("FERMÉ", LOW, f"{path.name} : ticket RM{m.group(1)} fermé, worktree encore présent → `pm-env-gc`")
    return findings


def history_path(cfg: PMConfig) -> Path:
    root = Path(getattr(cfg, "pm_dir", Path(__file__).resolve().parent.parent))
    p = root / "var" / "env-audit" / "history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def show_last(cfg: PMConfig) -> int:
    p = history_path(cfg)
    if not p.exists() or not p.read_text().strip():
        print("aucun audit enregistré — lancer `pm-env-audit.py --fetch`")
        return 1
    last = json.loads(p.read_text().strip().splitlines()[-1])
    age = (datetime.now() - datetime.fromisoformat(last["date"])).days
    print(f"dernier audit : {last['date']} (il y a {age} j) — {last['workspaces']} workspace(s), "
          f"{last['anomalies']} anomalie(s) : {last['par_gravite']}")
    if age > 7:
        print("⚠ plus de 7 jours : audit hebdomadaire à relancer")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit hebdomadaire des environnements (RM3163)")
    ap.add_argument("--workspace", help="client/projet — sinon tous")
    ap.add_argument("--fetch", action="store_true", help="git fetch --prune sur chaque repo avant l'audit")
    ap.add_argument("--max-age", type=float, default=7.0, help="âge (jours) au-delà duquel un fichier non commité est signalé")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--last", action="store_true", help="date et bilan du dernier audit")
    ap.add_argument("--no-history", action="store_true", help="ne pas enregistrer ce contrôle")
    args = ap.parse_args()
    cfg = PMConfig.load()
    if args.last:
        return show_last(cfg)
    findings: list[dict] = []
    wss = discover_workspaces(args.workspace)
    for ws in wss:
        for repo, label in repos_of(ws):
            findings.extend(audit_repo(cfg, ws, repo, label, args.fetch, args.max_age))
    order = {HIGH: 0, MED: 1, LOW: 2}
    findings.sort(key=lambda f: (order[f["gravite"]], f["workspace"], f["type"]))
    par_grav = {k: sum(1 for f in findings if f["gravite"] == k) for k in (HIGH, MED, LOW)}
    entry = {"date": datetime.now().isoformat(timespec="minutes"), "workspaces": len(wss), "fetch": args.fetch,
             "anomalies": len(findings), "par_gravite": par_grav,
             "par_type": {t: sum(1 for f in findings if f["type"] == t) for t in sorted({f["type"] for f in findings})},
             "elevees": [f["quoi"] for f in findings if f["gravite"] == HIGH][:20]}
    if not args.no_history:
        with history_path(cfg).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if args.json:
        print(json.dumps({"bilan": entry, "anomalies": findings}, ensure_ascii=False, indent=2))
    else:
        print(f"Audit des environnements — {entry['date']} — {len(wss)} workspace(s)"
              f"{' (fetch)' if args.fetch else ' (refs locales : lancer --fetch pour un vrai point)'}")
        if not findings:
            print("  ✓ rien à signaler")
        for f in findings:
            print(f"  [{f['gravite']:<7}] {f['type']:<7} {f['workspace']:<34} {f['repo']:<28} {f['quoi']}")
        print(f"\n{len(findings)} anomalie(s) : {par_grav} — historique : {history_path(cfg)}")
    return 2 if par_grav[HIGH] else 0


if __name__ == "__main__":
    sys.exit(main())
