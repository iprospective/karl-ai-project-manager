#!/usr/bin/env python3
"""Tests RM3033 — pm-core-update.py (port de `bin/mmi-pm core update`) : lecture du .env, détection du redémarrage karl-agent,
plans (hooks, co-déploiement, alias), dry-run sans privilège sur un dépôt temporaire, refus hors root sans dry-run (message sudo)."""
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_core_update", HERE / "pm-core-update.py"); C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# RM3178 : l'agent IMPORTE une douzaine de modules de scripts/ — karl_api_routes, pm_log, pm_notify,
# pm_bus, pm_modules… — dont plusieurs en import paresseux. Il garde en mémoire la version chargée au
# démarrage : ne redémarrer que sur `karl-agent.py` laissait un module livré invisible, et le symptôme
# (« route inconnue » sur une route déclarée partout) envoyait chercher n'importe où sauf là.
check("needs_agent_restart : le démon lui-même", bool(C.needs_agent_restart(["scripts/karl-agent.py", "x"])))
check("…et tout MODULE qu'il importe — c'est ce qui manquait (RM3178)",
      bool(C.needs_agent_restart(["scripts/karl_api_routes.py"]))
      and bool(C.needs_agent_restart(["scripts/pm_notify.py", "norms/NORMS.md"])))
check("…y compris un script pm-* (il coûte un redémarrage de trop, jamais un défaut invisible)",
      bool(C.needs_agent_restart(["scripts/pm-task-add.py"])))
check("mais pas ce qui ne peut rien changer dans le processus",
      not C.needs_agent_restart(["deploy/karl-agent/cockpit/index.html", "Changelog.md"])
      and not C.needs_agent_restart(["scripts/INDEX.md"]) and not C.needs_agent_restart([]))
check("les motifs sont RENDUS, pour dire pourquoi il a redémarré",
      C.needs_agent_restart(["scripts/pm_bus.py", "scripts/karl-agent.py", "x.md"])
      == ["scripts/karl-agent.py", "scripts/pm_bus.py"])
