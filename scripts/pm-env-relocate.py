#!/usr/bin/env python3
"""pm-env-relocate — déplacer des envs existants vers la disposition des réglages, les vhosts suivant (RM3209).

    mmi-pm env-relocate --plan plan.yml [--dry-run]
    sudo mmi-pm env-relocate --plan plan.yml --snapshot "<nom du snapshot ZFS pris sur l'hôte>" [--reload]
    sudo mmi-pm env-relocate --undo <journal.json>

Cas d'origine : MatNat (décision du 2026-09-16, « déplacer les envs actuels et faire suivre les vhosts »). Chaque
dev y a des clones complets (`/home/matnat_sf7/<dev>`, `<dev>2`…), servis par des vhosts fixes. Cible : des envs
sous `<workspace>/envs/[<utilisateur>/]`, worktrees du dépôt de leur propriétaire (`git.worktree_source=per_user`).

Plan (YAML, relu AVANT exécution) :

    workspace: /home/matnat_sf7          # racine du projet : envs/ y est créé
    repo: matnat_sf7                     # nom du dépôt dans le dossier des dépôts de chaque propriétaire
    compat_links: [AGENTS.md, data_dev, agent_config]
    references: [/etc/apache2/sites-enabled/matnat_sf7.conf, /etc/php/*/fpm/pool.d/*.conf, /home/matnat_sf7/*.sh]
    validate: ["apachectl configtest"]   # défaut : apachectl configtest si un fichier Apache est touché
    envs:
      - from: /home/matnat_sf7/alexandre2
        name: matnat_sf7-2               # nom de l'env (destination selon git.envs_layout)
        owner: alexandre                 # défaut : propriétaire du dossier
        adopt: true                      # défaut : devient un worktree du dépôt du propriétaire
        post: ["runuser -u {owner} -- php {dest}/bin/console cache:clear"]   # optionnel, non bloquant

Ce que l'outil garantit :
- contrôle préalable COMPLET avant toute mutation (sources, destinations, même système de fichiers, propriétaires) ;
- déplacement par RENOMMAGE (même système de fichiers exigé : jamais de copie de plusieurs Go) ;
- liens de compatibilité dans le nouveau parent pour les liens relatifs qui sortent de l'env (`data -> ../data_dev`) :
  aucun fichier suivi par git n'est modifié ;
- adoption SANS PERTE : branches locales et stashes importés dans le dépôt du propriétaire
  (`relocate/<env>/…`), arbre de travail intact (worktree `--no-checkout` + `reset` mixte) ; vérifié (même commit,
  mêmes fichiers modifiés), sinon l'adoption est annulée et l'env reste un clone complet, valide, à sa nouvelle place ;
- réécriture des références au chemin EXACT (`/home/x/alexandre` ne touche pas `/home/x/alexandre2`), sauvegardes,
  validation ; échec de validation ⇒ toutes les références restaurées ;
- un journal JSON, et `--undo` qui défait tout dans l'ordre inverse.

Snapshot ZFS : pris sur l'HÔTE avant exécution (le conteneur n'y a pas accès) — son nom est exigé et journalisé
(`--snapshot`), ou `--no-snapshot` assumé explicitement.
"""
import argparse
import datetime
import difflib
import glob
import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_worktrees   # noqa: E402

ME = pwd.getpwuid(os.geteuid()).pw_name


class RelocateError(Exception):
    pass


# ── Exécution git sous l'identité du propriétaire ─────────────────────────────────────────────────────────
def as_owner(owner: str, argv: list) -> list:
    if owner == ME:
        return argv
    if os.geteuid() == 0:
        return ["runuser", "-u", owner, "--", *argv]
    raise RelocateError(f"opération pour le compte « {owner} » : relancer avec sudo")


