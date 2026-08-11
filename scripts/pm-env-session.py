#!/usr/bin/env python3
"""pm-env-session — env de SESSION par ticket : worktree + runtime (RM1834).

Crée / démonte l'environnement éphémère d'un ticket dans un workspace projet
au layout RM1993 (`repos/<repo>.git` + `envs/`) :

    create   worktree `envs/<repo>-rm<id>` sur branche `<id>-<slug>` — si la
             branche exacte n'existe pas, toute branche locale/remote `<id>-*`
             est réutilisée (RM2229 : pm-branch-start tronque les slugs)
             + `.user.ini` (error_log par worktree, pool FPM PARTAGÉ du workspace)
             + canari `<docroot>/pm-env.txt` = nom d'env (sonde de vivacité
               cockpit : un vhost absent répond 200 via le site Apache par
               défaut — seul le canari prouve que CET env est servi)
             + vhost Apache `<repo>-rm<id>.lxc` (via helper privilégié)
             + BDD : partagée par défaut ; `--db-clone` = clone dédié `<db>_rm<id>`
             + étapes `runtime.post_create` / `post_create_container` (setup
               appli : vendor, assets… — re-exécutées sur un env déjà monté,
               ce qui fait de create l'action « réparer » du cockpit, RM2229)
    teardown vhost + worktree + logs + drop du clone BDD éventuel
             — la branche N'EST JAMAIS supprimée (NORMS), la BDD partagée non plus.
    list     envs de session présents dans le workspace

Runtime déclaré dans `.mmi-pm/meta.yml › repos[] › runtime:` :

    repos:
    - name: matnat_sf7
      remotes: {origin: ...}
      integration_branch: dev
      runtime:            # absent = env « code seul » (pas de vhost/.user.ini/BDD)
        pool: matnat-84   # pool FPM partagé du workspace (RM2081)
        docroot: public   # sous-dossier servi dans l'env
        db: matnat        # BDD dev partagée (source des clones à la demande)
        db_clone_default: false   # défaut PROJET : cloner la BDD par ticket ?
        db_clone:                 # paramètres du clone (optionnels)
          exclude_tables: [log_%, cache%]   # motifs LIKE — données exclues,
                                            # structure toujours copiée
          post_sql:                         # fixups exécutés SUR LE CLONE, confinés
            - "UPDATE config SET value = 'http://{host}/' WHERE name = 'site_url'"
        post_create:              # setup appli — shell, cwd = worktree (host)
          - "[ -d vendor ] || cp -r ../matnat_sf7-dev/vendor vendor"
        post_create_container:    # idem mais via ssh env_runtime.ssh_host,
          - "php bin/console cache:clear"   # cwd = worktree (chemin conteneur)

    Clone BDD = toujours OPTIONNEL. À la création : --db-clone / --no-db-clone
    tranchent sans question ; sinon la question est posée (TTY) avec le défaut
    projet `db_clone_default` ; hors TTY (hook, agent) le défaut s'applique.
    post_sql : placeholders {db} {clone} {rmid} {host} ; exécuté par le helper
    via un compte MySQL confiné au clone (jamais root — pas d'échappée possible).

Ops privilégiées (vhost/BDD/logs) déléguées à `pm-env-helper` sur la box de dev
via ssh+sudo — config `pm.config.yml :: env_runtime`. La config app (creds/base-URL,
brique C4/C5 RM1947) reste à la charge du provisionneur framework : ce script pose
le substrat générique et affiche quoi câbler.

Worktree/branche enregistrés dans le registre de session (pm_session, RM2034).
N'auto-committe rien : opère sur les repos du workspace, pas sur le repo PM.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pm-env-session: PyYAML requis")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_session
import pm_git
import redmine_utils

CORE = Path(__file__).resolve().parent.parent

USER_INI = """; Généré par pm-env-session (RM1834) — logs séparés par worktree de session.
; Le pool FPM reste PARTAGÉ au workspace ; error_log est surchargeable ici car
; posé en php_value[] dans common.conf.inc (RM2081).
error_log = {log}
log_errors = On
display_errors = Off
"""


def die(msg):
    sys.exit(f"pm-env-session: {msg}")


def run(cmd, cwd=None, check=True, capture=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        die(f"`{' '.join(map(str, cmd))}` a échoué (rc={r.returncode})"
            + (f" :\n{err}" if err else ""))
    return r


def git(args, cwd=None, check=True):
    return run(["git", *args], cwd=cwd, check=check)


# ------------------------------------------------------------- config/manifeste

def load_env_runtime_cfg() -> dict:
    """`pm.config.yml :: env_runtime` (+ override pm.config.local.yml)."""
    cfg = {}
    for name in ("pm.config.yml", "pm.config.local.yml"):
        p = CORE / name
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            cfg.update(data.get("env_runtime") or {})
    if not cfg.get("ssh_host") or not cfg.get("helper"):
        die("pm.config.yml :: env_runtime incomplet (ssh_host/helper requis)")
    return cfg


def find_workspace(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".mmi-pm").exists():
            return d
    die(f"aucun `.mmi-pm` en remontant depuis {start} (workspace PM-tracké ?)")


def load_repos(ws: Path) -> list[dict]:
    meta = ws / ".mmi-pm" / "meta.yml"
    if not meta.is_file():
        die(f"manifeste absent : {meta}")
    repos = (yaml.safe_load(meta.read_text(encoding="utf-8")) or {}).get("repos") or []
    if not repos:
        die("aucune clé `repos:` dans le manifeste (layout RM1993 requis — pm-env-init)")
    return repos


def pick_repo(repos: list[dict], name: str | None) -> dict:
    if name:
        for r in repos:
            if r.get("name") == name:
                return r
        die(f"repo `{name}` inconnu du manifeste")
    if len(repos) == 1:
        return repos[0]
    die("plusieurs repos dans le manifeste — précise --repo "
        f"({', '.join(r.get('name', '?') for r in repos)})")


def task_slug(ws: Path, rmid: int) -> str | None:
    """Slug depuis le fichier tâche co-localisé `.mmi-pm/tasks/RM<id>_<slug>.md`."""
    for f in (ws / ".mmi-pm" / "tasks").glob(f"RM{rmid}_*.md"):
        if not f.name.endswith(".log.md"):
            return f.stem[len(f"RM{rmid}_"):]
    return None


_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def set_test_url(ws: Path, rmid: int, url, dry: bool):
    """Écrit l'URL de test du ticket : frontmatter `test_url` + CF Redmine
    « Environnement de test » (RM2229). `url=None` = teardown → on VIDE les
    deux : une URL morte affichée est pire que rien (c'est le bug d'origine).
    Best-effort — l'env est monté/démonté même si le ticket est introuvable."""
    tf = next((f for f in (ws / ".mmi-pm" / "tasks").glob(f"RM{rmid}_*.md")
               if not f.name.endswith(".log.md")), None)
    if tf is None:
        print(f"  · test_url non écrit (pas de tâche co-localisée RM{rmid})")
        return
    if dry:
        print(f"  [dry] test_url ← {url!r} (frontmatter + CF Environnement de test)")
        return
    try:
        content = tf.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(content)
        fm = yaml.safe_load(m.group(2)) or {}
        fm["test_url"] = url
        new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                                default_flow_style=False)
        tf.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}",
                      encoding="utf-8")
        pm_git.autocommit([tf], f"pm(env): RM{rmid} test_url "
                                + ("renseigné" if url else "vidé (teardown)"))
        print(f"  ✓ test_url {'← ' + url if url else 'vidé'} (frontmatter)")
    except Exception as e:  # noqa: BLE001 — best-effort
        print(f"  ⚠ test_url frontmatter non écrit ({e})", file=sys.stderr)
    try:
        cid = redmine_utils.cf_id_by_name("Environnement de test")
        if cid:
            ok, err = redmine_utils.update_issue_fields(
                rmid, custom_fields=[{"id": cid, "value": url or ""}])
            print("  ✓ CF « Environnement de test » synchronisé" if ok
                  else f"  ⚠ CF non poussé ({err})")
    except Exception as e:  # noqa: BLE001 — hors-ligne etc.
        print(f"  ⚠ CF Environnement de test non poussé ({e})", file=sys.stderr)


