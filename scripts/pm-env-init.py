#!/usr/bin/env python3
"""pm-env-init — instancie le LAYOUT GIT d'un workspace projet (RM1947, P1a).

Matérialise l'arborescence uniforme (RM1993) depuis le manifeste
`.mmi-pm/meta.yml › repos:` :

    <workspace>/
    ├── .mmi-pm/         (PM, déjà là — source du manifeste)
    ├── repos/<repo>.git bare(s) : init --bare + remotes du manifeste + fetch
    ├── envs/<repo>-dev  worktree (branche d'intégration, LOCALE)
    ├── envs/<repo>-test worktree main|master  (--with-test, opt-in)
    ├── tmp/ sessions/ logs/ data/   (partagés workspace, untracked)
    └── .gitignore       whitelist .mmi-pm/

PÉRIMÈTRE P1a — layout git PUR, **zéro privilège** (git/fs dans le workspace karl) :
  - strictement ADDITIF, idempotent, --dry-run, réversible (--teardown).
  - branche d'intégration créée en LOCAL seulement (jamais de push — non-intrusif remote).

HORS P1a (renvois) :
  - runtime : vhost / BDD / config app / pool FPM            → P1b (provisionneurs)
  - implements / alternates (--reference produit partagé)    → RM1837 / P3
  - session-worktrees <repo>-rm<id> (en_cours→fermeture)     → RM1834 / P3

Modèle de bare (multi-remote propre) : `git init --bare` puis un `remote add` par
entrée du manifeste (origin obligatoire) + `fetch`. Les têtes distantes vivent dans
`refs/remotes/<k>/*` ; `refs/heads/*` n'est peuplé QUE par les worktrees → pas de
collision, uniforme quel que soit le nombre de remotes.

Forme d'un remote (RM2838) — une CHAÎNE reste le transport, comme depuis toujours :

    remotes: {origin: "gitlab:<owner>/<repo>.git"}

ou un mapping, pour noter l'identité EN PLUS du transport (cf. `pm_repos`) :

    remotes:
      origin:
        url: https://gogs.materiaux-naturels.fr/<owner>/<repo>.git   # identité
        ssh: ssh://gogs@matnat-tools/<owner>/<repo>.git              # transport

`git remote add` reçoit le transport (`ssh`, sinon `url`) ; l'`url` sert à rattacher
le dépôt à une instance du registre — ce qu'un alias tunnelé ne permet pas de déduire.

N'auto-committe RIEN côté PM (pm_git) : opère sur les repos du workspace, pas sur
le repo PM.
"""
import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pm-env-init: PyYAML requis (apt install python3-yaml)")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_repos  # transport vs identité d'un remote (RM2838)  # noqa: E402
import pm_ws_skeleton  # squelette sous racine verrouillée (RM2909)  # noqa: E402

SHARED_DIRS = ("tmp", "sessions", "logs", "data")
GITIGNORE = (
    "# Généré par pm-env-init (RM1947). Seul .mmi-pm/ est tracké ; tout le reste\n"
    "# (code en worktrees, bares, runtime) est local/régénérable.\n"
    "/*\n"
    "!/.gitignore\n"
    "!/.mmi-pm/\n"
)


class Ctx:
    """Contexte d'exécution : dry-run + verbosité + compteur d'actions."""

    def __init__(self, dry: bool, verbose: bool):
        self.dry = dry
        self.verbose = verbose
        self.changed = 0

    def act(self, msg: str):
        """Annonce une mutation (faite, ou prévue en dry-run)."""
        print(f"  {'[dry] ' if self.dry else ''}{msg}")
        self.changed += 1

    def skip(self, msg: str):
        if self.verbose:
            print(f"  · {msg}")


def die(msg: str):
    sys.exit(f"pm-env-init: {msg}")


def git(args, cwd=None, check=True, quiet=False):
    """Wrapper subprocess git. Retourne (rc, stdout)."""
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        if not quiet:
            sys.stderr.write(r.stderr)
        die(f"git {' '.join(args)} a échoué (rc={r.returncode})")
    return r.returncode, r.stdout.strip()


# ---------------------------------------------------------------- découverte

def find_workspace(start: Path) -> Path:
    """Remonte depuis `start` jusqu'au dossier contenant `.mmi-pm/` (le workspace)."""
    for d in [start, *start.parents]:
        if (d / ".mmi-pm").exists():
            return d
    die(f"aucun `.mmi-pm` trouvé en remontant depuis {start} "
        f"(es-tu dans un workspace PM-tracké ?)")


