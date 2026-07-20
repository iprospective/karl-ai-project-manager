#!/usr/bin/env python3
"""pm_git — auto-commit + push atomiques des écritures des scripts pm-* (RM1834 piste A).

Principe : chaque script pm-* sait EXACTEMENT quels fichiers il vient d'écrire
(RM<id>.md, .log.md…). Ce module les committe et les pousse atomiquement dans
leur repo (ai-projects en général), pour que plus personne n'ait à stager à la
main dans un arbre de travail partagé entre sessions (cause racine RM1834 ;
incident du add-trop-large 2026-06-12 en démonstration).

Garanties :
  - `git commit -m <msg> -- <chemins>` : le commit n'inclut QUE les chemins
    nommés — un fichier stagé par une session concurrente ne peut pas embarquer.
  - Verrou local (flock sur .git/pm-autocommit.lock, timeout 30 s) : sérialise
    les invocations concurrentes des scripts pm-* sur la machine.
  - NON-FATAL : aucun échec (pas un repo git, rien à committer, push rejeté…)
    ne casse l'opération principale du script appelant — warning et on continue.
  - Push rejeté (remote a avancé : instance fédérée) : le commit local est
    conservé, le prochain auto-push l'emportera ; on ne tente JAMAIS de
    rebase/merge dans l'arbre partagé dirty.

Config (pm.config.yml :: git, overridable via pm.config.local.yml) :
  git:
    autocommit: true   # false = désactive tout (les scripts n'auto-committent plus)
    autopush:   true   # false = commit local seulement

Usage côté script :
    import pm_git
    pm_git.autocommit([md_path, log_path], f"pm(status): RM{rm_id} -> {status}")
"""
import fcntl
import subprocess
import sys
import time
from pathlib import Path

LOCK_TIMEOUT_S = 30


def _run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _warn(msg):
    try:
        from pm_output import out
        out.warn(f"auto-commit : {msg}")
    except Exception:
        print(f"  ⚠ auto-commit : {msg}", file=sys.stderr)


def _push_error_kind(stderr):
    """RM2298 — classe un échec de push pour un diagnostic honnête :
    'protected' : branche protégée / pre-receive (ne se résoudra JAMAIS seul) ;
    'non_ff'    : le remote a avancé (fédération) — un prochain push l'emportera ;
    'other'     : réseau, auth, etc."""
    s = stderr or ""
    if "pre-receive hook declined" in s or "protected branch" in s.lower():
        return "protected"
    if "non-fast-forward" in s or "fetch first" in s or "Updates were rejected" in s:
        return "non_ff"
    return "other"