def map_container_path(cfg: dict, host_path: Path) -> str:
    """Traduit un chemin host → chemin vu par la box de dev (bind-mounts)."""
    for h, c in (cfg.get("workspace_map") or {}).items():
        hp = str(host_path)
        if hp == h or hp.startswith(h.rstrip("/") + "/"):
            return c.rstrip("/") + hp[len(h.rstrip("/")):]
    die(f"{host_path} hors des workspace_map de env_runtime — chemin non traduisible")


def on_target_box(cfg: dict) -> bool:
    """Sommes-nous DÉJÀ sur la box qui porte le helper privilégié ? (RM2646)

    Depuis 2026-07-07 les sessions tournent dans le conteneur `dev` : y faire
    `ssh mathieu@dev.lxc` revient à se joindre soi-même — ça échoue, et comme l'échec
    est « non bloquant », le vhost n'est jamais posé sans que personne ne le voie.

    Le signal retenu est le **helper présent et exécutable en local** : il n'est
    déployé que sur la box de dev, et il est exactement ce que la commande veut
    joindre — pas de devinette sur le hostname (`dev.local` ≠ `dev.lxc`), pas de
    résolution DNS. `env_runtime.force_ssh: true` rétablit le saut ssh si un jour une
    machine porte le binaire sans être la cible.
    """
    if cfg.get("force_ssh"):
        return False
    h = Path(cfg["helper"])
    return h.is_file() and os.access(h, os.X_OK)


