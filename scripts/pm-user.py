#!/usr/bin/env python3
"""pm-user — le compte PM UNIQUE d'un utilisateur : système, cockpit, profil (RM3208, U1).

Les comptes du cockpit sont ceux des utilisateurs du CLI (décision du 2026-09-16). Avant cet outil, créer un
utilisateur, c'était un runbook de gestes système d'un côté (`docs/guides/runbook-provisioning-dev-pm.md`) et
un formulaire du cockpit de l'autre — impossible sans cockpit.

    sudo mmi-pm user add <login> [--password-stdin|--password-prompt] [--pm-gid 1008] [--dry-run]
    sudo mmi-pm user disable <login>        retire l'accès (compte + groupe pm), réversible
    sudo mmi-pm user enable <login>         rend exactement ce que disable a retiré
    sudo mmi-pm user remove <login> [-y] [--purge-os]
         mmi-pm user passwd <login> --password-stdin
         mmi-pm user list [--json]

Ce que « un compte PM » recouvre :
- système : le compte de rôle `<login>-pm` (données partagées, sans home propre) et l'appartenance du rôle
  ET de l'humain au groupe `pm` ;
- cockpit : l'entrée du registre `var/karl-users.json` (module `pm_accounts`, partagé avec le cockpit) ;
  sans mot de passe, le compte existe mais n'ouvre aucune session ;
- profil : le gabarit `~/.config/mmi-pm/.env` (600, jamais écrasé), les skills et les hooks Claude Code.

Garde-fous : le compte humain doit exister (le PM ne crée pas de personnes) ; le mot de passe n'est jamais un
argument (visible dans `ps`) ; tout est idempotent ; `remove` ne touche jamais au compte humain et ne supprime
le rôle système qu'avec `--purge-os`. `--no-os` / `--no-cockpit` / `--no-profile` limitent le périmètre ;
`--no-os --no-profile` ne demande pas root.
"""
import argparse
import getpass
import grp
import json
import os
import pwd
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import pm_accounts as acc  # noqa: E402

CORE = SCRIPTS.parent
PM_GROUP = "pm"
ENV_TEMPLATE = """# ~/.config/mmi-pm/.env — secrets PERSONNELS du PM (RM2497). 600, jamais commité, jamais partagé.
# Tes actions Redmine et forge partent sous TON identité : renseigne tes propres clés.
# REDMINE_API_KEY=
# GITLAB_WORKER_TOKEN=
# GOGS_TOKEN=
"""


class PlanError(Exception):
    """Plan impossible (compte humain absent, login invalide…) : rien n'a été fait."""


@dataclass
class Step:
    name: str
    desc: str
    argv: list = None
    root: bool = True


def role_of(login: str) -> str:
    return f"{login}-pm"


def _check_login(login: str) -> None:
    if not acc.USERNAME_RE.match(login or ""):
        raise PlanError(f"login invalide « {login} » : 2-32 car., [a-z0-9._-], commence par [a-z0-9]")


# ── Plans (purs : ils ne lisent que l'état qu'on leur passe) ─────────────────────────────────────────────
def plan_add(login: str, st: dict, opts: dict) -> list:
    _check_login(login)
    if not (opts["no_os"] and opts["no_profile"]) and not st["human"]:
        raise PlanError(f"compte humain « {login} » inexistant : le créer d'abord (adduser {login}) — "
                        "le PM ne crée pas de personnes")
    role, py = role_of(login), sys.executable
    steps = []
    if not opts["no_os"]:
        if not st["group_pm"]:
            gid = ["--gid", str(opts["pm_gid"])] if opts.get("pm_gid") else []
            steps.append(Step("groupadd", f"créer le groupe {PM_GROUP}", ["groupadd", *gid, PM_GROUP]))
        if not st["role"]:
            steps.append(Step("useradd-role", f"créer le compte de rôle {role}",
                              ["useradd", "-M", "-d", opts["role_home"], "-s", "/bin/bash", role]))
        if not st["role_in_pm"]:
            steps.append(Step("role-in-pm", f"{role} → groupe {PM_GROUP}", ["usermod", "-aG", PM_GROUP, role]))
        if not st["human_in_pm"]:
            steps.append(Step("human-in-pm", f"{login} → groupe {PM_GROUP}", ["usermod", "-aG", PM_GROUP, login]))
    if not opts["no_cockpit"]:
        if st["account"] is None:
            what = "avec mot de passe" if opts["has_password"] else "sans mot de passe (aucune session cockpit)"
            steps.append(Step("account-create", f"créer le compte PM {login} ({what})", root=False))
        elif opts["has_password"]:
            steps.append(Step("account-passwd", f"changer le mot de passe de {login} (appareils révoqués)", root=False))
    if not opts["no_profile"]:
        if not st["env_file"]:
            steps.append(Step("env-template", f"gabarit ~{login}/.config/mmi-pm/.env (600)"))
        steps.append(Step("skills", "resynchroniser les skills PM (idempotent)",
                          [py, str(SCRIPTS / "pm-skills-sync.py")]))
        steps.append(Step("hooks", "resynchroniser les hooks Claude Code (idempotent)",
                          [py, str(SCRIPTS / "pm-claude-hooks-sync.py")]))
    return steps


