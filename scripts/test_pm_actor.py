#!/usr/bin/env python3
"""Tests RM3070 L3 — qui agit, et ce que le commit en dit.

Le démon agissait toujours sous son propre compte : tous les commits PM portaient le même auteur,
et les journaux disaient « le service ». Ici : l'acteur est résolu (conf, puis son ~/.gitconfig,
puis son nom système), transporté par l'environnement, et devient l'AUTEUR du commit — jamais avec
une adresse inventée.

Lancer : python3 scripts/test_pm_actor.py
"""
import os
import pathlib
import pwd
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_actor as A  # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


moi = pwd.getpwuid(os.getuid()).pw_name

print("[L3] résolution : la conf d'abord, puis son git, puis son compte")
conf = {"identities": {"alice": {"name": "Alice Martin", "email": "alice@exemple.fr"}}}
a = A.resolve("alice", conf)
check("la conf fait foi quand elle est complète",
      (a["name"], a["email"], a["source"]) == ("Alice Martin", "alice@exemple.fr", "conf identities"), str(a))
a = A.resolve(moi, {})
check("sans conf : mon identité git ou mon nom système", a["user"] == moi and a["name"], str(a))
check("personne : rien, et c'est dit", A.resolve("", {})["source"] == "inconnu")
a = A.resolve("compte-qui-nexiste-pas-xyz", {})
check("un compte inconnu ne fait pas tomber la résolution", a["user"] == "compte-qui-nexiste-pas-xyz", str(a))

print("\n[L3] l'environnement transporte l'acteur")
env = A.env_for({"user": "alice", "name": "Alice Martin", "email": "alice@exemple.fr"}, base={"PATH": "/bin"})
check("PM_ACTOR_* posés", env["PM_ACTOR_USER"] == "alice" and env["PM_ACTOR_NAME"] == "Alice Martin")
check("…et l'auteur git avec, puisque l'adresse est connue",
      env["GIT_AUTHOR_NAME"] == "Alice Martin" and env["GIT_AUTHOR_EMAIL"] == "alice@exemple.fr")
env = A.env_for({"user": "bob", "name": "Bob", "email": ""}, base={"PATH": "/bin"})
check("sans adresse : le nom voyage pour les journaux…", env["PM_ACTOR_NAME"] == "Bob")
check("…mais AUCUN auteur git n'est posé (pas d'adresse inventée)",
      "GIT_AUTHOR_EMAIL" not in env and "GIT_AUTHOR_NAME" not in env, str(env))
sale = {"PM_ACTOR_USER": "alice", "GIT_AUTHOR_EMAIL": "alice@exemple.fr", "PATH": "/bin"}
env = A.env_for({}, base=sale)
check("un acteur vide EFFACE le précédent — sinon bob committerait au nom d'alice",
      "PM_ACTOR_USER" not in env and "GIT_AUTHOR_EMAIL" not in env, str(env))

print("\n[L3] le commit porte l'humain, la machine reste le committer")
with tempfile.TemporaryDirectory() as d:
    g = lambda *a, **k: subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, check=True, **k)
    g("init", "-q", "-b", "main")
    g("config", "user.name", "Service Karl"); g("config", "user.email", "karl@machine")
    pathlib.Path(d, "f.txt").write_text("x")
    g("add", "f.txt")
    env = A.git_author_env({"PM_ACTOR_USER": "alice", "PM_ACTOR_NAME": "Alice Martin",
                            "PM_ACTOR_EMAIL": "alice@exemple.fr"}, base=dict(os.environ))
    subprocess.run(["git", "-C", d, "commit", "-qm", "essai"], env=env, check=True, capture_output=True)
    who = subprocess.run(["git", "-C", d, "log", "-1", "--format=%an|%ae|%cn|%ce"],
                         capture_output=True, text=True).stdout.strip()
    an, ae, cn, ce = who.split("|")
    check("auteur = l'humain", (an, ae) == ("Alice Martin", "alice@exemple.fr"), who)
    check("committer = le compte de service — « écrit par Alice, enregistré par karl »",
          (cn, ce) == ("Service Karl", "karl@machine"), who)
    # sans acteur : rien ne change (cas mono, ou appel CLI direct)
    pathlib.Path(d, "g.txt").write_text("y"); g("add", "g.txt")
    subprocess.run(["git", "-C", d, "commit", "-qm", "essai 2"],
                   env=A.git_author_env({}, base=dict(os.environ)), check=True, capture_output=True)
    who2 = subprocess.run(["git", "-C", d, "log", "-1", "--format=%an|%ae"],
                          capture_output=True, text=True).stdout.strip()
    check("sans acteur : l'identité de la machine, comme avant", who2 == "Service Karl|karl@machine", who2)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — identité de l'acteur (RM3070 L3)"))
sys.exit(1 if FAIL else 0)
