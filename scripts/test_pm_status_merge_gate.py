#!/usr/bin/env python3
"""Tests RM2319 — merge gate : pas de a_mep / ferme:resolu avec une branche non mergée.

Reproduit l'incident RM2302 sur un workspace fabriqué (bare + .mmi-pm/meta.yml) :
la fonction unmerged_ticket_branches doit détecter la branche du ticket non mergée
dans la branche d'intégration, y compris quand le frontmatter est tronqué/périmé
(détection par préfixe <id>-*), et se taire une fois la branche mergée.
Lancer : python3 scripts/test_pm_status_merge_gate.py
"""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_tsu", HERE / "pm-task-status-update.py")
tsu = importlib.util.module_from_spec(spec)
sys.modules["pm_tsu"] = tsu
spec.loader.exec_module(tsu)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True,
                   env={"PATH": "/usr/bin:/bin", "HOME": str(cwd or "/tmp"),
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


# — Workspace fabriqué (layout RM1993) : repos/demo.git + .mmi-pm/meta.yml + tâche —
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2319-"))
ws = tmp / "ws"
src = tmp / "src"                       # repo de travail, servira d'origine au bare
src.mkdir(parents=True)
sh("git", "init", "-q", "-b", "dev", str(src))
(src / "f.txt").write_text("base\n")
sh("git", "-C", str(src), "add", "f.txt")
sh("git", "-C", str(src), "commit", "-qm", "base")
sh("git", "-C", str(src), "checkout", "-qb", "9999-ma-feature")
(src / "f.txt").write_text("feature\n")
sh("git", "-C", str(src), "commit", "-qam", "RM9999 feature")
sh("git", "-C", str(src), "checkout", "-q", "dev")

(ws / "repos").mkdir(parents=True)
sh("git", "clone", "-q", "--bare", str(src), str(ws / "repos" / "demo.git"))
(ws / ".mmi-pm").mkdir()
(ws / ".mmi-pm" / "meta.yml").write_text(
    "repos:\n- name: demo\n  integration_branch: dev\n")
tasks = ws / ".mmi-pm" / "tasks"
tasks.mkdir()
md = tasks / "RM9999_ma-feature.md"
md.write_text("---\nredmine_id: 9999\n---\n")

# 1. branche non mergée → détectée (même sans git.branch au frontmatter : préfixe)
found = tsu.unmerged_ticket_branches(md, 9999)
check("branche non mergée détectée", found is not None)
check("nom de branche remonté", found and any("9999-ma-feature" in b for b in found[2]))
check("branche d'intégration remontée", found and found[1] == "dev")

# 2. autre ticket (aucune branche 1234-*) → rien à signaler
check("ticket sans branche → None", tsu.unmerged_ticket_branches(md, 1234) is None)

# 3. après merge dans dev → la garde se tait
sh("git", "-C", str(src), "merge", "-q", "--no-ff", "-m", "merge", "9999-ma-feature")
sh("git", "-C", str(ws / "repos" / "demo.git"), "fetch", "-q", "origin",
   "+refs/heads/*:refs/heads/*")
check("branche mergée → None", tsu.unmerged_ticket_branches(md, 9999) is None)

# 4. tâche hors workspace co-localisé → None (garde best-effort, jamais bloquante)
loose = tmp / "loose.md"
loose.write_text("---\nredmine_id: 9999\n---\n")
check("hors workspace → None", tsu.unmerged_ticket_branches(loose, 9999) is None)

# 5. multi-repo au manifeste → hors garde (ambigu, comme le hook env)
(ws / ".mmi-pm" / "meta.yml").write_text(
    "repos:\n- name: demo\n- name: autre\n")
check("multi-repo → None", tsu.unmerged_ticket_branches(md, 9999) is None)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests merge gate RM2319 passent")