def plan_disable(login: str, st: dict) -> list:
    _check_login(login)
    role, steps = role_of(login), []
    if st["account"] is not None and not st["account"].get("disabled"):
        steps.append(Step("account-disable", f"désactiver le compte {login} (appareils révoqués)", root=False))
    if st["role_in_pm"]:
        steps.append(Step("role-out-pm", f"{role} ← hors du groupe {PM_GROUP}", ["gpasswd", "-d", role, PM_GROUP]))
    if st["human_in_pm"]:
        steps.append(Step("human-out-pm", f"{login} ← hors du groupe {PM_GROUP}", ["gpasswd", "-d", login, PM_GROUP]))
    return steps


def plan_enable(login: str, st: dict, no_os: bool = False) -> list:
    _check_login(login)
    role, steps = role_of(login), []
    account = st["account"] or {}
    if st["account"] is not None and account.get("disabled"):
        steps.append(Step("account-enable", f"réactiver le compte {login}", root=False))
    if not no_os:
        removed = account.get("os_groups_removed") or [role, login]
        if role in removed and st["role"] and not st["role_in_pm"]:
            steps.append(Step("role-in-pm", f"{role} → groupe {PM_GROUP}", ["usermod", "-aG", PM_GROUP, role]))
        if login in removed and st["human"] and not st["human_in_pm"]:
            steps.append(Step("human-in-pm", f"{login} → groupe {PM_GROUP}", ["usermod", "-aG", PM_GROUP, login]))
    return steps


def plan_remove(login: str, st: dict, purge_os: bool = False) -> list:
    _check_login(login)
    role, steps = role_of(login), []
    if st["account"] is not None:
        steps.append(Step("account-delete", f"supprimer le compte PM {login} (appareils révoqués)", root=False))
    if st["role_in_pm"]:
        steps.append(Step("role-out-pm", f"{role} ← hors du groupe {PM_GROUP}", ["gpasswd", "-d", role, PM_GROUP]))
    if st["human_in_pm"]:
        steps.append(Step("human-out-pm", f"{login} ← hors du groupe {PM_GROUP}", ["gpasswd", "-d", login, PM_GROUP]))
    if purge_os and st["role"]:
        steps.append(Step("userdel-role", f"supprimer le compte de rôle {role}", ["userdel", role]))
    return steps


def merge_list(reg: dict, osv: dict) -> list:
    """Vue unique : registre PM + état système. Un rôle `<x>-pm` sans compte au registre reste visible."""
    members, rows, seen = osv.get("members") or set(), [], set()
    for u in reg.get("users") or []:
        name, seen = u["user"], seen | {u["user"]}
        state = "désactivé" if u.get("disabled") else ("actif" if u.get("password_set") else "sans mot de passe")
        rows.append({"user": name, "cockpit": state, "devices": u.get("devices", 0),
                     "os_role": u.get("os_role") or "—", "pm_group": _group_label(name, members)})
    for role in sorted(osv.get("roles") or []):
        base = role[:-3]
        if base not in seen:
            rows.append({"user": base, "cockpit": "—", "devices": 0, "os_role": role,
                         "pm_group": _group_label(base, members)})
    return rows


def _group_label(login, members) -> str:
    r, h = role_of(login) in members, login in members
    return "rôle+humain" if r and h else "rôle" if r else "humain" if h else "—"


def write_env_template(path: Path, uid=None, gid=None) -> bool:
    """Gabarit des secrets personnels : dossier 700, fichier 600, JAMAIS écrasé. Rend True si créé."""
    p = Path(path)
    if p.exists():
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(p.parent, 0o700)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(ENV_TEMPLATE)
    os.chmod(p, 0o600)
    if uid is not None and os.geteuid() == 0:
        for q in (p.parent.parent, p.parent, p):
            if q.name in (".config", "mmi-pm", ".env"):
                os.chown(q, uid, gid)
    return True


