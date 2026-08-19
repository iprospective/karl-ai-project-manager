#!/usr/bin/env python3
"""Tests RM2646 — deux régressions de `pm-env-session`.

1. **Le helper était toujours appelé par ssh.** Depuis que les sessions tournent DANS
   le conteneur `dev`, `ssh mathieu@dev.lxc` se joint lui-même et échoue ; l'échec
   étant « non bloquant », le vhost n'était jamais posé sans que rien ne le dise.
2. **La base de branche était le ref LOCAL**, même périmé (constaté : `refs/heads/dev`
   du bare pisceen à ~200 commits de retard). Le garde existait dans `pm-branch-start` ;
   il est désormais partagé (`pm_git.resolve_base_ref`).

Utilise un VRAI dépôt git temporaire pour le point 2.
Lancer : python3 scripts/test_pm_env_session_local_helper.py
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


pes = _load("pm_env_session", "pm-env-session.py")
import pm_git  # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


# ---------------------------------------------------------------- on_target_box

with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    fake = td / "pm-env-helper"
    fake.write_text("#!/bin/sh\nexit 0\n")

    cfg_absent = {"ssh_host": "mathieu@dev.lxc", "helper": str(td / "nexistepas")}
    check("helper absent en local → on passe par ssh", not pes.on_target_box(cfg_absent))

    cfg_noexec = {"ssh_host": "mathieu@dev.lxc", "helper": str(fake)}
    os.chmod(fake, 0o644)
    check("helper présent mais non exécutable → ssh (on ne pourrait rien lancer)",
          not pes.on_target_box(cfg_noexec))

    os.chmod(fake, 0o755)
    check("helper présent et exécutable → exécution locale", pes.on_target_box(cfg_noexec))

    check("force_ssh rétablit le saut ssh même avec le helper local",
          not pes.on_target_box({**cfg_noexec, "force_ssh": True}))

    # ---- argv construit par helper() : ssh vs local, et quoting
    captured = {}

    class _R:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _R()

    real_run, pes.subprocess.run = pes.subprocess.run, fake_run
    try:
        pes.helper(cfg_noexec, ["vhost-add", "env avec espace"], dry=False)
        local_cmd = captured["cmd"]
        pes.helper(cfg_absent, ["vhost-add", "env avec espace"], dry=False)
        ssh_cmd = captured["cmd"]
    finally:
        pes.subprocess.run = real_run

    check("sur la box : argv local, aucun ssh", local_cmd[:2] == ["sudo", "-n"]
          and "ssh" not in local_cmd)
    check("sur la box : arguments passés bruts (pas de quoting littéral)",
          "env avec espace" in local_cmd)
    check("hors de la box : argv ssh conservé",
          ssh_cmd[0] == "ssh" and ssh_cmd[1] == "mathieu@dev.lxc")
    check("hors de la box : arguments quotés pour le shell distant",
          "'env avec espace'" in ssh_cmd)


# ------------------------------------------------------------ resolve_base_ref

with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    upstream, clone = td / "up.git", td / "clone"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "dev", str(upstream)], check=True)
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)], check=True)
    for k in ("user.email", "user.name"):
        git("config", k, "t@t" if "email" in k else "t", cwd=clone)
    (clone / "a.txt").write_text("1")
    git("add", "-A", cwd=clone)
    git("commit", "-qm", "c1", cwd=clone)
    git("push", "-q", "origin", "dev", cwd=clone)
    # le clone avance et pousse, mais on remet SA branche locale en arrière :
    # c'est exactement l'état « ref local périmé » du bare pisceen.
    (clone / "a.txt").write_text("2")
    git("commit", "-qam", "c2", cwd=clone)
    git("push", "-q", "origin", "dev", cwd=clone)
    git("reset", "-q", "--hard", "HEAD~1", cwd=clone)
    git("fetch", "-q", "origin", cwd=clone)

    behind = git("rev-list", "--count", "refs/heads/dev..origin/dev", cwd=clone).stdout.strip()
    check("prérequis du test : la branche locale est bien en retard", behind == "1")

    said = []
    base = pm_git.resolve_base_ref(clone, "dev", fetch=False, warn=said.append)
    check("base locale périmée → on branche depuis origin/dev", base == "origin/dev")
    check("le retard est signalé, pas avalé",
          any("en retard" in m for m in said))

    check("ref déjà distant → renvoyé tel quel",
          pm_git.resolve_base_ref(clone, "origin/dev", fetch=False) == "origin/dev")

    said2 = []
    check("branche purement locale (pas de tracking) → repli sur le ref local",
          pm_git.resolve_base_ref(clone, "wip-sans-remote", fetch=False,
                                  warn=said2.append) == "wip-sans-remote")

    # resolve_base() de pm-env-session doit passer par le garde partagé
    check("pm-env-session.resolve_base délègue et renvoie la ref distante",
          pes.resolve_base(clone, "dev") == "origin/dev")


print()
if fails:
    print(f"ÉCHEC — {len(fails)} test(s) : " + ", ".join(fails))
    sys.exit(1)
print("OK — tous les tests passent")
