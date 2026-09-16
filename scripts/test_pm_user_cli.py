#!/usr/bin/env python3
"""Tests RM3208 (U1) — `mmi-pm user` : le compte PM unique d'un utilisateur (OS + cockpit + profil).

Ce qui doit tenir :
- les plans sont IDEMPOTENTS : ce qui existe déjà ne se refait pas ;
- rien ne se passe sans compte humain préexistant (le PM ne crée pas de personnes) ;
- le mot de passe n'est JAMAIS un argument de ligne de commande (visible dans `ps`) ;
- `--dry-run` n'écrit rien ;
- désactiver est réversible : ce qui est retiré est mémorisé et rendu par `enable` ;
- supprimer ne touche jamais au compte humain, et ne supprime le rôle OS qu'avec `--purge-os` ;
- le gabarit `~/.config/mmi-pm/.env` est créé en 600 (dossier 700) et jamais écrasé ;
- le parcours cockpit seul (`--no-os --no-profile`) fonctionne sans root, pour de vrai.
"""
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("pm_user", HERE / "pm-user.py")
pu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pu)

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def kinds(steps):
    return [s.name for s in steps]


FRESH = dict(group_pm=False, human=True, role=False, role_in_pm=False, human_in_pm=False,
             account=None, env_file=False)
DONE = dict(group_pm=True, human=True, role=True, role_in_pm=True, human_in_pm=True,
            account={"os_role": "alex-pm", "hash": "x"}, env_file=True)
OPTS = dict(no_os=False, no_cockpit=False, no_profile=False, pm_gid=None, role_home="/zfs/workspaces",
            has_password=False)