# ── État réel (impur) ─────────────────────────────────────────────────────────────────────────────────
def _registry():
    d = acc.auth_dir(CORE)
    return d / acc.USERS_NAME, d / acc.DEVICES_NAME


def os_view() -> dict:
    try:
        g = grp.getgrnam(PM_GROUP)
    except KeyError:
        return {"members": set(), "roles": set(), "group": False}
    members = set(g.gr_mem) | {p.pw_name for p in pwd.getpwall() if p.pw_gid == g.gr_gid}
    roles = {p.pw_name for p in pwd.getpwall() if p.pw_name.endswith("-pm")}
    return {"members": members, "roles": roles, "group": True}


def probe(login: str, no_os: bool) -> dict:
    users_path, _ = _registry()
    account = acc.load(users_path).get(login)
    try:
        human = pwd.getpwnam(login)
    except KeyError:
        human = None
    env_file = False
    if human:
        try:
            env_file = (Path(human.pw_dir) / ".config" / "mmi-pm" / ".env").exists()
        except PermissionError:
            env_file = False
    if no_os:
        return dict(group_pm=True, human=bool(human), role=False, role_in_pm=False, human_in_pm=False,
                    account=account, env_file=env_file)
    v = os_view()
    try:
        pwd.getpwnam(role_of(login))
        role = True
    except KeyError:
        role = False
    return dict(group_pm=v["group"], human=bool(human), role=role, role_in_pm=role_of(login) in v["members"],
                human_in_pm=login in v["members"], account=account, env_file=env_file)