def git(owner: str, repo: Path, *args, check=True) -> str:
    r = subprocess.run(as_owner(owner, ["git", "-C", str(repo), *args]), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RelocateError(f"git {' '.join(args)} ({repo}) : {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def changed_paths(owner: str, repo: Path) -> set:
    """Chemins suivis modifiés (indexés ou non) — comparés avant/après adoption sans tenir compte de l'index."""
    out = git(owner, repo, "status", "--porcelain=v1", "-uno", "-z")
    paths = set()
    for rec in out.split("\0"):
        if len(rec) > 3:
            paths.add(rec[3:])
    return paths


# ── Plan ─────────────────────────────────────────────────────────────────────────────────────────────────
def load_plan(path: Path) -> dict:
    try:
        plan = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise RelocateError(f"plan illisible : {e}")
    for key in ("workspace", "repo", "envs"):
        if not plan.get(key):
            raise RelocateError(f"plan : clé `{key}` obligatoire")
    if not isinstance(plan["envs"], list):
        raise RelocateError("plan : `envs` doit être une liste")
    names = [e.get("name") for e in plan["envs"]]
    if len(set(names)) != len(names) or not all(names):
        raise RelocateError("plan : chaque env porte un `name` unique")
    return plan


def resolve_plan(plan: dict, layout: pm_worktrees.Layout, st_dev=lambda p: os.stat(p).st_dev) -> list:
    """Entrées complètes et contrôlées. Aucune mutation : toute erreur arrête AVANT d'avoir touché quoi que ce soit."""
    ws = Path(plan["workspace"])
    if not ws.is_dir():
        raise RelocateError(f"workspace absent : {ws}")
    errors, entries = [], []
    for e in plan["envs"]:
        src = Path(e.get("from") or "")
        if not src.is_dir():
            errors.append(f"{e['name']} : source absente {src}")
            continue
        owner = e.get("owner") or pwd.getpwuid(src.stat().st_uid).pw_name
        try:
            pwd.getpwnam(owner)
        except KeyError:
            errors.append(f"{e['name']} : propriétaire inconnu « {owner} »")
            continue
        adopt = e.get("adopt", True)
        if not (src / ".git").is_dir():
            errors.append(f"{e['name']} : {src} n'est pas un clone (pas de dossier .git) — déjà adopté ?")
            continue
        if adopt and layout.source != "per_user":
            errors.append(f"{e['name']} : adoption demandée alors que git.worktree_source={layout.source} "
                          "(pour un dépôt central : pm-env-migrate)")
            continue
        dest = pm_worktrees.env_dir(ws, e["name"], layout, owner)
        if dest.exists() or dest.is_symlink():
            errors.append(f"{e['name']} : destination déjà occupée {dest}")
            continue
        if st_dev(src) != st_dev(ws):
            errors.append(f"{e['name']} : {src} et {ws} ne sont pas sur le même système de fichiers — "
                          "l'outil déplace par renommage, jamais par copie")
            continue
        repos_dir = pm_worktrees.user_repos_dir(owner) if adopt else None
        entries.append({"name": e["name"], "from": str(src), "dest": str(dest), "owner": owner, "adopt": adopt,
                        "source_repo": str(Path(repos_dir) / plan["repo"]) if adopt else None,
                        "post": list(e.get("post") or [])})
    dests = [x["dest"] for x in entries]
    if len(set(dests)) != len(dests):
        errors.append("deux envs visent la même destination")
    if errors:
        raise RelocateError("contrôle préalable :\n  - " + "\n  - ".join(errors))
    return entries


# ── Références ───────────────────────────────────────────────────────────────────────────────────────────
def reference_files(patterns) -> list:
    files = []
    for pat in patterns or []:
        for f in sorted(glob.glob(pat)):
            if Path(f).is_file() and f not in files:
                files.append(f)
    return files


def rewrite_text(text: str, moves: list) -> str:
    """Remplace chaque ancien chemin par le nouveau, au chemin EXACT : un chemin n'est pas le préfixe d'un autre
    (`/home/x/alexandre` ne touche pas `/home/x/alexandre2`). Les plus longs d'abord."""
    for old, new in sorted(moves, key=lambda m: -len(m[0])):
        text = re.sub(re.escape(old) + r"(?![A-Za-z0-9_.\-])", lambda _m, n=new: n, text)
    return text


# ── Opérations ───────────────────────────────────────────────────────────────────────────────────────────
class Run:
    def __init__(self, dry: bool, journal_path: Path):
        self.dry, self.journal_path, self.ops = dry, journal_path, []

    def say(self, msg):
        print(("  [essai] " if self.dry else "  → ") + msg)

    def record(self, **op):
        self.ops.append(op)
        if not self.dry:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            self.journal_path.write_text(json.dumps({"ops": self.ops}, ensure_ascii=False, indent=1), encoding="utf-8")


def ensure_source_repo(run: Run, env: dict):
    src_repo, owner, clone = Path(env["source_repo"]), env["owner"], Path(env["from"])
    if (src_repo / ".git").exists():
        return
    run.say(f"dépôt de {owner} absent → clone local (objets partagés) {clone} → {src_repo}")
    if run.dry:
        return
    src_repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(as_owner(owner, ["git", "clone", "-q", "--no-checkout", str(clone), str(src_repo)]), check=True)
    origin = git(owner, clone, "remote", "get-url", "origin", check=False)
    if origin:
        git(owner, src_repo, "remote", "set-url", "origin", origin)
    head = git(owner, clone, "rev-parse", "HEAD")
    git(owner, src_repo, "update-ref", "--no-deref", "HEAD", head)     # HEAD détaché : aucune branche occupée
    git(owner, src_repo, "reset", "-q")
    run.record(op="clone", repo=str(src_repo), owner=owner)


def import_refs(run: Run, env: dict):
    clone, src_repo, owner, name = Path(env["from"]), Path(env["source_repo"]), env["owner"], env["name"]
    stashes = git(owner, clone, "stash", "list", "--format=%H").split()
    run.say(f"import des branches locales et de {len(stashes)} stash(es) de {name} → relocate/{name}/…")
    if run.dry:
        return
    for i, sha in enumerate(stashes):
        git(owner, clone, "update-ref", f"refs/pm-relocate/stash/{i}", sha)
    try:
        git(owner, src_repo, "fetch", "-q", "--no-tags", str(clone),
            f"+refs/heads/*:refs/heads/relocate/{name}/*", f"+refs/pm-relocate/stash/*:refs/relocate/{name}/stash/*")
    finally:
        for i in range(len(stashes)):
            git(owner, clone, "update-ref", "-d", f"refs/pm-relocate/stash/{i}", check=False)
    run.record(op="import", repo=str(src_repo), owner=owner, name=name)


def checkout_target(env: dict, head_branch: str, head_sha: str) -> list:
    """Ce que le worktree adopté extrait : la branche d'origine si elle est libre et au même commit ; sinon la copie
    importée `relocate/<env>/<branche>` ; HEAD détaché si l'env l'était."""
    owner, src_repo, name = env["owner"], Path(env["source_repo"]), env["name"]
    if head_branch == "HEAD":
        return ["--detach", head_sha]
    occupied = {ln.split(" ", 1)[1][len("refs/heads/"):] for ln in
                git(owner, src_repo, "worktree", "list", "--porcelain").splitlines() if ln.startswith("branch ")}
    local = git(owner, src_repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{head_branch}", check=False)
    if head_branch not in occupied and (not local or local == head_sha):
        if not local:
            git(owner, src_repo, "branch", head_branch, head_sha)
        return [head_branch]
    return [f"relocate/{name}/{head_branch}"]


def adopt(run: Run, env: dict, before: dict):
    dest, owner, src_repo, name = Path(env["dest"]), env["owner"], Path(env["source_repo"]), env["name"]
    staging = dest.parent / ".pm-relocate-staging" / name
    backup = dest.parent / f".{name}.git-avant-relocate"
    run.say(f"adoption de {name} en worktree de {src_repo} (arbre de travail intact)")
    if run.dry:
        return
    target = checkout_target(env, before["branch"], before["sha"])
    staging.parent.mkdir(parents=True, exist_ok=True)
    git(owner, src_repo, "worktree", "add", "--no-checkout", "-q", str(staging), *target)
    try:
        os.rename(dest / ".git", backup)
        os.rename(staging / ".git", dest / ".git")
        shutil.rmtree(staging.parent, ignore_errors=True)
        git(owner, src_repo, "worktree", "repair", str(dest))
        git(owner, dest, "reset", "-q")
        after_sha = git(owner, dest, "rev-parse", "HEAD")
        after_paths = changed_paths(owner, dest)
        if after_sha != before["sha"] or after_paths != before["paths"]:
            raise RelocateError(f"vérification : commit {before['sha'][:10]}→{after_sha[:10]}, "
                                f"{len(before['paths'])}→{len(after_paths)} fichier(s) modifié(s)")
    except Exception as e:
        # l'env redevient un clone complet, valide, à sa nouvelle place
        if (dest / ".git").is_file():
            (dest / ".git").unlink()
        if backup.exists():
            os.rename(backup, dest / ".git")
        shutil.rmtree(staging.parent, ignore_errors=True)
        git(owner, src_repo, "worktree", "prune", check=False)
        print(f"  ⚠ adoption de {name} annulée ({e}) — l'env reste un clone complet à {dest}")
        return
    run.record(op="adopt", dest=str(dest), backup=str(backup), repo=str(src_repo), owner=owner,
               branch=" ".join(target))
    print(f"    ✓ {name} : worktree sur {' '.join(target)} ; ancien .git conservé dans {backup.name}")


def relocate(plan: dict, entries: list, run: Run, reload: bool) -> int:
    ws = Path(plan["workspace"])
    before = {}
    for env in entries:
        clone = Path(env["from"])
        before[env["name"]] = {"sha": git(env["owner"], clone, "rev-parse", "HEAD"),
                               "branch": git(env["owner"], clone, "rev-parse", "--abbrev-ref", "HEAD"),
                               "paths": changed_paths(env["owner"], clone)}
    for env in entries:
        src, dest = Path(env["from"]), Path(env["dest"])
        print(f"\n{env['name']} : {src} → {dest}  (propriétaire {env['owner']})")
        if env["adopt"]:
            ensure_source_repo(run, env)
            import_refs(run, env)
        run.say(f"renommage {src} → {dest}")
        if not run.dry:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.parent != ws / "envs" and os.geteuid() == 0:
                os.chown(dest.parent, pwd.getpwnam(env["owner"]).pw_uid, dest.parent.parent.stat().st_gid)
            os.rename(src, dest)
            run.record(op="move", src=str(src), dest=str(dest))
        for link in plan.get("compat_links") or []:
            lk, target = dest.parent / link, src.parent / link
            if lk.exists() or lk.is_symlink():
                if not (lk.is_symlink() and os.readlink(lk) == str(target)):
                    print(f"  ⚠ lien de compatibilité {lk} : existe déjà et vise ailleurs — laissé tel quel")
                continue
            if not (target.exists() or target.is_symlink()):
                continue
            run.say(f"lien de compatibilité {lk} → {target}")
            if not run.dry:
                lk.symlink_to(target)
                run.record(op="link", path=str(lk))
        if env["adopt"]:
            adopt(run, env, before[env["name"]])

    moves = [(e["from"], e["dest"]) for e in entries]
    touched = []
    for f in reference_files(plan.get("references")):
        old = Path(f).read_text(encoding="utf-8")
        new = rewrite_text(old, moves)
        if new == old:
            continue
        touched.append(f)
        print(f"\nréférence {f}")
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f, f, n=0))
        if not run.dry:
            st = os.stat(f)
            backup = f"{f}.avant-relocate-{run.journal_path.stem}"
            shutil.copy2(f, backup)
            tmp = f + ".pm-relocate-tmp"
            Path(tmp).write_text(new, encoding="utf-8")
            os.chmod(tmp, st.st_mode & 0o7777)
            if os.geteuid() == 0:
                os.chown(tmp, st.st_uid, st.st_gid)
            os.replace(tmp, f)
            run.record(op="reference", path=f, backup=backup)

    checks = plan.get("validate")
    if checks is None:
        checks = ["apachectl configtest"] if any(t.startswith("/etc/apache2/") for t in touched) else []
    for cmd in checks:
        run.say(f"validation : {cmd}")
        if run.dry:
            continue
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ✗ validation en échec : {(r.stderr or r.stdout).strip()[:400]}")
            for op in reversed(run.ops):
                if op["op"] == "reference":
                    shutil.copy2(op["backup"], op["path"])
            print("  ↩ références restaurées. Envs déplacés : `--undo " + str(run.journal_path) + "` pour tout défaire.")
            return 3
    for env in entries:
        for cmd in env["post"]:
            c = cmd.format(dest=shlex.quote(env["dest"]), src=shlex.quote(env["from"]), owner=env["owner"])
            run.say(f"après {env['name']} : {c}")
            if not run.dry:
                r = subprocess.run(c, shell=True, capture_output=True, text=True)
                if r.returncode != 0:
                    print(f"  ⚠ {c} : code {r.returncode} (non bloquant)")
    if reload and touched and not run.dry:
        units = ["apache2"] if any(t.startswith("/etc/apache2/") for t in touched) else []
        units += sorted({f"php{m.group(1)}-fpm" for t in touched for m in [re.match(r"/etc/php/([\d.]+)/fpm/", t)] if m})
        for u in units:
            run.say(f"rechargement {u}")
            subprocess.run(["systemctl", "reload", u], check=False)
    print(f"\n{'plan affiché, rien d écrit' if run.dry else 'journal : ' + str(run.journal_path)}".replace("d écrit", "d'écrit"))
    return 0


def undo(journal: Path) -> int:
    ops = json.loads(Path(journal).read_text(encoding="utf-8"))["ops"]
    for op in reversed(ops):
        kind = op["op"]
        if kind == "reference":
            shutil.copy2(op["backup"], op["path"])
            print(f"  ↩ référence restaurée : {op['path']}")
        elif kind == "adopt":
            dest, backup = Path(op["dest"]), Path(op["backup"])
            if (dest / ".git").is_file():
                (dest / ".git").unlink()
            if backup.exists():
                os.rename(backup, dest / ".git")
            git(op["owner"], Path(op["repo"]), "worktree", "prune", check=False)
            print(f"  ↩ adoption défaite : {dest} redevient un clone complet")
        elif kind == "link":
            p = Path(op["path"])
            if p.is_symlink():
                p.unlink()
                print(f"  ↩ lien retiré : {p}")
        elif kind == "move":
            os.rename(op["dest"], op["src"])
            print(f"  ↩ remis en place : {op['src']}")
    print("undo terminé (les dépôts clonés et les refs importées sont conservés : ils ne gênent rien)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mmi-pm env-relocate", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", type=Path, help="plan YAML (relu avant exécution)")
    g.add_argument("--undo", type=Path, metavar="JOURNAL", help="défaire une exécution d'après son journal")
    ap.add_argument("--dry-run", action="store_true", help="contrôle, plan et diffs ; rien d'écrit")
    s = ap.add_mutually_exclusive_group()
    s.add_argument("--snapshot", help="nom du snapshot ZFS pris sur l'hôte avant exécution (journalisé)")
    s.add_argument("--no-snapshot", action="store_true", help="sans snapshot : réversibilité à ta charge")
    ap.add_argument("--reload", action="store_true", help="recharger Apache / PHP-FPM si leurs fichiers ont changé")
    ap.add_argument("--journal", type=Path, help="chemin du journal (défaut : <workspace>/.pm-relocate/<horodatage>.json)")
    args = ap.parse_args(argv)
    try:
        if args.undo:
            return undo(args.undo)
        if not args.dry_run and not (args.snapshot or args.no_snapshot):
            raise RelocateError("snapshot ZFS préalable exigé : --snapshot \"<nom>\" (pris sur l'hôte), "
                                "ou --no-snapshot assumé")
        plan = load_plan(args.plan)
        layout = pm_worktrees.read_layout()
        entries = resolve_plan(plan, layout)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        journal = args.journal or Path(plan["workspace"]) / ".pm-relocate" / f"{stamp}.json"
        print(f"disposition : worktree_source={layout.source}, envs_layout={layout.envs_layout} ; {len(entries)} env(s)")
        run = Run(args.dry_run, journal)
        if not args.dry_run:
            run.record(op="start", plan=str(args.plan), snapshot=args.snapshot or "(aucun, assumé)")
        return relocate(plan, entries, run, args.reload)
    except RelocateError as e:
        print(f"pm-env-relocate : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