def helper(cfg: dict, args: list[str], dry: bool, check=True, stdin: str | None = None):
    """Invoque le helper privilégié : `sudo -n` en local si on est déjà sur la box
    (RM2646), sinon `ssh <ssh_host> sudo -n` comme avant."""
    # En local, subprocess passe argv tel quel : quoter injecterait des guillemets
    # littéraux. Via ssh, les arguments sont ré-interprétés par un shell distant :
    # le quoting est indispensable. D'où les deux formes.
    if on_target_box(cfg):
        cmd = ["sudo", "-n", cfg["helper"], *args]
    else:
        cmd = ["ssh", cfg["ssh_host"], "sudo", "-n", cfg["helper"],
               *(shlex.quote(a) for a in args)]
    if dry:
        print(f"  [dry] {' '.join(cmd)}" + (" << (sql)" if stdin else ""))
        return None
    r = subprocess.run(cmd, capture_output=True, text=True, input=stdin)
    if r.returncode != 0 and check:
        err = (r.stderr or r.stdout or "").strip()
        die(f"`{' '.join(cmd)}` a échoué (rc={r.returncode})"
            + (f" :\n{err}" if err else ""))
    out = (r.stdout or "").strip()
    if out:
        print("  " + out.replace("\n", "\n  "))
    return r


# ---------------------------------------------------------------------- create

def list_worktrees(bare: Path) -> list[tuple[Path, str | None]]:
    """(chemin, branche courte|None) de chaque worktree enregistré du bare —
    parse `git worktree list --porcelain`. Le bare lui-même et les worktrees
    détachés ressortent avec branche=None (pas de ligne `branch`)."""
    # check=False : un bare non initialisé (ou pas encore un repo git) => aucun
    # worktree, pas une erreur fatale — le résolveur retombe sur le chemin canonique.
    out = git(["-C", str(bare), "worktree", "list", "--porcelain"], check=False).stdout
    res: list[tuple[Path, str | None]] = []
    cur, br = None, None
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur is not None:
                res.append((Path(cur), br))
            cur, br = line[len("worktree "):], None
        elif line.startswith("branch "):
            ref = line[len("branch "):]
            br = ref.split("refs/heads/", 1)[-1] if "refs/heads/" in ref else ref
    if cur is not None:
        res.append((Path(cur), br))
    return res


def worktree_for_branch(bare: Path, name: str, rmid: int) -> tuple[Path, str] | None:
    """Worktree où la branche du ticket (`<rmid>-*`) est déjà checkoutée, quel
    que soit le NOM du worktree : canonique `<repo>-rm<id>` OU discriminé par
    session `<repo>-dev-<id>-s<seq>` (RM2034), OU créé/renommé à la main.

    Résolution par BRANCHE via `git worktree list` — jamais par chemin deviné
    (RM2394) : c'est la seule façon qui survive au nommage discriminé, aux
    renommages (`git worktree move`) et au multi-session. À égalité, le worktree
    au nom canonique l'emporte (chemin stable pour l'URL/vhost).
    Retourne (chemin, branche) ou None si le ticket n'a aucun worktree monté."""
    canonical = f"{name}-rm{rmid}"
    hits = [(p, b) for p, b in list_worktrees(bare)
            if b and b.startswith(f"{rmid}-")]
    if not hits:
        return None
    hits.sort(key=lambda pb: (pb[0].name != canonical, pb[0].name))
    return hits[0]


