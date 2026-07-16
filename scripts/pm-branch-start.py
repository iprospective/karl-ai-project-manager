#!/usr/bin/env python3
"""pm-branch-start — Crée la branche de travail d'un ticket (NORMS git-mep ; RM1923 #1 / RM1897).

Opération « je commence à coder un ticket » outillée :
  1. branche `<RMid>-<slug>` créée depuis la branche de base (--from, défaut :
     branche courante du repo) et checkée out — idempotent : si elle existe
     déjà, simple checkout ;
  2. CF Redmine « GIT Branche » renseigné ;
  3. frontmatter de la tâche (`git.repo` / `git.branch`) + entrée `.log.md` ;
  4. auto-commit des fichiers PM écrits (pm_git, RM1834) ;
  5. --take : enchaîne la prise du ticket (pm-task-status-update en_cours,
     auto-assignation NORMS).

Usage :
    pm-branch-start.py <rm_id> [--repo PATH] [--from BRANCH] [--slug SLUG]
                       [--take] [--no-commit] [--dry-run]

Le repo cible est le dépôt de CODE du ticket (défaut : cwd). La branche de
base doit être la branche d'intégration du projet (tripwire NORMS #3) — si
--from est omis, la branche courante est utilisée avec un avertissement.

NB : dans un workspace au layout RM1993 (`repos/` + `envs/`), l'env de session
`envs/<repo>-rm<id>` (worktree + vhost + BDD) est géré par `pm-env-session.py`
— créé automatiquement à la prise du ticket (hook en_cours de
pm-task-status-update, RM1834). Le mode --worktree ci-dessous reste le chemin
pour les repos hors layout.
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_git
import pm_session
import redmine_utils

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
CF_BRANCH_NAME = "GIT Branche"
SLUG_MAX = 40


def _git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"ERREUR git {' '.join(args)} : {(r.stderr or r.stdout).strip()}")
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--repo", default=".", help="Dépôt de code cible (défaut : cwd)")
    ap.add_argument("--from", dest="base", help="Branche de base (défaut : branche courante)")
    ap.add_argument("--slug", help="Slug de branche (défaut : slug du fichier de tâche)")
    ap.add_argument("--take", action="store_true",
                    help="Enchaîne la prise du ticket (status en_cours + auto-assignation)")
    ap.add_argument("--worktree", action="store_true",
                    help="Crée un git worktree dédié (au lieu d'un checkout in-place) + "
                         "branche discriminée par session <RMid>-<slug>-m<PMid>-s<seq> (RM2034). "
                         "Pour mener plusieurs tickets en parallèle sans se tromper de cible.")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git PM (RM1834)")
    ap.add_argument("--print-cd", action="store_true",
                    help="N'émet QUE le chemin de travail final sur stdout (logs sur stderr) "
                         "— usage machine : cd \"$(pm-branch-start.py <id> --worktree --print-cd)\" (RM2240)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # --print-cd : stdout réservé au chemin final, tout le reste part sur stderr
    # (même mécanique que pm-task-add --porcelain, RM2224).
    real_stdout = sys.stdout
    if args.print_cd:
        sys.stdout = sys.stderr

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : RM{args.rm_id} introuvable parmi les projets PM")

    # Slug : depuis le nom de fichier RM<id>_<slug>.md, tronqué proprement.
    if args.slug:
        slug = args.slug
    else:
        slug = md_path.stem.split("_", 1)[1] if "_" in md_path.stem else f"rm{args.rm_id}"
        slug = slug[:SLUG_MAX].rstrip("-")
    branch = f"{args.rm_id}-{slug}"

    repo = Path(args.repo).resolve()
    root_r = _git(repo, "rev-parse", "--show-toplevel", check=False)
    if root_r.returncode != 0:
        sys.exit(f"ERREUR : {repo} n'est pas dans un dépôt git")
    root = Path(root_r.stdout.strip())
    if root == cfg.projects_root:
        sys.exit("ERREUR : le repo cible est ai-projects (données PM) — la branche de "
                 "ticket se crée dans le dépôt de CODE du projet (--repo).")

    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    base = args.base or current
    if not args.base:
        print(f"  ⚠ --from omis : base = branche courante '{base}' (vérifie que c'est "
              f"bien la branche d'intégration du projet)", file=sys.stderr)

    # Mode worktree (RM2034) : branche discriminée par session + worktree dédié,
    # pour mener plusieurs tickets en parallèle sans se tromper de cible.
    wt = None
    if args.worktree:
        suffix = f"-m{pm_session.machine_id()}-s<seq>" if args.dry_run else pm_session.branch_suffix()
        branch = f"{args.rm_id}-{slug}{suffix}"
        seq = None if args.dry_run else pm_session.get_session_seq()
        wt = root.parent / (f"{root.name}-{args.rm_id}" + (f"-s{seq}" if seq is not None else ""))
        # Idempotence indépendante du cwd (RM2240) : si le frontmatter porte déjà
        # le worktree de CETTE branche, le réutiliser — sinon une relance depuis
        # un autre worktree calcule un chemin imbriqué et plante.
        try:
            fm_peek = yaml.safe_load(FM_RE.match(md_path.read_text(encoding="utf-8")).group(2)) or {}
            g_peek = fm_peek.get("git") or {}
            if g_peek.get("branch") == branch and g_peek.get("worktree") \
                    and Path(g_peek["worktree"]).is_dir():
                wt = Path(g_peek["worktree"])
        except Exception:
            pass

    exists = _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
                  check=False).returncode == 0
    if args.dry_run:
        action = (f"worktree add {wt}" if args.worktree
                  else ("checkout" if exists else f"création depuis {base} +checkout"))
        print(f"--dry-run : {action} pour '{branch}' dans {root} ; CF '{CF_BRANCH_NAME}'={branch} ; "
              f"frontmatter git.repo={root.name}, git.branch={branch}")
        return

    if args.worktree:
        if wt.exists():
            print(f"✓ worktree existant '{wt}' (branche '{branch}') réutilisé ({root.name})")
        elif exists:
            _git(root, "worktree", "add", str(wt), branch)
            print(f"✓ worktree '{wt}' sur branche existante '{branch}' ({root.name})")
        else:
            _git(root, "worktree", "add", str(wt), "-b", branch, base)
            print(f"✓ worktree '{wt}' + branche '{branch}' depuis '{base}' ({root.name})")
        pm_session.record_branch(branch)
        pm_session.record_worktree(str(wt))
    elif exists:
        _git(root, "checkout", branch)
        print(f"✓ branche existante '{branch}' checkée out ({root.name})")
    else:
        _git(root, "checkout", "-b", branch, base)
        print(f"✓ branche '{branch}' créée depuis '{base}' et checkée out ({root.name})")

    # CF Redmine « GIT Branche »
    cf_id = redmine_utils.cf_id_by_name(CF_BRANCH_NAME)
    if cf_id:
        ok, err = redmine_utils.update_issue_fields(
            args.rm_id, custom_fields=[{"id": cf_id, "value": branch}])
        if ok:
            print(f"✓ CF{cf_id} ({CF_BRANCH_NAME}) = {branch}")
        else:
            print(f"  ⚠ CF {CF_BRANCH_NAME} non poussé : {err}", file=sys.stderr)
    else:
        print(f"  ⚠ CF '{CF_BRANCH_NAME}' absent de redmine.reference.yml — skip", file=sys.stderr)

    # Frontmatter git.repo / git.branch + log
    content = md_path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {md_path}")
    fm = yaml.safe_load(m.group(2)) or {}
    git_block = fm.get("git") or {}
    git_block.update({"repo": root.name, "branch": branch})
    if wt is not None:
        git_block["worktree"] = str(wt)
    fm["git"] = git_block
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    fm["updated"] = now
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {now} — Branche de travail (pm-branch-start)\n"
                f"Tokens : 0 | Durée : 0 min\n\n"
                f"Branche `{branch}` ({'existante' if exists else f'créée depuis {base}'}) "
                f"dans le repo `{root.name}` ; CF « {CF_BRANCH_NAME} » renseigné.\n")
    print(f"✓ frontmatter git.repo/git.branch + log : {md_path.name}")

    if not args.no_commit:
        pm_git.autocommit([md_path, log_path], f"pm(branch): RM{args.rm_id} branche {branch}")

    # --take : prise du ticket (transition + auto-assignation, source unique)
    if args.take:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "pm-task-status-update.py"),
             str(args.rm_id), "en_cours",
             "--note", f"Prise en charge — branche de travail `{branch}` créée (pm-branch-start)."],
            check=False, stdout=sys.stderr if args.print_cd else None)
        if r.returncode != 0:
            print(f"  ⚠ transition en_cours échouée (exit {r.returncode}) — reprends : "
                  f"pm-task-status-update.py {args.rm_id} en_cours", file=sys.stderr)

    # Dernière ligne = action à exécuter : se PLACER dans le worktree du ticket
    # (RM2240 — un sous-processus ne change pas le cwd du shell parent ; sans ce
    # rappel l'agent continue à travailler dans le mauvais worktree).
    workdir = wt if wt is not None else root
    if args.print_cd:
        print(str(workdir), file=real_stdout)
    elif wt is not None:
        print(f"→ cd {workdir}")


if __name__ == "__main__":
    main()