def _superadmin():
    """KARL_WEB_USER : environnement, sinon le .env de l'instance (nom réservé, jamais un compte du registre)."""
    if os.environ.get("KARL_WEB_USER"):
        return os.environ["KARL_WEB_USER"]
    try:
        for line in (CORE / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("KARL_WEB_USER="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    except OSError:
        pass
    return None


def _read_password(args):
    if getattr(args, "password_stdin", False):
        pw = sys.stdin.readline().rstrip("\n")
        return pw or None
    if getattr(args, "password_prompt", False):
        a, b = getpass.getpass("mot de passe : "), getpass.getpass("confirmation : ")
        if a != b:
            sys.exit("pm-user : les deux saisies diffèrent — rien n'a été fait")
        return a or None
    return None


def execute(login: str, steps: list, args, password=None) -> int:
    me = pwd.getpwuid(os.geteuid()).pw_name
    root = os.geteuid() == 0
    blocking = [s for s in steps if s.root and not root and not (s.name in ("env-template", "skills", "hooks")
                                                                  and login == me)]
    if blocking and not args.dry_run:
        sys.exit("pm-user : étapes système requises (" + ", ".join(s.name for s in blocking) + ") — "
                 "relance avec sudo, ou limite le périmètre (--no-os / --no-profile)")
    if not steps:
        print(f"pm-user : {login} — rien à faire (déjà en place)")
        return 0
    users_path, devices_path = _registry()
    removed = [s.argv[2] for s in steps if s.name in ("role-out-pm", "human-out-pm")]
    try:
        human = pwd.getpwnam(login)
    except KeyError:
        human = None
    for s in steps:
        print(("  [essai] " if args.dry_run else "  → ") + s.desc)
        if args.dry_run:
            continue
        try:
            if s.name == "account-create":
                extra = None if args.no_os else {"os_role": role_of(login)}
                acc.create_user(users_path, login, password, superadmin=_superadmin(), extra=extra)
            elif s.name == "account-passwd":
                acc.update_user(users_path, devices_path, login, password=password)
            elif s.name == "account-disable":
                acc.update_user(users_path, devices_path, login, disabled=True,
                                extra={"os_groups_removed": removed} if removed else None)
            elif s.name == "account-enable":
                acc.update_user(users_path, devices_path, login, disabled=False, extra={"os_groups_removed": []})
            elif s.name == "account-delete":
                acc.delete_user(users_path, devices_path, login)
            elif s.name == "env-template":
                write_env_template(Path(human.pw_dir) / ".config" / "mmi-pm" / ".env", human.pw_uid, human.pw_gid)
            elif s.name in ("skills", "hooks"):
                argv = s.argv if login == me else ["runuser", "-u", login, "--", *s.argv]
                subprocess.run(argv, check=True, env={**os.environ, "HOME": human.pw_dir} if human else None)
            else:
                subprocess.run(s.argv, check=True)
        except acc.AccountError as e:
            sys.exit(f"pm-user : {s.name} refusé — {e.message}")
        except subprocess.CalledProcessError as e:
            sys.exit(f"pm-user : {s.name} en échec (code {e.returncode}) — les étapes précédentes sont faites, "
                     "relancer la commande reprend là (idempotent)")
    print(f"pm-user : {login} — " + ("plan affiché, rien d'écrit" if args.dry_run else f"{len(steps)} étape(s) faite(s)"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mmi-pm user", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, os_flag=True):
        p.add_argument("login")
        p.add_argument("--dry-run", action="store_true", help="affiche le plan, n'écrit rien")
        if os_flag:
            p.add_argument("--no-os", action="store_true", help="ni compte de rôle ni groupe pm")
        return p

    def pw(p):
        g = p.add_mutually_exclusive_group()
        g.add_argument("--password-stdin", action="store_true", help="lit le mot de passe sur une ligne de stdin")
        g.add_argument("--password-prompt", action="store_true", help="saisie masquée, avec confirmation")

    a = common(sub.add_parser("add", help="créer / compléter le compte PM (idempotent)"))
    a.add_argument("--no-cockpit", action="store_true", help="pas d'entrée au registre du cockpit")
    a.add_argument("--no-profile", action="store_true", help="ni gabarit .env, ni skills, ni hooks")
    a.add_argument("--pm-gid", type=int, help="gid fixe du groupe pm s'il faut le créer (parité hôte/conteneur)")
    a.add_argument("--role-home", default=os.environ.get("WORKSPACES_ROOT") or "/zfs/workspaces",
                   help="home (partagé, non créé) du compte de rôle — défaut : $WORKSPACES_ROOT")
    pw(a)
    p = common(sub.add_parser("passwd", help="changer le mot de passe cockpit"), os_flag=False)
    pw(p)
    common(sub.add_parser("disable", help="retirer l'accès (réversible)"))
    common(sub.add_parser("enable", help="rendre l'accès retiré par disable"))
    r = common(sub.add_parser("remove", help="supprimer le compte PM (jamais le compte humain)"))
    r.add_argument("--purge-os", action="store_true", help="supprimer aussi le compte de rôle <login>-pm")
    r.add_argument("-y", "--yes", action="store_true", help="sans confirmation")
    ls = sub.add_parser("list", help="comptes PM : registre + état système")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--no-os", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        users_path, devices_path = _registry()
        rows = merge_list(acc.list_users(users_path, devices_path, superadmin=_superadmin()),
                          {} if args.no_os else os_view())
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        else:
            print(f"{'UTILISATEUR':<16} {'COCKPIT':<18} {'APPAREILS':>9}  {'RÔLE OS':<18} GROUPE pm")
            for x in rows:
                print(f"{x['user']:<16} {x['cockpit']:<18} {x['devices']:>9}  {x['os_role']:<18} {x['pm_group']}")
        return 0

    login = args.login.strip().lower()
    no_os = getattr(args, "no_os", True)
    if not no_os and os.geteuid() != 0 and not args.dry_run:
        sys.exit("pm-user : ce verbe touche aux comptes système — relance avec sudo (ou --no-os)")
    try:
        st = probe(login, no_os)
        if args.cmd == "add":
            password = _read_password(args)
            opts = dict(no_os=args.no_os, no_cockpit=args.no_cockpit, no_profile=args.no_profile,
                        pm_gid=args.pm_gid, role_home=args.role_home, has_password=password is not None)
            return execute(login, plan_add(login, st, opts), args, password)
        if args.cmd == "passwd":
            password = _read_password(args)
            if not password:
                sys.exit("pm-user : mot de passe attendu (--password-stdin ou --password-prompt)")
            args.no_os = True
            steps = [Step("account-passwd", f"changer le mot de passe de {login} (appareils révoqués)", root=False)]
            return execute(login, steps, args, password)
        if args.cmd == "disable":
            return execute(login, plan_disable(login, st), args)
        if args.cmd == "enable":
            return execute(login, plan_enable(login, st, no_os=no_os), args)
        if args.cmd == "remove":
            if not args.yes and not args.dry_run:
                if not sys.stdin.isatty():
                    sys.exit("pm-user : suppression — confirme avec -y (pas de terminal pour demander)")
                if input(f"Supprimer le compte PM « {login} » ? Retape le login : ").strip() != login:
                    sys.exit("pm-user : confirmation différente — rien n'a été fait")
            return execute(login, plan_remove(login, st, purge_os=args.purge_os), args)
    except PlanError as e:
        sys.exit(f"pm-user : {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