with tempfile.TemporaryDirectory() as td:
    core = pathlib.Path(td) / "core"; (core / "scripts").mkdir(parents=True)
    (core / ".env").write_text('KARL_USER="mathieu"\n# commentaire\nPROJECTS_PATH=/p\nVIDE\n')
    check("read_env : quotes dépouillées, commentaires et lignes sans = ignorés", C.read_env(core / ".env") == {"KARL_USER": "mathieu", "PROJECTS_PATH": "/p"} and C.read_env(core / "absent") == {})
    subprocess.run(["git", "init", "-q", str(core)], check=True); subprocess.run(["git", "-C", str(core), "config", "user.email", "t@t"], check=True); subprocess.run(["git", "-C", str(core), "config", "user.name", "t"], check=True)
    (core / "scripts" / "pm-post-commit.py").write_text("#"); (core / "scripts" / "pm-pre-push").write_text("#")
    (core / ".git" / "hooks").mkdir(exist_ok=True); (core / ".git" / "hooks" / "pre-push").write_text("vrai fichier")
    plan = {n: a for n, _, a in C.hooks_plan(core)}
    check("hooks_plan : link / manual (fichier non-symlink) / skip-missing", plan == {"post-commit": "link", "pre-push": "manual", "pre-commit": "skip-missing"}, str(plan))
    dp = C.deploy_plan(core); check("deploy_plan : sources absentes → rien", dp == [])
    (core / "tools" / "env-runtime").mkdir(parents=True); (core / "tools" / "env-runtime" / "pm-env-helper.sh").write_text("#!/bin/sh\n")
    dp = C.deploy_plan(core); check("deploy_plan : source présente, cible absente → à installer", len(dp) == 1 and dp[0][1] == pathlib.Path("/usr/local/sbin/pm-env-helper") and dp[0][3] is True)
    bindir = pathlib.Path(td) / "bin"; bindir.mkdir()
    check("alias_plan : sans mmi-pm installé → skip", all(a == "skip" for *_, a in C.alias_plan(core, bindir)))
    (bindir / "mmi-pm").symlink_to(HERE / "mmi-pm.py"); (bindir / "mmi-task").write_text("vrai fichier"); (bindir / "mmi-core").symlink_to(HERE / "mmi-pm.py")
    ap = {l.name: a for l, _, a in C.alias_plan(core, bindir)}
    check("alias_plan : ok / manual / link", ap["mmi-core"] == "ok" and ap["mmi-task"] == "manual" and ap["mmi-env"] == "link" and set(ap) == {f"mmi-{d}" for d in C.ALIAS_DOMAINS}, str(ap))
    (core / "README.md").write_text("x"); subprocess.run(["git", "-C", str(core), "add", "-A"], check=True); subprocess.run(["git", "-C", str(core), "commit", "-qm", "seed"], check=True)
    out = io.StringIO()
    with redirect_stdout(out):
        rc = C.update(core, dry=True)
    o = out.getvalue()
    check("dry-run : plan complet, rien écrit, code 0", rc == 0 and "[dry] git pull --ff-only origin" in o and "[dry] hook post-commit : link" in o and "[dry] hook pre-push : manual" in o and "/usr/local/sbin/pm-env-helper : à installer" in o and "[dry] alias mmi-core" in o and not (core / ".git" / "hooks" / "post-commit").exists(), o)
    if os.geteuid() != 0:
        out = io.StringIO()
        _vrai = C.code_a_moi
        C.code_a_moi = lambda *a, **k: False      # un code root-owned, vu d'un compte ordinaire
        try:
            with redirect_stdout(out):
                C.update(core, dry=False)
            check("hors root, code qui n'est pas à moi : refus explicite", False)
        except SystemExit as e:
            check("hors root, code qui n'est pas à moi : refus explicite (le re-exec sudo est dans main)", "doit tourner en root" in str(e))
        finally:
            C.code_a_moi = _vrai
    else:
        check("(root) garde sudo non testée", True)
    try:
        C.update(pathlib.Path(td) / "pasgit", dry=True); check("pas un dépôt git → erreur", False)
    except SystemExit as e:
        check("pas un dépôt git → erreur", "pas un dépôt git" in str(e))
    r = subprocess.run([sys.executable, str(HERE / "pm-core-update.py"), "--dry-run", "--core-dir", str(core)], capture_output=True, text=True)
    check("CLI --dry-run : sans sudo, code 0", r.returncode == 0 and "[dry]" in r.stdout and "re-exec sudo" not in r.stdout, r.stdout + r.stderr)

# ── RM3054 : provisioning utilisateur (hooks Claude, skills) — plans purs sur un faux core + faux home
with tempfile.TemporaryDirectory() as td:
    core = pathlib.Path(td) / "core"; home = pathlib.Path(td) / "home"
    (core / "scripts").mkdir(parents=True); (core / "skills" / "mmi-a").mkdir(parents=True); (core / "skills" / "mmi-b").mkdir()
    (core / "skills" / "mmi-a" / "SKILL.md").write_text("---\nname: mmi-a\n---\n"); (core / "skills" / "mmi-b" / "SKILL.md").write_text("x")
    (core / "skills" / "pas-un-skill").mkdir()
    (home / ".claude" / "skills").mkdir(parents=True)
    (home / ".claude" / "skills" / "mmi-a").symlink_to(core / "skills" / "mmi-a")          # déjà le bon lien
    (home / ".claude" / "skills" / "mmi-b").mkdir()                                          # occupé par un vrai dossier
    plan = {l.name: a for l, _, a in C.skills_plan(core, home)}
    check("skills_plan : ok / manual (dossier réel) / seuls les dossiers avec SKILL.md", plan == {"mmi-a": "ok", "mmi-b": "manual"}, str(plan))
    (core / "skills" / "mmi-c").mkdir(); (core / "skills" / "mmi-c" / "SKILL.md").write_text("x")
    plan = {l.name: a for l, _, a in C.skills_plan(core, home)}
    check("skills_plan : un skill nouveau → link", plan.get("mmi-c") == "link", str(plan))
    import shutil as _sh
    _sh.copy(HERE / "pm-claude-hooks-sync.py", core / "scripts" / "pm-claude-hooks-sync.py")
    for s in ("pm-turn-start.py", "pm-turn-wait.py", "pm-task-tick.py", "pm-task-report.py", "pm-session-status.py", "pm-think-harvest.py"):
        (core / "scripts" / s).write_text("#")
    (home / ".claude" / "settings.json").write_text("{}")
    check("claude_hooks_missing : settings vide → hooks manquants", C.claude_hooks_missing(core, home) is True)
    (core / ".env").write_text("KARL_USER=utilisateur-inexistant-xyz\n")
    check("instance_user : user inconnu → None (provisioning ignoré, jamais bloquant)", C.instance_user(core) is None)

