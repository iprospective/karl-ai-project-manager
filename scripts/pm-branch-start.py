#!/usr/bin/env python3
"""pm-branch-start — Crée la branche de travail d'un ticket (NORMS git-mep ; RM1923 #1 / RM1897).

Opération « je commence à coder un ticket » outillée :
  1. branche `<RMid>-<slug>` créée depuis la branche de base (--from, défaut :
     branche courante du repo) et checkée out — idempotent : si elle existe
     déjà, simple checkout ;
  2. CF Redmine « GIT Branche » renseigné ;
  3. frontmatter de la tâche (`git.repo` / `git.branch`, et `git.worktree` dès
     que le dépôt cible est un worktree dédié — RM2754) + entrée `.log.md` ;
  4. auto-commit des fichiers PM écrits (pm_git, RM1834) ;
  5. --take : enchaîne la prise du ticket (pm-task-status-update en_cours,
     auto-assignation NORMS).

Usage :
    pm-branch-start.py <rm_id> [--repo PATH] [--from BRANCH] [--slug SLUG]
                       [--take] [--no-commit] [--dry-run]

Le repo cible est le dépôt de CODE du ticket (défaut : cwd). La branche de
base doit être la branche d'intégration du projet (tripwire NORMS #3) — si
--from est omis, la branche courante est utilisée avec un avertissement.

Gardes de cible (RM2360) : un CORE (repo qui révisionne `.mmi-pm`) est refusé —
le code se branche dans un worktree `envs/` tiré de `repos/`, pas dans le core ;
et si la tâche a déjà enregistré son repo de code, un cwd pointant ailleurs est
refusé (contournable par `--repo` explicite).

NB : dans un workspace au layout RM1993 (`repos/` + `envs/`), l'env de session
`envs/<repo>-rm<id>` (worktree + vhost + BDD) est géré par `pm-env-session.py`
— créé automatiquement à la prise du ticket (hook en_cours de
pm-task-status-update, RM1834). Le mode --worktree ci-dessous reste le chemin
pour les repos hors layout.

`git.worktree` est renseigné dans les DEUX cas (RM2754) : avec `--worktree`, et
aussi quand le `--repo` reçu est déjà un worktree lié — ce que fait `pm-task-take`
en passant l'env de session. Sans cela le champ restait vide pour tous les tickets
pris normalement, `pm-task-cd` répondait « mode in-place » et le garde-fou n°2 de
`pm-pre-commit` (« tu commites depuis le mauvais worktree ») n'avait rien à
comparer. Un travail réellement in-place dans le dépôt principal, lui, ne
renseigne toujours rien : le champ reste le reflet de la réalité.
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out
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


def _resolve_base(root, base, fetch=True):
    """Base de branchement résolue sur le REMOTE — implémentation partagée dans
    `pm_git.resolve_base_ref` (RM2574 pour la règle, RM2646 pour la factorisation :
    `pm-env-session` créait des branches sans ce garde).

    En `--dry-run` on ne fetch pas (un essai à blanc n'écrit pas dans `.git`) : la
    résolution se fait sur les refs `origin/*` telles qu'elles sont, et on le dit.
    """
    return pm_git.resolve_base_ref(root, base, fetch=fetch, warn=out.warn)


def _is_core(root):
    """Un dépôt est un CORE PM (structure/projet) s'il RÉVISIONNE un `.mmi-pm` /
    `.mmi-pm-client` à sa racine — jamais une cible de branche de code (invariant NORMS
    structure-reference, RM2348 : le code se branche dans un worktree `envs/` tiré de
    `repos/`). On teste le suivi git plutôt que la simple présence : dans le modèle
    legacy, `.mmi-pm` est un symlink gitignoré du workspace de CODE (non tracké) — il ne
    doit donc PAS être pris pour un core."""
    tracked = _git(root, "ls-files", "--", ".mmi-pm", ".mmi-pm-client",
                   check=False).stdout.strip()
    return bool(tracked)


def repo_name_of(root: Path) -> str:
    """Nom CANONIQUE du dépôt de code, indépendant du worktree d'où l'on parle.

    Source : le bare `repos/<name>.git` que désigne `--git-common-dir`. Utiliser
    `root.name` à la place — comme le faisait ce script — fait dériver le nom du
    worktree courant : lancé depuis le worktree d'un autre ticket, il produisait
    `<repo>-dev-2394-s29-2431-s29`, puis `…-2431-s29-…` au coup d'après (RM2523).
    """
    common = _git(root, "rev-parse", "--git-common-dir", check=False).stdout.strip()
    if common:
        p = Path(common)
        if not p.is_absolute():
            p = (root / p).resolve()
        # ORDRE IMPORTANT : ".git".endswith(".git") est vrai, donc le cas du
        # dépôt classique doit être testé AVANT celui du bare — sinon il tombe
        # dans la branche `[:-4]` et retourne une chaîne vide.
        if p.name == ".git":                 # dépôt classique : <repo>/.git
            return p.parent.name
        if p.name.endswith(".git"):          # layout RM1993 : repos/<name>.git
            return p.name[:-4]
    return root.name                          # repli : ancien comportement


# >>> is_linked_worktree — pure (testée par test_pm_branch_start_worktree.py)
def is_linked_worktree(git_dir: str, git_common_dir: str) -> bool:
    """Le dossier de travail est-il un worktree LIÉ, et non le dépôt principal ?

    Fait, pas heuristique : git donne deux chemins. Dans le dépôt principal ils
    désignent la même chose ; dans un worktree lié, `--git-dir` pointe sous
    `<commun>/worktrees/<nom>`. On ne devine donc rien depuis le nom du dossier
    (`envs/…`), qui n'est qu'une convention et mentirait le jour où elle change.
    """
    if not git_dir or not git_common_dir:
        return False
    return Path(git_dir).resolve() != Path(git_common_dir).resolve()
# <<< is_linked_worktree


def worktree_path(root: Path, rm_id: int, branch: str, seq) -> Path:
    """Chemin du worktree de session, convention UNIQUE (RM2523).

        envs/<repo>-rm<id>           canonique — même forme que `pm-env-session create`
        envs/<repo>-rm<id>-s<seq>    si le canonique est déjà pris par une AUTRE branche

    Le suffixe de session n'apparaît donc qu'en cas de collision réelle (deux
    sessions sur le même ticket), au lieu d'être systématique. `pm-env-session`
    résout de toute façon par branche : le nom n'est plus qu'un repère humain.
    """
    envs = root.parent
    canonical = envs / f"{repo_name_of(root)}-rm{rm_id}"
    if not canonical.exists():
        return canonical
    # occupé : par NOUS (même branche) → on le réutilise ; par un autre → suffixe
    head = _git(canonical, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    if head == branch:
        return canonical
    return envs / f"{repo_name_of(root)}-rm{rm_id}-s{seq}" if seq is not None else \
        envs / f"{repo_name_of(root)}-rm{rm_id}-s0"


def peek_task_frontmatter(md_path):
    """Frontmatter YAML de la tâche (dict), ou {} si illisible."""
    try:
        return yaml.safe_load(FM_RE.match(md_path.read_text(encoding="utf-8")).group(2)) or {}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--repo", default=None,
                    help="Dépôt de code cible (défaut : cwd). Passé explicitement, "
                         "il contourne le cross-check du repo enregistré (RM2360).")
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
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

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

    repo = Path(args.repo if args.repo is not None else ".").resolve()
    root_r = _git(repo, "rev-parse", "--show-toplevel", check=False)
    if root_r.returncode != 0:
        sys.exit(f"ERREUR : {repo} n'est pas dans un dépôt git")
    root = Path(root_r.stdout.strip())
    if root == cfg.projects_root:
        sys.exit("ERREUR : le repo cible est ai-projects (index PM) — la branche de "
                 "ticket se crée dans le dépôt de CODE du projet (--repo).")

    # Garde structurelle (RM2360) : un CORE (repo qui révisionne .mmi-pm) n'est jamais
    # une cible de branche de code. Sans ça, lancer depuis la racine d'un workspace
    # projet branche le core au lieu du repo de code (bug RM2325).
    if _is_core(root):
        sys.exit(
            f"ERREUR : le repo cible '{root.name}' est un CORE PM (il révisionne "
            f".mmi-pm) — la branche de ticket se crée dans le dépôt de CODE, un "
            f"worktree sous 'envs/' tiré de 'repos/'. Place-toi dans 'envs/<repo>' "
            f"(ex. l'env d'intégration '<repo>-dev') ou passe --repo <chemin-du-code>.")

    # Cross-check (RM2360) : si la tâche a déjà enregistré son repo de code, refuser un
    # repo différent (empêche de polluer git.repo/CF depuis le mauvais endroit) — sauf
    # --repo explicite (choix délibéré, ex. le code a changé de dépôt).
    canonical_repo = repo_name_of(root)
    recorded = ((peek_task_frontmatter(md_path).get("git") or {}).get("repo"))
    if recorded and recorded != canonical_repo and args.repo is None:
        # RM2523 — `git.repo` a longtemps été rempli avec `root.name`, donc le nom
        # du WORKTREE courant (`<repo>-dev`, `<repo>-rm2356-2373-s1-…`). Ces valeurs
        # héritées désignent bien ce dépôt : on les accepte et on les normalise à
        # l'écriture, au lieu de bloquer une tâche pour un nom mal enregistré.
        if recorded.startswith(canonical_repo):
            out.warn(f"git.repo hérité '{recorded}' (nom de worktree) → normalisé "
                     f"en '{canonical_repo}' (RM2523)")
        else:
            sys.exit(
                f"ERREUR : la tâche RM{args.rm_id} est enregistrée sur le repo de code "
                f"'{recorded}', mais le cwd résout vers '{canonical_repo}'. Place-toi "
                f"dans '{recorded}', ou passe --repo explicitement si le repo a changé.")

    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    base = args.base or current
    if not args.base:
        out.warn(f"--from omis : base = branche courante '{base}' (vérifie que c'est "
                 f"bien la branche d'intégration du projet)")
    base = _resolve_base(root, base, fetch=not args.dry_run)

    # Mode worktree (RM2034) : branche discriminée par session + worktree dédié,
    # pour mener plusieurs tickets en parallèle sans se tromper de cible.
    wt = None
    if args.worktree:
        suffix = f"-m{pm_session.machine_id()}-s<seq>" if args.dry_run else pm_session.branch_suffix()
        branch = f"{args.rm_id}-{slug}{suffix}"
        seq = None if args.dry_run else pm_session.get_session_seq()
        # RM2523 — le nom part du REPO, pas du worktree courant. Il dérivait de
        # `root.name` : lancer pm-branch-start depuis le worktree d'un autre
        # ticket concaténait son nom, d'où les chaînes observées en juillet 2026
        # (`<repo>-rm2356-2373-s1-2385-s1-2323-s20-…`, 7 cas sur ce workspace).
        # Convention unique, alignée sur `pm-env-session create` :
        #     envs/<repo>-rm<id>            (canonique)
        #     envs/<repo>-rm<id>-s<seq>     (si le canonique sert déjà à une AUTRE branche)
        wt = worktree_path(root, args.rm_id, branch, seq)
        # Idempotence indépendante du cwd (RM2240) : si le frontmatter porte déjà
        # le worktree de CETTE branche, le réutiliser — sinon une relance depuis
        # un autre worktree calcule un chemin imbriqué et plante.
        g_peek = peek_task_frontmatter(md_path).get("git") or {}
        if g_peek.get("branch") == branch and g_peek.get("worktree") \
                and Path(g_peek["worktree"]).is_dir():
            wt = Path(g_peek["worktree"])

    exists = _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
                  check=False).returncode == 0
    if args.dry_run:
        # La base retenue figure dans TOUS les cas de création (RM2574) : c'est
        # l'information que l'essai à blanc doit permettre de vérifier.
        action = (f"worktree add {wt}" + ("" if exists else f" (branche depuis {base})")
                  if args.worktree
                  else ("checkout" if exists else f"création depuis {base} +checkout"))
        print(f"--dry-run : {action} pour '{branch}' dans {root} ; CF '{CF_BRANCH_NAME}'={branch} ; "
              f"frontmatter git.repo={canonical_repo}, git.branch={branch}")
        return

    if args.worktree:
        if wt.exists():
            out.info(f"✓ worktree existant '{wt}' (branche '{branch}') réutilisé ({root.name})")
        elif exists:
            _git(root, "worktree", "add", str(wt), branch)
            out.info(f"✓ worktree '{wt}' sur branche existante '{branch}' ({root.name})")
        else:
            _git(root, "worktree", "add", str(wt), "-b", branch, base)
            out.info(f"✓ worktree '{wt}' + branche '{branch}' depuis '{base}' ({root.name})")
        pm_session.record_branch(branch)
        pm_session.record_worktree(str(wt))
    elif exists:
        _git(root, "checkout", branch)
        out.info(f"✓ branche existante '{branch}' checkée out ({root.name})")
    else:
        _git(root, "checkout", "-b", branch, base)
        out.info(f"✓ branche '{branch}' créée depuis '{base}' et checkée out ({root.name})")

    # CF Redmine « GIT Branche »
    cf_id = redmine_utils.cf_id_by_name(CF_BRANCH_NAME)
    cf_ok = False
    if cf_id:
        ok, err = redmine_utils.update_issue_fields(
            args.rm_id, custom_fields=[{"id": cf_id, "value": branch}])
        if ok:
            cf_ok = True
            out.info(f"✓ CF{cf_id} ({CF_BRANCH_NAME}) = {branch}")
        else:
            out.warn(f"CF {CF_BRANCH_NAME} non poussé : {err}")
    else:
        out.warn(f"CF '{CF_BRANCH_NAME}' absent de redmine.reference.yml — skip")

    # Frontmatter git.repo / git.branch + log
    content = md_path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {md_path}")
    fm = yaml.safe_load(m.group(2)) or {}
    git_block = fm.get("git") or {}
    # RM2523 — nom CANONIQUE du dépôt, jamais celui du worktree courant.
    git_block.update({"repo": canonical_repo, "branch": branch})
    if wt is not None:
        git_block["worktree"] = str(wt)
    elif is_linked_worktree(
            _git(root, "rev-parse", "--path-format=absolute", "--git-dir",
                 check=False).stdout.strip(),
            _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir",
                 check=False).stdout.strip()):
        # RM2754 — le dépôt cible EST déjà un worktree dédié, sans que `--worktree`
        # ait été demandé : c'est le flux normal, `pm-task-take` passe `--repo
        # <env de session>`. Sans cette ligne le champ restait vide pour TOUS les
        # tickets pris normalement, donc `pm-task-cd` répondait « mode in-place »
        # et le contrôle n°2 de `pm-pre-commit` — « tu commites depuis le mauvais
        # worktree », le garde-fou phare de RM2240 — n'avait rien à comparer et
        # laissait tout passer.
        git_block["worktree"] = str(root)
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
    out.info(f"✓ frontmatter git.repo/git.branch + log : {md_path.name}")

    # Ligne dense unique (contrat T1, CDC RM2316) — le détail est en --verbose / log.
    out.op("branche", rm=args.rm_id, extra=branch + (" CF3=OK" if cf_ok else ""))

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
            out.warn(f"transition en_cours échouée (exit {r.returncode}) — reprends : "
                     f"pm-task-status-update.py {args.rm_id} en_cours")

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
