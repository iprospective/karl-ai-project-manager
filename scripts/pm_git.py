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

DEUX RÉGIMES depuis RM2440, selon la nature du dépôt :

  **Dépôt CORE** (données PM : `.mmi-pm/` ou `.mmi-pm-client/` réel à la racine)
  - `main` y accepte le push direct (pm-protect pose push=Developer) : plus de
    repli sur `dev`, plus de promotion par MR, donc plus d'arriéré possible.
  - Un rejet **non-fast-forward** est rattrapé sur place : `fetch` + `rebase`
    de nos seuls commits, sous le verrou, avec `--autostash`. C'est la levée
    ciblée de l'ancien invariant « jamais de rebase dans l'arbre partagé » :
    elle ne vaut QUE pour les cores (le contenu est du markdown de tickets, les
    conflits sont rares et un abandon propre est toujours possible) et elle est
    nécessaire — sans elle, autoriser le push direct ne fait que déplacer
    l'arriéré du mode `protected` vers le mode `non_ff` (constat RM2440).
  - Conflit de rebase ⇒ `rebase --abort` + warning : on ne laisse jamais un
    arbre partagé en état de rebase interrompu.

  **Dépôt de CODE** — inchangé : `main`/`dev` restent protégées, la livraison
  passe par une MR, et on ne rebase pas l'arbre partagé.

VERBOSITÉ (RM2440) : le chemin nominal est **silencieux**. Un auto-commit qui
réussit n'écrit rien — la plomberie des données PM ne fait pas partie de ce que
l'utilisateur a demandé. Seuls les **échecs** parlent, en une ligne. Les scripts
appelants qui veulent tracer le sha le récupèrent dans la valeur de retour.

Config (pm.config.yml :: git, overridable via pm.config.local.yml) :
  git:
    autocommit: true   # false = désactive tout (les scripts n'auto-committent plus)
    autopush:   true   # false = commit local seulement
    verbose:    false  # true = réaffiche la ligne « ✓ commit <sha> » du succès
    sweep:      true   # RM3013 : rattrapage de ce qui traîne (dépôts de données)
    sweep_after_min: 60  # âge minimal (dernière modification) d'un fichier rattrapé

Usage côté script :
    import pm_git
    pm_git.autocommit([md_path, log_path], f"pm(status): RM{rm_id} -> {status}")