def load_repos(ws: Path) -> list[dict]:
    """Lit `.mmi-pm/meta.yml › repos:` et valide le schéma minimal (RM1993)."""
    meta = ws / ".mmi-pm" / "meta.yml"
    if not meta.is_file():
        die(f"manifeste absent : {meta}")
    try:
        data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        die(f"meta.yml illisible : {e}")
    repos = data.get("repos")
    if not repos:
        die("aucune clé `repos:` dans le manifeste — rien à instancier.\n"
            "  Déclare au moins :\n"
            "    repos:\n"
            "      - name: <repo>\n"
            "        remotes: {origin: gitlab:<...>}\n"
            "    (ou, pour noter l'identité EN PLUS du transport :\n"
            "        remotes: {origin: {url: https://<forge>/<owner>/<repo>.git,\n"
            "                           ssh: gitlab:<owner>/<repo>.git}})\n"
            "        integration_branch: dev")
    for i, r in enumerate(repos):
        if not r.get("name"):
            die(f"repos[{i}] sans `name`")
        rem = r.get("remotes") or {}
        if "origin" not in rem:
            die(f"repos[{r.get('name')}] : remote `origin` obligatoire")
        # RM2838 : chaque remote est une chaîne (transport pur, historique) ou un
        # mapping {url, ssh}. Valider ICI évite de découvrir la faute au milieu
        # d'un `git remote add`, à moitié instancié.
        try:
            pm_repos.validate_remotes(r)
        except pm_repos.RepoConfError as e:
            die(str(e))
    return repos


# ------------------------------------------------------------------ git ops

def remote_heads(bare: Path) -> set[str]:
    """Branches connues côté remotes (refs/remotes/*/<head>)."""
    _, out = git(["-C", str(bare), "for-each-ref", "--format=%(refname)",
                  "refs/remotes"], check=False)
    heads = set()
    for ref in out.splitlines():
        # refs/remotes/<remote>/<branch...>
        parts = ref.split("/", 3)
        if len(parts) == 4:
            heads.add(parts[3])
    return heads


def local_heads(bare: Path) -> set[str]:
    _, out = git(["-C", str(bare), "for-each-ref", "--format=%(refname:short)",
                  "refs/heads"], check=False)
    return set(out.split()) if out else set()


def ensure_bare(ctx: Ctx, ws: Path, repo: dict):
    """Crée/réconcilie le bare repos/<name>.git + ses remotes (idempotent)."""
    name = repo["name"]
    bare = ws / "repos" / f"{name}.git"
    remotes = repo["remotes"]

    if not bare.exists():
        ctx.act(f"git init --bare repos/{name}.git")
        if not ctx.dry:
            bare.parent.mkdir(parents=True, exist_ok=True)
            git(["init", "--bare", "-q", str(bare)])
            git(["-C", str(bare), "config", "gc.auto", "0"])
    else:
        ctx.skip(f"bare repos/{name}.git déjà présent")
        if not ctx.dry:
            git(["-C", str(bare), "config", "gc.auto", "0"])

    # remotes : origin d'abord, puis le reste (ordre déterministe).
    # Lecture de l'état même en dry-run (read-only) → preview fidèle.
    existing = set()
    if bare.exists():
        _, out = git(["-C", str(bare), "remote"], check=False)
        existing = set(out.split())
    ordered = ["origin"] + sorted(k for k in remotes if k != "origin")
    for k in ordered:
        # Le transport, pas l'identité (RM2838) : `ssh` s'il est déclaré, sinon
        # `url`. Une chaîne reste elle-même — comportement historique.
        url = pm_repos.remote_transport(remotes[k], f"repos[{name}].remotes.{k}")
        if k in existing:
            ctx.skip(f"remote {k} déjà configuré")
            continue
        ctx.act(f"git remote add {k} {url}  (repos/{name}.git)")
        if not ctx.dry:
            git(["-C", str(bare), "remote", "add", k, url])

    # fetch (peuple refs/remotes/<k>/*)
    if not ctx.dry and bare.exists():
        for k in ordered:
            rc, _ = git(["-C", str(bare), "fetch", "--quiet", k], check=False, quiet=True)
            if rc != 0:
                sys.stderr.write(f"  ⚠ fetch {k} a échoué (remote injoignable ?) — continue\n")
    elif ctx.dry:
        ctx.act(f"git fetch (tous remotes)  (repos/{name}.git)")
    return bare


