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

# — RM3173 : un dépôt central RÉEL a des refs distantes (refspec origin/*) ; le distant fait foi —
# Incidents RM3091 / RM3059 : branche rebasée et poussée depuis un autre worktree, mergée ;
# la branche LOCALE du dépôt central restait sur les commits d'avant rebase → refus à tort.
t2 = pathlib.Path(tempfile.mkdtemp(prefix="rm3173-"))
up = t2 / "upstream.git"                       # le GitLab
sh("git", "init", "-q", "--bare", "-b", "dev", str(up))
w = t2 / "w"                                   # un worktree « ailleurs »
sh("git", "clone", "-q", str(up), str(w))
(w / "f.txt").write_text("base\n")
sh("git", "-C", str(w), "add", "f.txt")
sh("git", "-C", str(w), "commit", "-qm", "base")
sh("git", "-C", str(w), "push", "-q", "origin", "HEAD:dev", "HEAD:main")
sh("git", "-C", str(w), "checkout", "-qb", "4242-feature")
(w / "g.txt").write_text("v1\n")
sh("git", "-C", str(w), "add", "g.txt")
sh("git", "-C", str(w), "commit", "-qm", "RM4242 v1")
sh("git", "-C", str(w), "push", "-q", "origin", "4242-feature")

ws2 = t2 / "ws"
(ws2 / "repos").mkdir(parents=True)
central = ws2 / "repos" / "demo.git"
sh("git", "clone", "-q", "--bare", str(up), str(central))
sh("git", "-C", str(central), "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
sh("git", "-C", str(central), "fetch", "-q", "origin")
(ws2 / ".mmi-pm" / "tasks").mkdir(parents=True)
(ws2 / ".mmi-pm" / "meta.yml").write_text("repos:\n- name: demo\n  integration_branch: dev\n")
md2 = ws2 / ".mmi-pm" / "tasks" / "RM4242_feature.md"
md2.write_text("---\nredmine_id: 4242\n---\n")
check("RM3173 : branche poussée non mergée → détectée (par sa version distante)",
      (f := tsu.unmerged_ticket_branches(md2, 4242)) is not None and f[2] == ["origin/4242-feature"] and f[3]["fresh"])

# rebase + push forcé depuis le worktree, puis merge dans dev : la locale du central reste périmée
sh("git", "-C", str(w), "commit", "-q", "--amend", "-m", "RM4242 v1 (rebasée)")
sh("git", "-C", str(w), "push", "-q", "-f", "origin", "4242-feature")
sh("git", "-C", str(w), "checkout", "-q", "dev")
sh("git", "-C", str(w), "merge", "-q", "--no-ff", "-m", "merge 4242", "4242-feature")
sh("git", "-C", str(w), "push", "-q", "origin", "dev")
stale = subprocess.run(["git", "-C", str(central), "merge-base", "--is-ancestor", "4242-feature", "origin/dev"]).returncode
check("…la locale du central est bien périmée (précondition du cas réel)", stale != 0)
check("RM3173 : mergée côté distant, locale périmée → PAS de refus", tsu.unmerged_ticket_branches(md2, 4242) is None)

# mergée dans main seulement (la prod) → pas de refus non plus
sh("git", "-C", str(w), "checkout", "-qb", "4243-hotfix", "origin/main")
(w / "h.txt").write_text("fix\n")
sh("git", "-C", str(w), "add", "h.txt")
sh("git", "-C", str(w), "commit", "-qm", "RM4243 fix")
sh("git", "-C", str(w), "push", "-q", "origin", "4243-hotfix")
sh("git", "-C", str(w), "checkout", "-qB", "main", "origin/main")
sh("git", "-C", str(w), "merge", "-q", "--no-ff", "-m", "merge 4243", "4243-hotfix")
sh("git", "-C", str(w), "push", "-q", "origin", "main")
check("RM3173 : mergée dans main (la prod) → pas de refus", tsu.unmerged_ticket_branches(md2, 4243) is None)

# jamais poussée : seule la locale existe → elle est jugée
sh("git", "-C", str(w), "checkout", "-qb", "4244-local", "dev")
(w / "l.txt").write_text("local\n")
sh("git", "-C", str(w), "add", "l.txt")
sh("git", "-C", str(w), "commit", "-qm", "RM4244 local")
sh("git", "-C", str(w), "push", "-q", str(central), "4244-local")   # dans le central, jamais sur le distant
check("RM3173 : branche jamais poussée → jugée sur la locale, détectée",
      (f := tsu.unmerged_ticket_branches(md2, 4244)) is not None and f[2] == ["4244-local"])

# distant injoignable : on ne peut pas conclure, et on le dit (fresh=False)
sh("git", "-C", str(w), "checkout", "-qb", "4245-x", "dev")
(w / "x.txt").write_text("x\n")
sh("git", "-C", str(w), "add", "x.txt")
sh("git", "-C", str(w), "commit", "-qm", "RM4245")
sh("git", "-C", str(w), "push", "-q", "origin", "4245-x")
sh("git", "-C", str(central), "fetch", "-q", "origin")
sh("git", "-C", str(central), "remote", "set-url", "origin", str(t2 / "disparu.git"))
f = tsu.unmerged_ticket_branches(md2, 4245)
check("RM3173 : fetch en échec → refs signalées non fraîches", f is not None and f[3]["fresh"] is False)
src_tsu = (HERE / "pm-task-status-update.py").read_text(encoding="utf-8")
check("…et le refus a son propre message (« impossible de conclure »)",
      'if not infos["fresh"]:' in src_tsu and "impossible de conclure" in src_tsu)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests merge gate RM2319 passent")