"""
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

LOCK_TIMEOUT_S = 30
# RM3013 — rattrapage de ce qui traîne : seuil d'âge (minutes) et fichiers de travail ignorés.
SWEEP_AFTER_MIN = 60
SWEEP_SKIP_SUFFIXES = (".tmp", ".lock", ".swp", ".part", "~")
SWEEP_SKIP_PREFIXES = (".#",)

# Marqueurs d'un dépôt de données PM, à la RACINE du dépôt (invariant posé par
# norms/src/modules/structure-reference.md). Source unique : pm-protect importe
# `is_core_repo` d'ici pour que détection et politique ne puissent pas diverger.
CORE_MARKERS = (".mmi-pm", ".mmi-pm-client")


def _run(args, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)


def _env_commit():
    """L'environnement d'un `git commit` : l'AUTEUR est l'humain pour qui on agit quand on le
    connaît (RM3070 L3, `PM_ACTOR_*`) ; le committer reste le compte qui exécute. Sans acteur
    posé — cas mono, ou appel direct en ligne de commande — rien ne change."""
    try:
        import pm_actor
        return pm_actor.git_author_env()
    except Exception:      # noqa: BLE001 — l'identité ne doit JAMAIS empêcher un commit
        return None


def _num(v, default):
    try:
        return float(v) if v is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def _warn(msg):
    try:
        from pm_output import out
        out.warn(f"auto-commit : {msg}")
    except Exception:
        print(f"  ⚠ auto-commit : {msg}", file=sys.stderr)
    _journal("warn", f"auto-commit : {msg}")


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
        return {"autocommit": True, "autopush": True, "integration_branch": "dev",
                "sweep": True, "sweep_after_min": SWEEP_AFTER_MIN}
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
            "verbose": bool(merged.get("verbose", False)),
            "integration_branch": str(merged.get("integration_branch", "dev") or "dev"),
            "sweep": bool(merged.get("sweep", True)),
            "sweep_after_min": _num(merged.get("sweep_after_min"), SWEEP_AFTER_MIN)}


def repo_root(path):
    """Racine du repo git contenant `path` (Path) ou None. Utile pour grouper par
    repo un lot de fichiers couvrant plusieurs workspaces (mode `--all`, RM2038)."""
    p = Path(path)
    start = p if p.is_dir() else p.parent
    r = _run(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def is_core_repo(path):
    """True si `path` est (dans) un dépôt de DONNÉES PM — RM2440.

    Le marqueur doit être un dossier RÉEL à la racine du dépôt. Dans un workspace
    de CODE, `.mmi-pm` est un *symlink* vers le dossier PM centralisé : ce dépôt-là
    n'est pas un core, sa branche de prod reste protégée comme du code. Sans le
    test `is_symlink()`, tout workspace PM-tracké serait pris pour un core et
    perdrait sa protection — c'est le piège de cette détection.
    """
    root = path if isinstance(path, Path) and (path / ".git").exists() else repo_root(path)
    if root is None:
        return False
    return any((root / m).is_dir() and not (root / m).is_symlink() for m in CORE_MARKERS)


def resolve_base_ref(root, base, fetch=True, warn=None, dry_run_note=True):
    """Résout la base de branchement sur le REMOTE plutôt que sur le ref local (RM2574).

    `git checkout -b <br> dev` résout `dev` en `refs/heads/dev` — la branche LOCALE du
    clone, que rien ne rafraîchit. Sur un clone où l'on ne travaille jamais `dev`
    directement, elle décroche silencieusement : la branche du ticket part alors d'un
    code périmé (vécu RM2574 : 500 lignes de retard sur `scripts/karl-agent.py` ;
    RM2646 : `refs/heads/dev` du bare pisceen ~200 commits en arrière), sans le moindre
    signal.

    On fetch, puis on branche depuis `origin/<base>` dès que ce ref existe. Le fetch
    seul ne suffirait pas : il rafraîchit `origin/*` mais laisse le ref local — et donc
    la base retenue — au même endroit.

    Repli sur le ref local : pas de remote, `origin/<base>` inexistant (branche locale
    seulement), ou `base` désignant déjà un ref distant.

    Partagé par `pm-branch-start` et `pm-env-session` (RM2646) : les deux créent des
    branches de ticket, le garde ne doit pas exister d'un seul côté.

    `warn` : callable(str) pour les avertissements (défaut : `_warn`). `dry_run_note` :
    signaler qu'on résout sans fetch (à couper quand l'appelant ne fetch jamais).
    """
    say = warn or (lambda m: _warn(m))
    if "/" in base:            # origin/dev, upstream/main… déjà distant
        return base
    remote = "origin"
    if _run(["git", "-C", str(root), "remote", "get-url", remote]).returncode != 0:
        return base            # pas de remote : rien à rafraîchir
    if fetch:
        # Un fetch qui échoue EN SILENCE est le pire cas : la ref origin/* reste périmée
        # et annonce la base « à jour » alors qu'elle a divergé (cf. NORMS git-mep).
        r = _run(["git", "-C", str(root), "fetch", "--quiet", remote])
        if r.returncode != 0:
            say(f"git fetch {remote} a ÉCHOUÉ ({(r.stderr or r.stdout).strip()[:200]}) — "
                f"la base '{base}' peut être périmée, et rien ne le dira ensuite")
    elif dry_run_note:
        say(f"pas de fetch : base résolue sur les refs '{remote}/*' déjà présentes "
            f"(possiblement périmées)")
    tracked = f"{remote}/{base}"
    if _run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet",
             tracked]).returncode != 0:
        return base            # branche purement locale (version, wip…) : légitime
    if _run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet",
             f"refs/heads/{base}"]).returncode == 0:
        behind = _run(["git", "-C", str(root), "rev-list", "--count",
                       f"refs/heads/{base}..{tracked}"]).stdout.strip()
        if behind.isdigit() and int(behind) > 0:
            say(f"base locale '{base}' en retard de {behind} commit(s) sur "
                f"'{tracked}' → branchement depuis '{tracked}'")
    return tracked


def _rebase_onto_remote(root, branch):
    """Rattrape un rejet non-fast-forward sur un CORE : fetch + rebase de nos
    commits au-dessus du remote. Retourne (ok, détail).

    Appelé **sous le verrou** (voir autocommit) : aucune autre invocation pm-*
    de la machine ne touche l'arbre pendant ce temps. `--autostash` met de côté
    le travail non commité d'une session concurrente et le remet après.

    En cas de conflit on **abandonne** (`rebase --abort`) : un arbre partagé
    laissé en rebase interrompu casserait toutes les sessions suivantes, alors
    qu'un commit local en retard est rattrapable au tour d'après.
    """
    f = _run(["git", "-C", str(root), "fetch", "origin", branch])
    if f.returncode != 0:
        return False, "fetch impossible"
    r = _run(["git", "-C", str(root), "rebase", "--autostash", f"origin/{branch}"])
    if r.returncode == 0:
        return True, "rebase ok"
    _run(["git", "-C", str(root), "rebase", "--abort"])
    last = (r.stderr or r.stdout or "").strip().splitlines()
    return False, (last[-1] if last else "conflit")


def _journal(level, msg, **fields):
    """Trace dans logs/karl-agent.jsonl (catégorie `pm`, RM3010) — best-effort, jamais bloquant.
    `echo=False` : la ligne console est déjà portée par `_warn`, pas de doublon sur stderr."""
    try:
        import pm_log
        pm_log.log("pm", level, msg, echo=False, **fields)
    except Exception:
        pass


def _trigger_name(message):
    """`pm(tick): RM2889 …` → `tick` ; sinon un extrait court du message."""
    import re
    m = re.match(r"^\s*pm\(([^)]+)\)", message or "")
    return m.group(1) if m else (message or "?").strip()[:40]


def _stale_paths(root, cfg, exclude=()):
    """RM3013 — chemins du repo laissés non commités depuis plus de `sweep_after_min`.

    Lit `git status --porcelain -z --untracked-files=all`, écarte les chemins commités
    par l'appel courant et les fichiers de travail (`*.tmp`, `*.lock`, `*.swp`, `*~`,
    `.#*`), puis ne garde que ce dont la dernière modification (mtime ; pour une
    suppression : mtime du dossier parent) est antérieure au seuil. Un fichier
    touché il y a moins d'une heure est laissé tranquille : une session peut être
    dessus, et c'est son propre auto-commit qui doit l'emporter.
    """
    import os
    st = _run(["git", "-C", str(root), "status", "--porcelain", "-z", "--untracked-files=all"])
    if st.returncode != 0:
        return []
    cutoff = time.time() - float(cfg.get("sweep_after_min", SWEEP_AFTER_MIN)) * 60
    entries = st.stdout.split("\0")
    picked, i = [], 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        xy, p = e[:2], e[3:]
        if xy[0] in "RC":
            i += 1  # renommage/copie stagé : l'entrée suivante est l'ancien chemin
        if p in exclude or p.endswith("/"):
            continue
        name = p.rsplit("/", 1)[-1]
        if name.endswith(SWEEP_SKIP_SUFFIXES) or name.startswith(SWEEP_SKIP_PREFIXES):
            continue
        fp = root / p
        try:
            mtime = os.lstat(fp).st_mtime
        except FileNotFoundError:  # suppression : datée par le dossier parent
            try:
                mtime = os.lstat(fp.parent).st_mtime
            except OSError:
                continue
        except OSError:
            continue
        if mtime <= cutoff:
            picked.append(p)
    return picked


def _sweep_stale(root, cfg, trigger, exclude=()):
    """RM3013 — commit de rattrapage de ce qui traîne, sous le verrou de l'appelant.

    Pas de timer ni de process dédié (décision Mathieu 2026-09-06) : c'est chaque
    auto-commit d'un script qui referme le filet. Dépôts de DONNÉES seulement
    (`is_core_repo`) ; `git.sweep: false` débraye. Retourne le sha du commit de
    rattrapage ou None. Silencieux si succès (RM2440) ; journalisé (catégorie `pm`).
    """
    if not cfg.get("sweep", True) or not is_core_repo(root):
        return None
    picked = _stale_paths(root, cfg, exclude)
    if not picked:
        return None
    mins = int(float(cfg.get("sweep_after_min", SWEEP_AFTER_MIN)))
    tool = _trigger_name(trigger)
    add = _run(["git", "-C", str(root), "add", "-A", "--"] + picked)
    if add.returncode != 0:
        _warn(f"rattrapage : git add a échoué : {add.stderr.strip()}")
        return None
    msg = (f"pm(rattrapage): {len(picked)} fichier(s) laissés non commités > {mins} min "
           f"(déclenché par {tool})")
    c = _run(["git", "-C", str(root), "commit", "-m", msg, "--"] + picked, env=_env_commit())
    if c.returncode != 0:
        _warn(f"rattrapage : git commit a échoué : {(c.stderr or c.stdout).strip()}")
        return None
    sha = _run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"]).stdout.strip()
    _journal("info", f"rattrapage git : {len(picked)} fichier(s) commités", repo=str(root), sha=sha,
             actor=os.environ.get("PM_ACTOR_USER") or None,   # RM3070 L3 : qui, pas seulement quoi
             after_min=mins, trigger=tool, files=picked[:20], more=max(0, len(picked) - 20) or None)
    return sha


def _push(root, cfg, sha):
    """Pousse HEAD selon le régime du dépôt (core : push direct + rebase de rattrapage,
    RM2440 ; code : repli sur la branche d'intégration si protégée, RM2298).
    Retourne le suffixe descriptif du succès ('' si rien n'est parti ; l'échec a déjà parlé)."""
    pushed = ""
    core = is_core_repo(root)
    cur = _run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    p = _run(["git", "-C", str(root), "push"])
    if p.returncode == 0:
        return " + push"
    kind = _push_error_kind(p.stderr)
    last = p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "raison inconnue"
    if kind == "non_ff" and core and cur:
        # RM2440 — sur un core, on rattrape au lieu de différer : sous
        # le verrou, fetch + rebase de nos commits, puis re-push. C'est
        # ce qui empêche l'arriéré de se reformer sous une autre forme
        # une fois le push direct autorisé.
        ok, why = _rebase_onto_remote(root, cur)
        if ok:
            p3 = _run(["git", "-C", str(root), "push"])
            if p3.returncode == 0:
                pushed = " + push (après rebase sur origin)"
            else:
                l3 = (p3.stderr or "").strip().splitlines()
                _warn(f"push refusé après rebase ({l3[-1] if l3 else '?'}) — "
                      f"commit local {sha} conservé")
        else:
            _warn(f"remote a avancé et le rebase a échoué ({why}) — commit "
                  f"local {sha} conservé, arbre laissé intact")
    elif kind == "protected":
        # RM2298 : branche courante protégée — un push direct ne passera
        # JAMAIS ici. Repli sur la branche d'intégration ; la promotion se
        # fait ensuite par MR. Depuis RM2440 ce chemin ne concerne plus que
        # les dépôts de CODE : sur un core, `main` accepte le push direct.
        integ = cfg["integration_branch"]
        if core:
            _warn(f"branche {cur or '?'} protégée sur un dépôt de données PM — "
                  f"politique core non appliquée ? (pm-protect --repo {root}) ; "
                  f"commit local {sha} conservé")
        elif cur and cur != integ:
            p2 = _run(["git", "-C", str(root), "push", "origin", f"HEAD:{integ}"])
            if p2.returncode == 0:
                pushed = f" + push → {integ} ({cur} protégée ; livraison par MR)"
            else:
                last2 = (p2.stderr or "").strip().splitlines()[-1] if (p2.stderr or "").strip() else "?"
                _warn(f"branche {cur} protégée ET repli {integ} refusé ({last2}) "
                      f"— commit local {sha} conservé")
        else:
            _warn(f"branche {cur or '?'} protégée ({last}) — commit local {sha} "
                  f"conservé ; livraison par MR")
    elif kind == "non_ff":
        _warn(f"push différé (remote a avancé : non-fast-forward) — commit local {sha} "
              f"conservé, le prochain auto-push l'emportera")
    else:
        _warn(f"push refusé ({last}) — commit local {sha} conservé")
    return pushed


def _index_touch(paths):
    """Réindexe les fiches écrites (RM3128). Silencieux et sans effet si l'index n'a
    jamais été construit — on ne le crée pas en douce au détour d'un commit."""
    try:
        import pm_searchdb
        from pm_paths import PMConfig
        cfg = PMConfig.load(os.environ.get("PM_CORE_DIR") or None)
        if not pm_searchdb.db_path(cfg).exists():
            return
        for p in paths:
            if p.name.startswith("RM") and p.name.endswith(".md"):
                pm_searchdb.touch(cfg, p)
    except (Exception, SystemExit):      # PMConfig.load() peut sys.exit() hors PM
        return


def autocommit(paths, message, push=None, enabled=None, allow_missing=False):
    """Committe (et pousse) atomiquement les chemins listés. Retourne le sha court ou None.

    paths   : fichiers écrits par l'appelant (str|Path ; inexistants/None ignorés).
    message : message de commit (convention : `pm(<outil>): RM<id> <action>`).
    push    : force/désactive le push pour cet appel (None = config autopush).
    enabled : force/désactive l'auto-commit pour cet appel (None = config autocommit).
    allow_missing : garde les chemins ABSENTS du disque, pour committer une
              **suppression** (RM2866, `pm-task-move` : la fiche a quitté le repo
              source). Hors ce cas, un chemin manquant est une erreur d'appelant —
              d'où le filtre par défaut, conservé tel quel.

    RM3013 : sur un dépôt de DONNÉES, chaque appel referme aussi le filet — ce qui
    traîne non commité depuis plus de `git.sweep_after_min` part dans un commit
    `pm(rattrapage): …` séparé (voir `_sweep_stale`), poussé avec le nôtre. Le sha
    rendu reste celui des chemins nommés (None s'ils n'avaient rien à committer,
    même si un rattrapage est parti).
    """
    cfg = load_git_config()
    if not (cfg["autocommit"] if enabled is None else enabled):
        return None
    paths = [Path(p).resolve() for p in paths
             if p and (allow_missing or Path(p).exists())]
    if not paths:
        return None

    # RM3128 — première des deux entrées de l'index : toute écriture PM passe ici.
    # Greffé sur un process existant plutôt que sur un timer dédié, comme le sweep
    # RM3013 juste au-dessus. Jamais fatal : l'index est une projection, son échec ne
    # doit pas empêcher un ticket d'être écrit.
    _index_touch(paths)

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

        sha = None
        if _run(["git", "-C", str(root), "status", "--porcelain", "--"] + rel).stdout.strip():
            add = _run(["git", "-C", str(root), "add", "--"] + rel)
            if add.returncode != 0:
                _warn(f"git add a échoué : {add.stderr.strip()}")
                return None
            # `commit -- <chemins>` : n'embarque QUE ces chemins, même si d'autres
            # fichiers sont stagés par une session concurrente.
            c = _run(["git", "-C", str(root), "commit", "-m", message, "--"] + rel, env=_env_commit())
            if c.returncode != 0:
                _warn(f"git commit a échoué : {(c.stderr or c.stdout).strip()}")
                return None
            sha = _run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"]).stdout.strip()

        # RM3013 — le rattrapage tourne même quand nos chemins étaient déjà à jour :
        # un process qui passe par ici est l'occasion de commiter ce qui traîne.
        swept = _sweep_stale(root, cfg, message, exclude=set(rel))
        if sha is None and swept is None:
            return None  # rien à committer (contenu identique) et rien qui traîne

        pushed = ""
        if cfg["autopush"] if push is None else push:
            pushed = _push(root, cfg, sha or swept)

        # RM2440 — le succès est silencieux : la plomberie git des données PM ne
        # fait pas partie de ce que l'utilisateur a demandé. `git.verbose: true`
        # dans pm.config.yml rétablit la ligne pour du débogage.
        if cfg.get("verbose"):
            extra = (f"{sha} ({len(rel)} fichier(s))" if sha else "rien pour nos chemins") \
                + (f" ; rattrapage {swept}" if swept else "") + pushed
            try:
                from pm_output import out
                out.op("commit", extra=extra)
            except Exception:
                print(f"✓ auto-commit {extra}")
        return sha


if __name__ == "__main__":
    # Mode CLI minimal (debug / usage manuel) : pm_git.py <message> <fichier>...
    if len(sys.argv) < 3:
        sys.exit("usage: pm_git.py <message> <fichier>...")
    autocommit(sys.argv[2:], sys.argv[1])