def resolve_branch(bare: Path, integration_branch: str | None):
    """Résout la branche d'intégration : explicite → dev → develop → (créée main|master).

    Retourne (mode, branch, base) :
      mode 'local'  : branche locale existante (base=None)
      mode 'track'  : créer locale en tracking d'un remote head (base='origin/<b>')
      mode 'create' : créer locale depuis un base main|master (base='origin/<base>')
    """
    rheads, lheads = remote_heads(bare), local_heads(bare)
    cands = [integration_branch] if integration_branch else ["dev", "develop"]
    for c in cands:
        if c in lheads:
            return ("local", c, None)
        if c in rheads:
            return ("track", c, f"origin/{c}")
    # aucune : créer depuis main|master
    base = next((b for b in ("main", "master") if b in rheads), None)
    if not base:
        die(f"ni dev/develop ni main/master sur les remotes de {bare.name} "
            f"(remotes vides ? fetch échoué ?)")
    return ("create", integration_branch or "dev", f"origin/{base}")


def add_worktree(ctx: Ctx, ws: Path, bare: Path, wt_name: str, mode: str,
                 branch: str, base: str | None):
    """Monte envs/<wt_name> sur `branch` (idempotent)."""
    wt = ws / "envs" / wt_name
    if wt.exists():
        ctx.skip(f"worktree envs/{wt_name} déjà monté")
        return wt
    rel = f"envs/{wt_name}"
    if mode == "local":
        ctx.act(f"git worktree add {rel} {branch}")
        cmd = ["worktree", "add", str(wt), branch]
    else:  # track | create : créer la branche locale depuis `base`
        verb = "tracking" if mode == "track" else "créée depuis"
        ctx.act(f"git worktree add -b {branch} {rel} {base}  ({verb})")
        cmd = ["worktree", "add", "-b", branch, str(wt), base]
    if not ctx.dry:
        (ws / "envs").mkdir(parents=True, exist_ok=True)
        git(["-C", str(bare), *cmd])
    return wt


# --------------------------------------------------------------- scaffolding

def ensure_scaffolding(ctx: Ctx, ws: Path):
    """Crée les dossiers partagés + .gitignore (idempotent, untracked)."""
    for d in SHARED_DIRS:
        p = ws / d
        if p.exists():
            ctx.skip(f"{d}/ déjà présent")
        else:
            ctx.act(f"mkdir {d}/")
            if not ctx.dry:
                p.mkdir(parents=True, exist_ok=True)
    gi = ws / ".gitignore"
    if gi.is_file() and gi.read_text(encoding="utf-8") == GITIGNORE:
        ctx.skip(".gitignore déjà à jour")
    else:
        ctx.act("écrit .gitignore (whitelist .mmi-pm/)")
        if not ctx.dry:
            gi.write_text(GITIGNORE, encoding="utf-8")


# ------------------------------------------------------------------ teardown