# ── RM3070 L1 : installation mono — le code appartient à l'utilisateur, la mise à jour se passe de sudo
check("code_a_moi : root n'est jamais « à moi » (il garde le chemin complet)", C.code_a_moi(HERE, euid=0) is False)
check("code_a_moi : un code à un autre compte → non", C.code_a_moi(pathlib.Path("/"), euid=4242) is False)
check("as_user : un autre compte, sans root → None (signalé, pas tenté)",
      os.geteuid() == 0 or C.as_user("utilisateur-inexistant-xyz", ["true"], []) is None)
if os.geteuid() != 0:
    import pwd as _pwd
    moi = _pwd.getpwuid(os.geteuid()).pw_name
    check("as_user : moi-même, sans root → la commande directe, sans runuser",
          C.as_user(moi, ["true"], ["A=1"]) == ["env", "A=1", "true"])
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        g = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True, text=True)
        g("init", "-q", "--bare", "-b", "main", str(td / "origin.git"))
        g("clone", "-q", str(td / "origin.git"), str(td / "amont"))
        for d in ("amont",):
            g("-C", str(td / d), "config", "user.email", "t@t"); g("-C", str(td / d), "config", "user.name", "t")
        (td / "amont" / "README.md").write_text("v1"); g("-C", str(td / "amont"), "add", "-A")
        g("-C", str(td / "amont"), "commit", "-qm", "v1"); g("-C", str(td / "amont"), "push", "-q", "origin", "HEAD:main")
        g("clone", "-q", "-b", "main", str(td / "origin.git"), str(td / "core"))
        core = td / "core"
        # KARL_USER inexistant : ni le VRAI service karl-agent ni le vrai ~/.claude ne sont touchés
        (core / ".env").write_text("KARL_USER=utilisateur-inexistant-xyz\n")
        (td / "amont" / "README.md").write_text("v2"); g("-C", str(td / "amont"), "commit", "-qam", "v2")
        g("-C", str(td / "amont"), "push", "-q", "origin", "HEAD:main")
        check("code_a_moi : mon propre checkout → oui", C.code_a_moi(core) is True)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = C.update(core, dry=False)
        o = out.getvalue()
        check("mise à jour SANS sudo : le code avance", rc == 0 and (core / "README.md").read_text() == "v2", o)
        check("…et elle dit son profil : installation mono, verrou sauté",
              "installation mono" in o and "re-verrouillé" not in o, o)
        r = subprocess.run([sys.executable, str(HERE / "pm-core-update.py"), "--core-dir", str(core)],
                           capture_output=True, text=True, timeout=60)
        check("CLI sans --dry-run : pas de re-exec sudo quand le code est à moi",
              r.returncode == 0 and "re-exec sudo" not in r.stdout + r.stderr, r.stdout + r.stderr)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — pm-core-update (RM3033)")