def main():
    print("plan d'ajout")
    p = pu.plan_add("alex", FRESH, OPTS)
    check("installation neuve : tout", kinds(p) == ["groupadd", "useradd-role", "role-in-pm", "human-in-pm",
                                                   "account-create", "env-template", "skills", "hooks"], kinds(p))
    ua = next(s for s in p if s.name == "useradd-role")
    check("rôle = <login>-pm, home partagé, sans home créé",
          ua.argv == ["useradd", "-M", "-d", "/zfs/workspaces", "-s", "/bin/bash", "alex-pm"], ua.argv)
    p = pu.plan_add("alex", FRESH, {**OPTS, "pm_gid": 1008})
    check("gid fixe transmis", p[0].argv == ["groupadd", "--gid", "1008", "pm"], p[0].argv)
    p = pu.plan_add("alex", DONE, OPTS)
    check("idempotent : ne restent que les resynchronisations", kinds(p) == ["skills", "hooks"], kinds(p))
    p = pu.plan_add("alex", DONE, {**OPTS, "has_password": True})
    check("mot de passe fourni sur compte existant → changement", "account-passwd" in kinds(p), kinds(p))
    p = pu.plan_add("alex", FRESH, {**OPTS, "no_os": True, "no_profile": True})
    check("--no-os --no-profile → compte cockpit seul", kinds(p) == ["account-create"], kinds(p))
    check("OS/profil exigent root", all(s.root for s in pu.plan_add("alex", FRESH, OPTS) if s.name != "account-create"))
    try:
        pu.plan_add("alex", {**FRESH, "human": False}, OPTS)
        check("humain absent → refus", False)
    except pu.PlanError as e:
        check("humain absent → refus explicite", "alex" in str(e), str(e))
    try:
        pu.plan_add("Alex!", FRESH, OPTS)
        check("login invalide → refus", False)
    except pu.PlanError:
        check("login invalide → refus", True)

    print("désactiver / réactiver / supprimer")
    p = pu.plan_disable("alex", DONE)
    check("désactiver : compte + sortie du groupe pm (rôle et humain)",
          kinds(p) == ["account-disable", "role-out-pm", "human-out-pm"], kinds(p))
    gone = {**DONE, "role_in_pm": False, "human_in_pm": False,
            "account": {**DONE["account"], "disabled": True, "os_groups_removed": ["alex-pm", "alex"]}}
    check("désactiver deux fois : rien", pu.plan_disable("alex", gone) == [], kinds(pu.plan_disable("alex", gone)))
    p = pu.plan_enable("alex", gone)
    check("réactiver rend exactement ce qui a été retiré",
          kinds(p) == ["account-enable", "role-in-pm", "human-in-pm"], kinds(p))
    p = pu.plan_remove("alex", DONE, purge_os=False)
    check("supprimer : compte + groupe, rôle OS conservé", kinds(p) == ["account-delete", "role-out-pm", "human-out-pm"], kinds(p))
    p = pu.plan_remove("alex", DONE, purge_os=True)
    check("--purge-os supprime le rôle OS", "userdel-role" in kinds(p), kinds(p))
    check("jamais de suppression du compte humain", all("alex" not in (s.argv or [])[-1:] or s.name != "userdel-role" or
                                                         s.argv[-1] == "alex-pm" for s in p))

    print("mot de passe jamais en argument")
    r = subprocess.run([sys.executable, str(HERE / "pm-user.py"), "add", "alex", "--password", "secret123"],
                       capture_output=True, text=True)
    check("--password refusé", r.returncode != 0, r.stdout + r.stderr)

    print("gabarit .env personnel")
    with tempfile.TemporaryDirectory() as d:
        env = Path(d) / ".config" / "mmi-pm" / ".env"
        check("créé", pu.write_env_template(env) is True)
        check("fichier 600", stat.S_IMODE(env.stat().st_mode) == 0o600, oct(env.stat().st_mode))
        check("dossier 700", stat.S_IMODE(env.parent.stat().st_mode) == 0o700, oct(env.parent.stat().st_mode))
        check("clé Redmine proposée, non renseignée", "# REDMINE_API_KEY=" in env.read_text())
        env.write_text("REDMINE_API_KEY=perso\n")
        check("jamais écrasé", pu.write_env_template(env) is False and "perso" in env.read_text())

    print("liste fusionnée")
    reg = {"users": [{"user": "alex", "disabled": False, "devices": 2, "password_set": True, "os_role": "alex-pm"}],
           "superadmin": "admin"}
    osv = {"members": {"alex", "alex-pm", "bea-pm"}, "roles": {"alex-pm", "bea-pm"}}
    rows = {r["user"]: r for r in pu.merge_list(reg, osv)}
    check("compte du registre avec son état OS", rows["alex"]["pm_group"] == "rôle+humain", rows.get("alex"))
    check("rôle OS sans compte registre visible", rows.get("bea", {}).get("cockpit") == "—", rows.get("bea"))

    print("parcours réel, cockpit seul, sans root")
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "KARL_AGENT_AUTH_DIR": d}
        run = lambda *a, inp=None: subprocess.run([sys.executable, str(HERE / "pm-user.py"), *a],
                                                  capture_output=True, text=True, env=env, input=inp)
        r = run("add", "zoe", "--no-os", "--no-profile", "--dry-run")
        check("dry-run n'écrit rien", r.returncode == 0 and not (Path(d) / "karl-users.json").exists(), r.stdout + r.stderr)
        r = run("add", "zoe", "--no-os", "--no-profile")
        users = json.loads((Path(d) / "karl-users.json").read_text())
        check("compte créé sans mot de passe", r.returncode == 0 and "zoe" in users and "hash" not in users["zoe"],
              r.stdout + r.stderr)
        r = run("add", "zoe", "--no-os", "--no-profile", "--password-stdin", inp="motdepasse-zoe\n")
        users = json.loads((Path(d) / "karl-users.json").read_text())
        check("mot de passe posé par stdin", r.returncode == 0 and "hash" in users["zoe"], r.stdout + r.stderr)
        check("mot de passe absent des sorties", "motdepasse-zoe" not in r.stdout + r.stderr)
        r = run("disable", "zoe", "--no-os")
        check("désactivé", json.loads((Path(d) / "karl-users.json").read_text())["zoe"].get("disabled") is True,
              r.stdout + r.stderr)
        r = run("list", "--json", "--no-os")
        check("liste JSON", r.returncode == 0 and any(x["user"] == "zoe" for x in json.loads(r.stdout)), r.stdout + r.stderr)
        r = run("remove", "zoe", "--no-os", "-y")
        check("supprimé", "zoe" not in json.loads((Path(d) / "karl-users.json").read_text()), r.stdout + r.stderr)
        r = run("add", "zoe")
        check("étapes OS sans root → refus lisible", (os.geteuid() == 0) or (r.returncode != 0 and "sudo" in r.stdout + r.stderr),
              r.stdout + r.stderr)

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