def resolve_base(bare: Path, integration_branch: str | None) -> str:
    """Point de départ de la branche ticket, résolu sur le REMOTE (RM2646).

    Retenir le ref LOCAL dès qu'il existe — ce que faisait cette fonction — crée des
    branches sur une base périmée sans le dire : constaté sur le bare pisceen, dont
    `refs/heads/dev` accusait ~200 commits de retard sur `origin/dev`. Le garde vit
    dans `pm_git.resolve_base_ref`, partagé avec `pm-branch-start` : il ne doit pas
    exister d'un seul côté (les deux outils créent des branches de ticket).
    """
    heads = git(["-C", str(bare), "for-each-ref", "--format=%(refname:short)",
                 "refs/heads"]).stdout.split()
    remotes = git(["-C", str(bare), "for-each-ref", "--format=%(refname)",
                   "refs/remotes"]).stdout.splitlines()
    cands = [integration_branch] if integration_branch else ["dev", "develop"]
    for c in [*cands, "main", "master"]:
        if c in heads or f"refs/remotes/origin/{c}" in remotes:
            return pm_git.resolve_base_ref(bare, c, warn=lambda m: print(f"  ⚠ {m}"))
    die(f"aucune branche d'intégration résoluble dans {bare.name}")


def cmd_create(args):
    if args.db_clone and args.no_db_clone:
        die("--db-clone et --no-db-clone sont mutuellement exclusifs")
    cfg = load_env_runtime_cfg()
    ws = find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    repo = pick_repo(load_repos(ws), args.repo)
    name, rmid = repo["name"], args.rmid
    bare = ws / "repos" / f"{name}.git"
    bare.is_dir() or die(f"bare absent : {bare} (lancer pm-env-init d'abord)")
    runtime = repo.get("runtime") or {}
    dry = args.dry_run

    # env_name = identité STABLE du ticket (vhost `<repo>-rm<id>.lxc`, canari,
    # nom des logs). Le worktree, lui, est résolu PAR BRANCHE (RM2394) : il peut
    # déjà être monté sous un nom discriminé par session (RM2034) ou canonique.
    env_name = f"{name}-rm{rmid}"
    canonical = ws / "envs" / env_name
    slug = args.slug or task_slug(ws, rmid) or "session"
    branch = f"{rmid}-{slug}"

    # Réutilise le worktree du ticket s'il existe déjà (quel que soit son nom),
    # sinon on le créera au chemin canonique. On pose alors le vhost/runtime
    # PAR-DESSUS l'existant (idempotent) au lieu d'échouer sur `worktree add`.
    reused = worktree_for_branch(bare, name, rmid)  # lecture seule (dry inclus)
    if reused is not None:
        wt, branch = reused
    else:
        wt = canonical
    print(f"workspace : {ws}\nenv       : envs/{wt.name}  (branche {branch})")

    # 1. worktree + branche ticket
    if wt.exists():
        if wt != canonical:
            print(f"  · worktree du ticket réutilisé : envs/{wt.name} "
                  f"(résolu par branche, RM2394)")
        else:
            print(f"  · worktree déjà monté")
    else:
        lheads = git(["-C", str(bare), "for-each-ref", "--format=%(refname:short)",
                      "refs/heads"]).stdout.split()
        # Branche exacte, sinon TOUTE branche du ticket (préfixe `<id>-`) :
        # pm-branch-start tronque le slug, pas nous (RM2229/RM2065 gap #1) —
        # sans ça on repartirait de main en croyant reprendre le ticket.
        if branch not in lheads:
            hits = sorted(h for h in lheads if h.startswith(f"{rmid}-"))
            if hits:
                branch = hits[0]
                print(f"  · branche du ticket trouvée par préfixe : {branch}")
        if branch in lheads:
            print(f"  git worktree add envs/{env_name} {branch}  (branche existante)")
            not dry and git(["-C", str(bare), "worktree", "add", str(wt), branch])
        else:
            rheads = [h.split("/", 3)[-1] for h in
                      git(["-C", str(bare), "for-each-ref",
                           "--format=%(refname)", "refs/remotes"]).stdout.split()]
            rhits = sorted(h for h in rheads if h.startswith(f"{rmid}-"))
            if rhits:
                branch = rhits[0]
                print(f"  git worktree add envs/{env_name} {branch}  (depuis origin/{branch})")
                not dry and git(["-C", str(bare), "worktree", "add", "-b", branch,
                                 str(wt), f"origin/{branch}"])
            else:
                base = resolve_base(bare, repo.get("integration_branch"))
                print(f"  git worktree add -b {branch} envs/{env_name}  (depuis {base})")
                not dry and git(["-C", str(bare), "worktree", "add", "-b", branch,
                                 str(wt), base])
    if not dry:
        pm_session.record_worktree(str(wt))
        pm_session.record_branch(branch)

    if not runtime:
        print("  · pas de bloc `runtime:` au manifeste → env code seul, terminé.")
        return

    pool, docroot = runtime.get("pool"), runtime.get("docroot", "public")
    pool or die("runtime.pool manquant au manifeste")

    # 2. .user.ini — logs séparés par worktree (pool partagé)
    log = f"{cfg.get('log_dir', '/var/log/php')}/{pool}-rm{rmid}.error.log"
    ini = wt / docroot / ".user.ini"
    if dry:
        print(f"  [dry] écrit {ini.relative_to(ws)} (error_log={log})")
    elif ini.is_file() and f"error_log = {log}" in ini.read_text(encoding="utf-8"):
        print("  · .user.ini déjà en place")
    else:
        ini.parent.is_dir() or die(f"docroot absent dans le worktree : {ini.parent}")
        ini.write_text(USER_INI.format(log=log), encoding="utf-8")
        print(f"  ✓ {ini.relative_to(ws)} (error_log par worktree)")

    # 2b. canari de vivacité (RM2229) : GET /pm-env.txt == env_name ⇔ ce vhost
    # sert bien CE worktree (un vhost absent retombe sur le site Apache par
    # défaut avec un 200 trompeur). Nom sans point initial : les dotfiles
    # sont bloqués par Apache (403).
    canary = wt / docroot / "pm-env.txt"
    if dry:
        print(f"  [dry] écrit {canary.relative_to(ws)} (canari de vivacité)")
    elif not canary.is_file() or canary.read_text(encoding="utf-8").strip() != env_name:
        canary.write_text(env_name + "\n", encoding="utf-8")
        print(f"  ✓ {canary.relative_to(ws)} (canari de vivacité)")

    # 3. vhost (privilégié)
    if args.no_vhost:
        print("  · vhost sauté (--no-vhost)")
    else:
        docroot_c = map_container_path(cfg, wt / docroot)
        helper(cfg, ["vhost-add", env_name, docroot_c, f"/run/php/{pool}.sock"], dry)

    # 4. BDD — TOUJOURS optionnel : flag explicite > question (TTY) > défaut projet
    db = runtime.get("db")
    if args.db_clone and not db:
        die("--db-clone demandé mais runtime.db absent du manifeste")
    if db:
        if args.db_clone:
            want_clone = True
        elif args.no_db_clone:
            want_clone = False
        else:
            default = bool(runtime.get("db_clone_default"))
            if sys.stdin.isatty() and sys.stderr.isatty():
                hint = "O/n" if default else "o/N"
                ans = input(f"  ? Cloner la BDD partagée `{db}` en `{db}_rm{rmid}` "
                            f"pour ce ticket ? [{hint}] ").strip().lower()
                want_clone = default if not ans else ans in ("o", "y", "oui", "yes")
            else:
                want_clone = default
                print(f"  · BDD : défaut projet appliqué (db_clone_default="
                      f"{'true' if default else 'false'} ; forcer : --db-clone/--no-db-clone)")
        if want_clone:
            clone = f"{db}_rm{rmid}"
            spec = runtime.get("db_clone") or {}
            excludes = [str(p) for p in (spec.get("exclude_tables") or [])]
            helper(cfg, ["db-clone", db, clone, *excludes], dry)
            # post-SQL du manifeste (config domaine/email/modules…) — exécuté
            # CONFINÉ au clone par le helper. Placeholders : {db} {clone} {rmid} {host}
            post = spec.get("post_sql") or []
            if post:
                subst = {"db": db, "clone": clone, "rmid": str(rmid),
                         "host": f"{env_name}.lxc"}
                # substitution ciblée (pas str.format : le SQL peut contenir
                # des accolades littérales — JSON…) ; placeholders inconnus laissés tels quels
                rx = re.compile(r"\{(" + "|".join(subst) + r")\}")
                sql = ";\n".join(rx.sub(lambda m: subst[m.group(1)], s).rstrip("; \t")
                                 for s in post) + ";"
                helper(cfg, ["db-post-sql", clone], dry, stdin=sql)
            print(f"  ⚠ config app à pointer sur `{clone}` dans le worktree "
                  f"(brique C4/provisionneur framework — manuel pour l'instant)")
        else:
            print(f"  · BDD partagée `{db}` (pas de clone pour ce ticket)")

    # 5. setup appli déclaratif (RM2229) : étapes du manifeste, exécutées à
    # CHAQUE create — y compris sur un env déjà monté (= action « réparer »).
    # L'idempotence des étapes est la responsabilité du manifeste (guards
    # `[ -d vendor ] ||`…). Tout doit être posé AVANT le premier hit HTTP,
    # sinon l'opcache/realpath du pool FPM partagé fige la résolution fautive.
    # Confiance : meta.yml est versionné et possédé par le workspace — même
    # niveau de confiance que le code du repo (jamais d'entrée client ici).
    subst = {"rmid": str(rmid), "env": env_name}
    rx = re.compile(r"\{(" + "|".join(subst) + r")\}")
    expand = lambda s: rx.sub(lambda m: subst[m.group(1)], s)  # noqa: E731
    for step in (runtime.get("post_create") or []):
        step = expand(str(step))
        print(f"  $ {step}")
        if not dry:
            r = subprocess.run(["bash", "-c", step], cwd=str(wt),
                               capture_output=True, text=True)
            r.returncode == 0 or die(f"post_create a échoué ({r.returncode}) : "
                                     f"{step}\n{(r.stderr or r.stdout).strip()}")
    csteps = runtime.get("post_create_container") or []
    if csteps:
        wt_c = map_container_path(cfg, wt)
        # RM2646 : même règle que `helper()` — déjà sur la box, on exécute sur place.
        local = on_target_box(cfg)
        where = "local" if local else cfg["ssh_host"]
        for step in csteps:
            step = expand(str(step))
            print(f"  $ [{where}] {step}")
            if not dry:
                argv = (["bash", "-c", f"cd {shlex.quote(wt_c)} && {step}"] if local
                        else ["ssh", cfg["ssh_host"],
                              f"cd {shlex.quote(wt_c)} && {step}"])
                r = subprocess.run(argv, capture_output=True, text=True)
                r.returncode == 0 or die(
                    f"post_create_container a échoué ({r.returncode}) : "
                    f"{step}\n{(r.stderr or r.stdout).strip()}")

    # 6. test_url du ticket (RM2229) : frontmatter + CF « Environnement de
    # test » — la file de recette (Redmine + cockpit) pointe l'env vivant.
    set_test_url(ws, rmid, f"http://{env_name}.lxc/", dry)

    print(f"\n{'[dry-run] ' if dry else ''}✓ env de session prêt : "
          f"http://{env_name}.lxc/  (Host: {env_name}.lxc)")