def load_git_config():
    """Section `git` de pm.config.yml (+ override pm.config.local.yml)."""
    try:
        import yaml
    except ImportError:
        return {"autocommit": True, "autopush": True, "integration_branch": "dev"}
    base = Path(__file__).resolve().parent.parent
    merged = {}
    for name in ("pm.config.yml", "pm.config.local.yml"):
        p = base / name
        if p.is_file():
            try:
                merged.update((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("git") or {})
            except (OSError, yaml.YAMLError):
                pass
    return {"autocommit": bool(merged.get("autocommit", True)),
            "autopush": bool(merged.get("autopush", True)),
            "integration_branch": str(merged.get("integration_branch", "dev") or "dev")}


def repo_root(path):
    """Racine du repo git contenant `path` (Path) ou None. Utile pour grouper par
    repo un lot de fichiers couvrant plusieurs workspaces (mode `--all`, RM2038)."""
    p = Path(path)
    start = p if p.is_dir() else p.parent
    r = _run(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def autocommit(paths, message, push=None, enabled=None):
    """Committe (et pousse) atomiquement les chemins listés. Retourne le sha court ou None.

    paths   : fichiers écrits par l'appelant (str|Path ; inexistants/None ignorés).
    message : message de commit (convention : `pm(<outil>): RM<id> <action>`).
    push    : force/désactive le push pour cet appel (None = config autopush).
    enabled : force/désactive l'auto-commit pour cet appel (None = config autocommit).
    """
    cfg = load_git_config()
    if not (cfg["autocommit"] if enabled is None else enabled):
        return None
    paths = [Path(p).resolve() for p in paths if p and Path(p).exists()]
    if not paths:
        return None

    root_r = _run(["git", "-C", str(paths[0].parent), "rev-parse", "--show-toplevel"])
    if root_r.returncode != 0:
        _warn(f"{paths[0].parent} n'est pas dans un repo git — skip")
        return None
    root = Path(root_r.stdout.strip())
    rel = []
    for p in paths:
        try:
            rel.append(str(p.relative_to(root)))
        except ValueError:
            _warn(f"{p} hors du repo {root} — ignoré")
    if not rel:
        return None

    lock_file = root / ".git" / "pm-autocommit.lock"
    try:
        lk = open(lock_file, "w")
    except OSError as e:
        _warn(f"verrou inaccessible ({e}) — skip")
        return None
    with lk:
        deadline = time.time() + LOCK_TIMEOUT_S
        while True:
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > deadline:
                    _warn(f"verrou occupé > {LOCK_TIMEOUT_S}s — skip (commit au prochain appel)")
                    return None
                time.sleep(0.4)

        if not _run(["git", "-C", str(root), "status", "--porcelain", "--"] + rel).stdout.strip():
            return None  # rien à committer (contenu identique)

        add = _run(["git", "-C", str(root), "add", "--"] + rel)
        if add.returncode != 0:
            _warn(f"git add a échoué : {add.stderr.strip()}")
            return None
        # `commit -- <chemins>` : n'embarque QUE ces chemins, même si d'autres
        # fichiers sont stagés par une session concurrente.
        c = _run(["git", "-C", str(root), "commit", "-m", message, "--"] + rel)
        if c.returncode != 0:
            _warn(f"git commit a échoué : {(c.stderr or c.stdout).strip()}")
            return None
        sha = _run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"]).stdout.strip()

        pushed = ""
        if cfg["autopush"] if push is None else push:
            p = _run(["git", "-C", str(root), "push"])
            if p.returncode == 0:
                pushed = " + push"
            else:
                kind = _push_error_kind(p.stderr)
                last = p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "raison inconnue"
                if kind == "protected":
                    # RM2298 : branche courante protégée (RM2030) — un push direct
                    # ne passera JAMAIS ; « le prochain l'emportera » était un faux
                    # diagnostic ici. Repli : pousser l'historique courant sur la
                    # branche d'intégration ; la promotion vers la branche protégée
                    # se fait par lot via pm-promote.py (MR auto-mergée).
                    integ = cfg["integration_branch"]
                    cur = _run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
                    if cur and cur != integ:
                        p2 = _run(["git", "-C", str(root), "push", "origin", f"HEAD:{integ}"])
                        if p2.returncode == 0:
                            pushed = f" + push → {integ} ({cur} protégée ; promotion : pm-promote.py)"
                        else:
                            last2 = (p2.stderr or "").strip().splitlines()[-1] if (p2.stderr or "").strip() else "?"
                            _warn(f"branche {cur} protégée ET repli {integ} refusé ({last2}) "
                                  f"— commit local {sha} conservé ; lancer pm-promote.py")
                    else:
                        _warn(f"branche {cur or '?'} protégée ({last}) — commit local {sha} conservé ; "
                              f"promotion requise : pm-promote.py")
                elif kind == "non_ff":
                    _warn(f"push différé (remote a avancé : non-fast-forward) — commit local {sha} "
                          f"conservé, le prochain auto-push l'emportera")
                else:
                    _warn(f"push refusé ({last}) — commit local {sha} conservé")
        try:
            from pm_output import out
            out.op("commit", extra=f"{sha} ({len(rel)} fichier(s)){pushed}")
        except Exception:
            print(f"✓ auto-commit {sha} ({len(rel)} fichier(s)){pushed}")
        return sha


if __name__ == "__main__":
    # Mode CLI minimal (debug / usage manuel) : pm_git.py <message> <fichier>...
    if len(sys.argv) < 3:
        sys.exit("usage: pm_git.py <message> <fichier>...")
    autocommit(sys.argv[2:], sys.argv[1])
