#!/usr/bin/env python3
"""Tests RM2660 — le GC supprime ce qu'il annonce, et rien d'autre.

Le dry-run annonçait 78 branches à chaque passage sans jamais les supprimer :
il testait « ancêtre de origin/main » (juste) là où l'exécution s'en remettait
à `git branch -d`, qui compare au HEAD du dépôt. Dans un bare, HEAD pointe sur
une branche arbitraire — ici un reliquat de ticket — et son verdict ne dit rien
de l'intégration réelle.

Le scénario ci-dessous REPRODUIT cette configuration : HEAD du bare sur une
branche de ticket sans rapport. Sans le correctif, la branche intégrée n'est
pas supprimée et le dry-run se répète indéfiniment.

Lancer : python3 scripts/test_pm_env_gc_branches.py
"""
import importlib.util
import io
import contextlib
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_env_gc", HERE / "pm-env-gc.py")
gc = importlib.util.module_from_spec(spec)
sys.modules["pm_env_gc"] = gc
spec.loader.exec_module(gc)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def sh(*args, cwd):
    subprocess.run(args, cwd=str(cwd), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build():
    """Un bare + une branche intégrée + une branche non intégrée, et le HEAD
    du bare posé sur une TROISIÈME branche sans rapport."""
    root = pathlib.Path(tempfile.mkdtemp())
    work, bare = root / "work", root / "repo.git"
    sh("git", "init", "-q", "-b", "main", str(work), cwd=root)
    sh("git", "config", "user.email", "t@t", cwd=work)
    sh("git", "config", "user.name", "t", cwd=work)
    (work / "a.txt").write_text("1", encoding="utf-8")
    sh("git", "add", "-A", cwd=work)
    sh("git", "commit", "-qm", "base", cwd=work)

    # La branche où traînera le HEAD du bare, prise AVANT tout le reste : elle
    # ne contiendra donc pas le travail intégré plus bas. C'est précisément la
    # configuration qui faisait échouer `git branch -d` — la créer après le
    # merge la rendrait « contenante » et le test ne prouverait plus rien.
    sh("git", "branch", "333-reliquat", cwd=work)

    # branche intégrée : commit puis merge dans main
    sh("git", "checkout", "-qb", "111-integree", cwd=work)
    (work / "b.txt").write_text("2", encoding="utf-8")
    sh("git", "add", "-A", cwd=work)
    sh("git", "commit", "-qm", "travail livré", cwd=work)
    sh("git", "checkout", "-q", "main", cwd=work)
    sh("git", "merge", "-q", "--no-ff", "-m", "merge", "111-integree", cwd=work)

    # branche NON intégrée : du travail qui n'est nulle part ailleurs
    sh("git", "checkout", "-qb", "222-non-integree", cwd=work)
    (work / "c.txt").write_text("3", encoding="utf-8")
    sh("git", "add", "-A", cwd=work)
    sh("git", "commit", "-qm", "travail non mergé", cwd=work)

    sh("git", "checkout", "-q", "main", cwd=work)
    sh("git", "clone", "-q", "--bare", str(work), str(bare), cwd=root)
    # LE piège : HEAD du bare sur une branche de ticket quelconque
    sh("git", "symbolic-ref", "HEAD", "refs/heads/333-reliquat", cwd=bare)
    return root, bare


def run(bare, apply, verbose=False):
    """Lance gc_branches en capturant sa sortie. Tous les tickets sont `ferme`."""
    gc.ticket_status = lambda cfg, rm_id: "ferme"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        pruned, kept, busy = gc.gc_branches(None, bare, apply, verbose)
    return pruned, kept, busy, buf.getvalue()


root, bare = build()

# — dry-run : la branche intégrée est annoncée, l'autre non —
pruned, kept, busy, out = run(bare, apply=False)
check("le dry-run annonce la branche intégrée", "111-integree" in out and pruned == 1)
check("il n'annonce PAS la branche non intégrée", "222-non-integree" not in out)
check("et il la compte comme gardée, au lieu de la taire", kept >= 1)

# — exécution : elle fait exactement ce qui était annoncé —
# C'est le cœur du ticket : avant le correctif, `git branch -d` refusait ici,
# car HEAD pointe sur 333-reliquat qui ne contient pas 111-integree.
pruned, kept, busy, out = run(bare, apply=True)
check("l'exécution supprime ce que le dry-run avait annoncé", pruned == 1)
refs = subprocess.run(["git", "-C", str(bare), "for-each-ref", "--format=%(refname:short)",
                       "refs/heads/"], capture_output=True, text=True).stdout.split()
check("la branche intégrée a bien disparu du dépôt", "111-integree" not in refs)
check("la branche NON intégrée est toujours là", "222-non-integree" in refs)
check("le travail non mergé n'a donc pas été perdu",
      subprocess.run(["git", "-C", str(bare), "cat-file", "-e", "222-non-integree^{commit}"],
                     capture_output=True).returncode == 0)

# — le symptôme d'origine : plus rien à annoncer après coup —
pruned, kept, busy, out = run(bare, apply=False)
check("un dry-run relancé n'annonce plus aucune suppression", pruned == 0)
check("mais il continue de signaler ce qu'il garde", kept >= 1)

# — la branche du HEAD ne peut pas être supprimée : ne pas l'annoncer non plus —
check("la branche sur laquelle pointe HEAD n'est jamais annoncée",
      "333-reliquat" not in out.replace("→ branche locale à supprimer : 333", "×"))

# — une branche encore checkoutée : git refuse de la supprimer, donc on ne la
#   promet pas. Cas réel : un worktree sale est conservé (garde de non-perte)
#   et sa branche, pourtant intégrée, restait annoncée à chaque passage. —
sh("git", "update-ref", "refs/heads/555-occupee", "main", cwd=bare)
wt = root / "wt-555"
sh("git", "worktree", "add", "-q", str(wt), "555-occupee", cwd=bare)
pruned, kept, busy, out = run(bare, apply=False)
check("une branche rattachée à un worktree n'est pas annoncée",
      "555-occupee" not in out and pruned == 0)
check("elle est comptée comme gardée, avec sa propre raison", busy >= 1)
pruned, kept, busy, out = run(bare, apply=True)
check("et l'exécution ne tente pas de la supprimer",
      "✗ échec" not in out and pruned == 0)
refs = subprocess.run(["git", "-C", str(bare), "for-each-ref", "--format=%(refname:short)",
                       "refs/heads/"], capture_output=True, text=True).stdout.split()
check("elle est toujours là", "555-occupee" in refs)

# — une seule définition de « intégré », pour les worktrees comme pour les branches —
ok, ref = gc.integrated(bare, "222-non-integree")
check("integrated() dit non pour une branche non mergée", ok is False and ref is None)
sh("git", "update-ref", "refs/heads/444-tmp", "main", cwd=bare)
ok, ref = gc.integrated(bare, "444-tmp")
check("et oui pour une branche présente dans main", ok is True and ref)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests GC des branches RM2660 passent")