# -------------------------------------------------------------------- teardown

def cmd_teardown(args):
    cfg = load_env_runtime_cfg()
    ws = find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    repo = pick_repo(load_repos(ws), args.repo)
    name, rmid = repo["name"], args.rmid
    # `env_name` = identité STABLE du ticket (vhost, logs, clone BDD) — elle ne
    # dépend PAS du nom du worktree et reste canonique.
    env_name = f"{name}-rm{rmid}"
    bare = ws / "repos" / f"{name}.git"
    runtime = repo.get("runtime") or {}
    dry = args.dry_run

    # RM2523 — le worktree se résout PAR BRANCHE, comme dans `create` (RM2394).
    # Deviner `envs/<repo>-rm<id>` ratait tous ceux créés par
    # `pm-branch-start --worktree`, nommés `<repo>-dev-<id>-s<seq>` : teardown
    # annonçait « worktree déjà absent » et sortait en succès alors que le
    # worktree était bien monté. Repli sur le chemin canonique quand le ticket
    # n'a aucune branche checkoutée (worktree déjà démonté, ou jamais créé).
    found = worktree_for_branch(bare, name, rmid)
    wt = found[0] if found else ws / "envs" / env_name
    try:
        shown = wt.relative_to(ws)
    except ValueError:
        shown = wt
    print(f"workspace : {ws}\nteardown  : {shown}"
          + (f"  [branche {found[1]}]" if found else ""))

    # 1. refuse un worktree sale (sauf --force) — les commits restent sur la branche.
    # Les fichiers posés par create (.user.ini, canari pm-env.txt) ne comptent
    # pas comme dirt (artefacts de l'outil).
    docroot = runtime.get("docroot", "public") if runtime else None
    own = {f"?? {docroot}/.user.ini", f"?? {docroot}/pm-env.txt"} if docroot else set()
    if wt.is_dir():
        st = git(["-C", str(wt), "status", "--porcelain"], check=False).stdout
        dirt = [ln for ln in st.splitlines()
                if ln.strip() and ln.strip() not in own]
        if dirt and not args.force:
            die("worktree sale (modifs non commitées) — commit/stash d'abord, "
                "ou --force pour perdre :\n" + "\n".join(dirt))
        # 1bis. refuse une branche aux commits non poussés (sauf --force) — RM2319 :
        # le worktree démonté, la branche reste dans le bare mais devient invisible ;
        # des commits jamais poussés y seraient oubliés (variante de l'incident RM2302).
        br = git(["-C", str(wt), "branch", "--show-current"], check=False).stdout.strip()
        if br and not args.force:
            git(["-C", str(wt), "fetch", "origin", br], check=False)
            upstream = git(["-C", str(wt), "rev-parse", "--verify", "--quiet",
                            f"refs/remotes/origin/{br}"], check=False).stdout.strip()
            # poussé = derrière origin/<br> si elle existe, sinon derrière N'IMPORTE
            # quelle branche origin (branche jamais poussée mais contenu déjà livré)
            scope = [f"origin/{br}..HEAD"] if upstream else ["HEAD", "--not", "--remotes=origin"]
            ahead = git(["-C", str(wt), "rev-list", "--count", *scope],
                        check=False).stdout.strip()
            if ahead and ahead != "0":
                die(f"branche '{br}' : {ahead} commit(s) non poussé(s) sur origin — "
                    f"pousse d'abord (git push -u origin {br}), ou --force pour "
                    f"démonter quand même (les commits restent dans le bare, mais hors de vue).")

    # 2. runtime (privilégié) : vhost + logs php + clone BDD
    if runtime:
        pool = runtime.get("pool", "")
        helper(cfg, ["vhost-remove", env_name], dry)
        pool and helper(cfg, ["phplog-purge", f"{pool}-rm{rmid}"], dry)
        db = runtime.get("db")
        if db and not args.keep_db:
            helper(cfg, ["db-drop", f"{db}_rm{rmid}"], dry)
        elif db:
            print(f"  · clone BDD conservé ({db}_rm{rmid}) — --keep-db")

    # 3. worktree (la branche <id>-<slug> N'EST JAMAIS supprimée — NORMS)
    if wt.is_dir():
        if docroot and not dry:
            # artefacts posés par create (.user.ini, canari pm-env.txt) : à
            # retirer, sinon git worktree remove refuse (untracked)
            for rel in (f"{docroot}/.user.ini", f"{docroot}/pm-env.txt"):
                f = wt / rel
                f.is_file() and f.unlink()
        cmd = ["-C", str(bare), "worktree", "remove"]
        args.force and cmd.append("--force")
        print(f"  git worktree remove {shown}")
        if not dry:
            r = git([*cmd, str(wt)], check=False)
            # RM2572 — git refuse CATÉGORIQUEMENT de retirer un worktree contenant
            # des submodules, même parfaitement propre. Les projets dont les modules
            # sont en submodules (convention RM2110) tombent tous dans ce cas : sans
            # ce repli, aucun de leurs envs de session n'est démontable.
            # Forcer est sûr ICI, et seulement ici : les deux garde-fous qui
            # protègent quelque chose ont déjà été franchis plus haut — worktree
            # propre (étape 1) et branche sans commit non poussé (étape 1bis).
            # Le repli reste ciblé sur ce refus : tout autre échec de git (worktree
            # verrouillé, chemin introuvable) doit continuer de remonter.
            if r.returncode != 0 and "submodules" in (r.stderr or ""):
                print("  · worktree à submodules : git refuse le retrait simple, "
                      "on force (worktree propre et branche poussée déjà vérifiés)")
                r = git([*cmd, "--force", str(wt)], check=False)
            if r.returncode != 0:
                die("git worktree remove a échoué :\n" + (r.stderr or "").strip())
            pm_session.forget_worktree(str(wt))
    else:
        # RM2523 — distinguer « rien à démonter » (cas normal) de « un worktree
        # existe mais n'a pas été reconnu » (anomalie). L'ancien message unique
        # « worktree déjà absent » décrivait un succès dans les deux cas.
        orphans = [p for p, b in list_worktrees(bare)
                   if b and b.startswith(f"{rmid}-") and Path(p).is_dir()]
        if orphans:
            die("un worktree du ticket est monté mais n'a pas pu être résolu :\n  "
                + "\n  ".join(str(p) for p in orphans)
                + f"\n(bare : {bare}) — signaler, ne pas démonter à la main.")
        print(f"  · aucun worktree monté pour RM{rmid} — rien à démonter")

    # 4. test_url du ticket (RM2229) : on VIDE frontmatter + CF — une URL
    # morte affichée est exactement le bug d'origine.
    set_test_url(ws, rmid, None, dry)

    print(f"\n{'[dry-run] ' if dry else ''}✓ teardown terminé "
          f"(branche {rmid}-* conservée)")


