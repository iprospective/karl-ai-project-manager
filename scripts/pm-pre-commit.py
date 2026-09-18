#!/usr/bin/env python3
"""pm-pre-commit — garde-fou « bon worktree / bonne branche » (RM2240).

Installé par pm-hooks-install (symlink .git/hooks/pre-commit, y compris sur les
bares repos/*.git dont héritent les worktrees envs/). Hors workspace PM : laisse
passer. Trois vérifications, du plus dur au plus doux :

1. Branche de ticket `<id>-…` SANS ticket RM<id> local → REFUS (tripwire #13,
   même garde que pm-pre-push mais AVANT le commit).
2. Branche de ticket dont le frontmatter `git.worktree` pointe AILLEURS que le
   worktree courant → REFUS : c'est précisément « je travaille dans le mauvais
   worktree ». Escapes : `git commit --no-verify` ou PM_SKIP_WORKTREE_CHECK=1
   (cas légitime : plusieurs sessions sur le même ticket, le frontmatter porte
   le worktree de la DERNIÈRE session passée par pm-branch-start).
3. Commit sur une branche d'intégration (dev/main/…) alors que la session
   courante a des worktrees de ticket actifs sur CE repo → AVERTISSEMENT
   bruyant (non bloquant : merges et hotfix légitimes).

0. Dépôt PUBLIABLE (`.client-data-guard.yml` à la racine, RM3201) : une ligne
   ajoutée qui nomme un client ou l'une de ses instances → REFUS. Indépendant du
   workspace PM : c'est le dépôt qui se déclare publié, pas son emplacement.
   Escape : PM_SKIP_CLIENT_DATA_CHECK=1 (tracé à l'écran), ou `--no-verify`.

Toute erreur interne du hook laisse passer le commit (fail-open) : un garde-fou
ne doit jamais bloquer le travail par accident.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # RM3053
from pm_think import is_task_sheet  # noqa: E402  RM3053 : la fiche, jamais un frère (.log.md, .think.md)

INTEGRATION_BRANCHES = {"dev", "main", "master", "preprod"}


def sh(*args, cwd=None):
    return subprocess.run(args, capture_output=True, text=True, cwd=cwd)


def find_pm_workspace(start: Path):
    d = start
    while True:
        if (d / ".mmi-pm").exists():
            return d
        if d == d.parent:
            return None
        d = d.parent


def fm_git_field(task_file: Path, field: str):
    """Extrait `git.<field>` du frontmatter sans dépendance yaml (hook rapide)."""
    m = re.search(rf"^git:\n(?:  .*\n)*?  {field}:\s*(\S+)",
                  task_file.read_text(encoding="utf-8"), re.M)
    if not m or m.group(1) in ("null", "~"):
        return None
    return m.group(1).strip("'\"")


def warn_integration_branch(top: Path, branch: str):
    """Cas 3 : la session a-t-elle des worktrees de ticket actifs sur ce repo ?"""
    if not os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pm_session
    rec = pm_session.current_record()
    if not rec:
        return
    common = sh("git", "rev-parse", "--path-format=absolute", "--git-common-dir",
                cwd=top).stdout.strip()
    ours = []
    for w in rec.get("worktrees") or []:
        wp = Path(w)
        if not wp.is_dir() or wp.resolve() == top.resolve():
            continue
        c = sh("git", "rev-parse", "--path-format=absolute", "--git-common-dir",
               cwd=wp).stdout.strip()
        if c and c == common:
            ours.append(str(wp))
    if ours:
        print(f"pm-pre-commit: ⚠ COMMIT SUR '{branch}' alors que ta session a des "
              f"worktrees de ticket actifs sur ce repo :", file=sys.stderr)
        for w in ours:
            print(f"  • {w}", file=sys.stderr)
        print("  Es-tu dans le BON worktree ? (RM2240 — `cd \"$(pm-task-cd.py <id>)\"`)\n"
              "  Commit laissé passer (merge/hotfix légitimes possibles).", file=sys.stderr)


def client_data_check(top: Path) -> int:
    """RM3201 : un dépôt publiable ne reçoit aucune donnée client. 0 = passe, 1 = refus."""
    if not (top / ".client-data-guard.yml").is_file():
        return 0
    if os.environ.get("PM_SKIP_CLIENT_DATA_CHECK") == "1":
        print("pm-pre-commit: ⚠ contrôle des données client DÉSACTIVÉ "
              "(PM_SKIP_CLIENT_DATA_CHECK=1) sur un dépôt publiable.", file=sys.stderr)
        return 0
    try:
        import pm_client_data_guard as G
        from pm_paths import PMConfig
        conf = G.load_guard_config(top)
        pat = G.collect(PMConfig.load(), conf.get("common_words") or ())
        if pat.empty():
            print("pm-pre-commit: ⚠ données client NON contrôlées — les données privées du "
                  "PM sont injoignables d'ici (RM3201).", file=sys.stderr)
            return 0
        found = G.check_staged(top, pat, conf.get("exempt") or ())
    except Exception as e:  # fail-open, mais bruyant
        print(f"pm-pre-commit: ⚠ contrôle des données client en erreur, commit laissé "
              f"passer ({e})", file=sys.stderr)
        return 0
    if not found:
        return 0
    print("pm-pre-commit: REFUS — ce dépôt est publiable (.client-data-guard.yml) et le "
          "commit y ajoute des données client (RM3201) :", file=sys.stderr)
    for f in found[:30]:
        print(f"    {f}", file=sys.stderr)
    if len(found) > 30:
        print(f"    … et {len(found) - 30} autre(s)", file=sys.stderr)
    print("  Jeu fictif (clienta…, domaines en .example) ; conf réelle hors git ; instances "
          "dans le environments.md du projet — norms/src/modules/client-data.md.\n"
          "  Dette connue et tracée seulement : marqueur `client-data-guard: allow` sur la ligne.",
          file=sys.stderr)
    return 1


def main():
    top_r = sh("git", "rev-parse", "--show-toplevel")
    if top_r.returncode == 0:
        rc = client_data_check(Path(top_r.stdout.strip()))
        if rc:
            return rc
    if os.environ.get("PM_SKIP_WORKTREE_CHECK") == "1":
        return 0
    top_r = sh("git", "rev-parse", "--show-toplevel")
    if top_r.returncode != 0:
        return 0
    top = Path(top_r.stdout.strip())
    ws = find_pm_workspace(top)
    if ws is None:
        return 0
    branch = sh("git", "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if not branch:
        return 0  # detached HEAD (rebase, bisect…) : ne pas gêner

    m = re.match(r"^(\d+)-", branch)
    if not m:
        if branch in INTEGRATION_BRANCHES:
            try:
                warn_integration_branch(top, branch)
            except Exception:
                pass  # fail-open : l'avertissement ne doit jamais casser un commit
        return 0

    rm_id = m.group(1)
    tasks = ws / ".mmi-pm" / "tasks"
    task_files = sorted(tasks.glob(f"RM{rm_id}_*.md")) if tasks.is_dir() else []
    task_files = [f for f in task_files if is_task_sheet(f)]
    if not task_files:
        print(f"pm-pre-commit: REFUS — branche '{branch}' : aucun ticket RM{rm_id} "
              f"dans {tasks}.\n"
              f"  Id prédit/inventé ? (tripwire #13) Crée le ticket d'abord :\n"
              f"  ID=$(pm-task-add … --porcelain) puis pm-branch-start \"$ID\".",
              file=sys.stderr)
        return 1

    try:
        expected_wt = fm_git_field(task_files[0], "worktree")
        expected_br = fm_git_field(task_files[0], "branch")
    except Exception:
        return 0  # frontmatter illisible : fail-open
    # Bloquer seulement si la branche courante EST celle du frontmatter (même
    # session) : une branche différente = autre session sur le ticket, dont le
    # worktree frontmatter ne nous concerne pas (simple ⚠ plus bas).
    if expected_wt and (expected_br is None or expected_br == branch):
        wt_path = Path(expected_wt)
        if wt_path.is_dir() and wt_path.resolve() != top.resolve():
            print(f"pm-pre-commit: REFUS — tu commits pour RM{rm_id} dans\n"
                  f"    {top}\n"
                  f"  alors que son worktree enregistré est\n"
                  f"    {expected_wt}\n"
                  f"  → `cd \"$(pm-task-cd.py {rm_id})\"` puis recommence (RM2240).\n"
                  f"  Cas légitime (multi-session sur le même ticket) : "
                  f"`git commit --no-verify` ou PM_SKIP_WORKTREE_CHECK=1.",
                  file=sys.stderr)
            return 1
    if expected_br and expected_br != branch:
        print(f"pm-pre-commit: ⚠ branche courante '{branch}' ≠ git.branch du ticket "
              f"('{expected_br}') — autre session sur RM{rm_id}, ou frontmatter "
              f"périmé ? Commit laissé passer.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # fail-open assumé : garde-fou, pas point de défaillance
        print(f"pm-pre-commit: erreur interne ignorée ({e})", file=sys.stderr)
        sys.exit(0)