def teardown(ctx: Ctx, ws: Path, repos: list[dict], only: set[str],
             purge: bool, assume_yes: bool):
    """Retire les worktrees envs/<repo>-* ; bares seulement avec --purge + confirmation."""
    for repo in repos:
        name = repo["name"]
        if only and name not in only:
            continue
        bare = ws / "repos" / f"{name}.git"
        if not bare.exists():
            ctx.skip(f"repos/{name}.git absent — rien à défaire")
            continue
        # worktrees connus du bare
        _, out = git(["-C", str(bare), "worktree", "list", "--porcelain"], check=False)
        wts = [ln.split(" ", 1)[1] for ln in out.splitlines() if ln.startswith("worktree ")]
        for wtpath in wts:
            p = Path(wtpath)
            if p == bare or bare in p.parents:
                continue  # le bare lui-même
            # refuse de détruire un worktree sale (commits/edits non sauvegardés)
            _, st = git(["-C", wtpath, "status", "--porcelain"], check=False)
            if st.strip():
                sys.stderr.write(f"  ⚠ {p.name} a des modifs non commitées — sauté "
                                 f"(commit/stash d'abord)\n")
                continue
            ctx.act(f"git worktree remove {p.name}")
            if not ctx.dry:
                git(["-C", str(bare), "worktree", "remove", wtpath])
        if purge:
            if not assume_yes and not ctx.dry:
                ans = input(f"  ⚠ SUPPRIMER le bare repos/{name}.git "
                            f"(commits/branches LOCAUX non poussés perdus) ? [y/N] ")
                if ans.strip().lower() != "y":
                    print("    → conservé")
                    continue
            ctx.act(f"rm -rf repos/{name}.git")
            if not ctx.dry:
                import shutil
                shutil.rmtree(bare)


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        prog="pm-env-init",
        description="Instancie le layout git d'un workspace projet (RM1947 P1a).")
    ap.add_argument("workspace", nargs="?", default=None,
                    help="dossier workspace (défaut : découverte depuis cwd via .mmi-pm)")
    ap.add_argument("--repo", action="append", default=[], metavar="NAME",
                    help="restreint aux repos nommés (défaut : tous)")
    ap.add_argument("--with-test", action="store_true",
                    help="monte aussi envs/<repo>-test sur main|master")
    ap.add_argument("--teardown", action="store_true",
                    help="retire les worktrees (réversibilité) ; bares avec --purge")
    ap.add_argument("--purge", action="store_true",
                    help="avec --teardown : supprime aussi les bares (confirmation requise)")
    ap.add_argument("-y", "--yes", action="store_true", help="non-interactif (confirme --purge)")
    ap.add_argument("--dry-run", action="store_true", help="prévisualise, aucune mutation")
    ap.add_argument("-v", "--verbose", action="store_true", help="affiche aussi les no-op")
    ap.add_argument("--print-gitignore", action="store_true",
                    help="émet le .gitignore du layout sur stdout et sort. Contrat consommé "
                         "par `pm-env-helper ws-init` (RM2909) : à la racine d'un workspace au "
                         "modèle (2750), créer ce fichier est une op privilégiée — le texte "
                         "reste défini ICI, jamais recopié dans le shell du helper.")
    args = ap.parse_args()

    if args.print_gitignore:
        sys.stdout.write(GITIGNORE)
        return

    start = Path(args.workspace).resolve() if args.workspace else Path.cwd()
    if args.workspace and not start.is_dir():
        die(f"{start} n'est pas un dossier")
    ws = find_workspace(start)
    repos = load_repos(ws)
    only = set(args.repo)
    if only:
        unknown = only - {r["name"] for r in repos}
        if unknown:
            die(f"repo(s) inconnu(s) du manifeste : {', '.join(sorted(unknown))}")

    ctx = Ctx(args.dry_run, args.verbose)
    print(f"workspace : {ws}")

    # Modèle multi-user (RM2438 / T6 RM2502) : la racine est en `2750 pm:pm`, group r-x
    # — créer `repos/`, `envs/` ou les partagés du layout y est une op PRIVILÉGIÉE. Le
    # verbe NOPASSWD dédié (RM2909) la porte ; sans lui on échouait en `Permission
    # denied` au milieu de l'instanciation, à réparer par deux sudo interactifs.
    if not args.teardown:
        pm_ws_skeleton.ensure_skeleton(ws, ctx.dry)

    if args.teardown:
        teardown(ctx, ws, repos, only, args.purge, args.yes)
        print(f"\n{'[dry-run] ' if ctx.dry else ''}teardown : {ctx.changed} action(s).")
        return

    for repo in repos:
        name = repo["name"]
        if only and name not in only:
            continue
        if repo.get("implements"):
            sys.stderr.write(f"  ⚠ {name} a `implements:` → différé RM1837/P3, repo sauté\n")
            continue
        print(f"\n• repo {name}")
        bare = ensure_bare(ctx, ws, repo)
        if ctx.dry and not bare.exists():
            # en dry-run sur un workspace vierge, pas de bare pour résoudre la branche
            ctx.act(f"git worktree add envs/{name}-dev <branche d'intégration résolue>")
            if args.with_test:
                ctx.act(f"git worktree add envs/{name}-test main|master")
            continue
        mode, branch, base = resolve_branch(bare, repo.get("integration_branch"))
        add_worktree(ctx, ws, bare, f"{name}-dev", mode, branch, base)
        if args.with_test:
            # -test = main|master explicitement (jamais dev/develop)
            rheads = remote_heads(bare)
            tb = next((b for b in ("main", "master") if b in rheads), None)
            if tb:
                add_worktree(ctx, ws, bare, f"{name}-test", "track", tb, f"origin/{tb}")
            else:
                sys.stderr.write(f"  ⚠ {name} : pas de main|master → -test sauté\n")

    ensure_scaffolding(ctx, ws)
    # Verbe symétrique : ce qui vient d'être créé l'a été sous l'identité de l'appelant
    # (worktrees, bares) — on repasse le modèle pour refermer. No-op hors modèle.
    pm_ws_skeleton.apply_perms(ws, ctx.dry)
    print(f"\n{'[dry-run] ' if ctx.dry else ''}terminé : {ctx.changed} action(s) "
          f"sur {ws}.")


if __name__ == "__main__":
    main()