# ------------------------------------------------------------------------ list

def cmd_list(args):
    """Envs de session du workspace.

    RM2523 — la liste part des worktrees RÉELLEMENT enregistrés dans les bares,
    pas d'un glob `*-rm<id>` sur les noms de dossier : ce glob ne voyait pas les
    worktrees créés par `pm-branch-start --worktree` (`<repo>-dev-<id>-s<seq>`),
    qui sont pourtant la majorité en pratique. Le RM-id vient de la BRANCHE
    (`<id>-<slug>`), seule source fiable quel que soit le nom du dossier.
    """
    ws = find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    envs = ws / "envs"
    rows: dict[str, tuple[str, str]] = {}   # chemin → (rm, branche)

    for repo in load_repos(ws):
        bare = ws / "repos" / f"{repo['name']}.git"
        for p, br in list_worktrees(bare):
            if not Path(p).is_dir() or Path(p).resolve() == bare.resolve():
                continue
            m = re.match(r"(\d+)-", br or "")
            rows[str(p)] = (m.group(1) if m else "?", br or "?")

    # Filet : un dossier `envs/*-rm<id>` dont le worktree n'est plus enregistré
    # (bare recréé, .git cassé) reste signalé — sinon il disparaîtrait du radar.
    if envs.is_dir():
        for p in sorted(envs.glob("*-rm[0-9]*")):
            if p.is_dir() and str(p) not in rows:
                m = re.search(r"-rm(\d+)$", p.name)
                rows[str(p)] = (m.group(1) if m else "?", "non enregistré")

    if not rows:
        print(f"(aucun env de session dans {ws}/envs/)")
        return
    for path in sorted(rows):
        rm, br = rows[path]
        try:
            shown = Path(path).relative_to(ws)
        except ValueError:
            shown = Path(path)
        print(f"  {shown}  RM{rm}  branche={br}")


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(
        prog="pm-env-session",
        description="Env de session par ticket : worktree + runtime (RM1834).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("rmid", type=int, help="id Redmine du ticket")
        p.add_argument("workspace", nargs="?", default=None,
                       help="workspace (défaut : découverte via .mmi-pm depuis cwd)")
        p.add_argument("--repo", default=None, help="repo du manifeste (si plusieurs)")
        p.add_argument("--dry-run", action="store_true")

    pc = sub.add_parser("create", help="crée l'env de session (worktree + runtime)")
    common(pc)
    pc.add_argument("--slug", default=None,
                    help="slug de branche (défaut : slug du fichier tâche, sinon `session`)")
    pc.add_argument("--db-clone", action="store_true",
                    help="clone la BDD partagée en <db>_rm<id> sans poser la question")
    pc.add_argument("--no-db-clone", action="store_true",
                    help="BDD partagée, sans poser la question")
    pc.add_argument("--no-vhost", action="store_true", help="pas de vhost (code seul)")
    pc.set_defaults(fn=cmd_create)

    pt = sub.add_parser("teardown", help="démonte l'env (branche + BDD partagée conservées)")
    common(pt)
    pt.add_argument("--keep-db", action="store_true", help="conserve le clone BDD éventuel")
    pt.add_argument("--force", action="store_true",
                    help="démonte même si le worktree a des modifs non commitées")
    pt.set_defaults(fn=cmd_teardown)

    pl = sub.add_parser("list", help="liste les envs de session du workspace")
    pl.add_argument("workspace", nargs="?", default=None)
    pl.set_defaults(fn=cmd_list)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
