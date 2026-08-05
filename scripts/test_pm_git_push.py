#!/usr/bin/env python3
"""Tests RM2298 — auto-push pm_git face à une branche protégée (RM2030).

Sans réseau : la « protection » est un hook pre-receive local sur un repo bare
qui refuse refs/heads/main (même message « pre-receive hook declined » que
GitLab). Lancer : python3 scripts/test_pm_git_push.py

MISE À JOUR RM2440 — les dépôts montés ici n'ont pas de `.mmi-pm/` : ils sont
donc traités comme des dépôts de **CODE**, dont le comportement est inchangé
(repli sur la branche d'intégration, pas de rebase). Deux ajustements :
  - le **succès est silencieux** : on ne cherche plus une ligne « + push » dans
    la sortie, on vérifie l'effet réel sur le remote — ce qui est de toute façon
    l'assertion utile ;
  - le message de la branche protégée ne renvoie plus vers `pm-promote`
    (déprécié) mais vers la livraison par MR.
Les assertions de sortie lisent `out + err` : `_warn` passe par `pm_output`
quand il est importable, qui écrit sur stdout — chercher dans `err` seul rendait
le test rouge indépendamment du code testé.
"""
import contextlib
import io
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pm_git

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def git(*a, cwd):
    return subprocess.run(["git", *a], cwd=str(cwd), check=True,
                          capture_output=True, text=True).stdout.strip()


def seed(tmp, name):
    """Bare + clone avec un commit initial poussé sur main et dev."""
    bare = tmp / f"{name}.git"
    bare.mkdir()
    git("init", "--bare", ".", cwd=bare)
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=bare)
    work = tmp / name
    git("clone", str(bare), str(work), cwd=tmp)
    git("config", "user.email", "t@t", cwd=work)
    git("config", "user.name", "t", cwd=work)
    git("checkout", "-b", "main", cwd=work)
    (work / "f.md").write_text("v1\n", encoding="utf-8")
    git("add", "f.md", cwd=work)
    git("commit", "-m", "seed", cwd=work)
    git("push", "-u", "origin", "main", cwd=work)
    git("push", "origin", "main:dev", cwd=work)
    return bare, work


def protect_main(bare):
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nwhile read o n r; do\n"
                    '  [ "$r" = "refs/heads/main" ] && { echo "GL-HOOK-ERR: protected" >&2; exit 1; }\n'
                    "done\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)


def autocommit(work, content):
    (work / "f.md").write_text(content, encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        sha = pm_git.autocommit([work / "f.md"], "pm(test): maj")
    return sha, out.getvalue(), err.getvalue()


# — classification des échecs de push —
check("classement : pre-receive → protected",
      pm_git._push_error_kind("! [remote rejected] main -> main (pre-receive hook declined)") == "protected")
check("classement : protected branch → protected",
      pm_git._push_error_kind("remote: GitLab: You are not allowed to push code to protected branches") == "protected")
check("classement : non-fast-forward → non_ff",
      pm_git._push_error_kind("! [rejected] main -> main (non-fast-forward)") == "non_ff")
check("classement : fetch first → non_ff",
      pm_git._push_error_kind("! [rejected] main -> main (fetch first)") == "non_ff")
check("classement : autre → other", pm_git._push_error_kind("fatal: unable to access") == "other")

with tempfile.TemporaryDirectory() as td:
    tmp = pathlib.Path(td)

    # — nominal : push direct OK, et SILENCIEUX (RM2440) —
    bare, work = seed(tmp, "nominal")
    sha, out, err = autocommit(work, "v2\n")
    check("nominal : commit créé", sha is not None, out + err)
    check("nominal : main distante avancée", git("rev-parse", "main", cwd=bare) == git("rev-parse", "HEAD", cwd=work))
    check("nominal : aucune sortie (RM2440)", (out + err).strip() == "", out + err)

    # — main protégée (dépôt de CODE) : repli sur la branche d'intégration —
    bare, work = seed(tmp, "protected")
    protect_main(bare)
    main_before = git("rev-parse", "main", cwd=bare)
    sha, out, err = autocommit(work, "v2\n")
    check("protégée : commit créé", sha is not None, out + err)
    check("protégée : dev distante = HEAD local", git("rev-parse", "dev", cwd=bare) == git("rev-parse", "HEAD", cwd=work))
    check("protégée : main distante intacte", git("rev-parse", "main", cwd=bare) == main_before)
    check("protégée : plus de faux « l'emportera »", "l'emportera" not in (out + err), out + err)

    # — non-fast-forward (une autre instance a poussé) : différé, diagnostic dédié —
    bare, work = seed(tmp, "nonff")
    other = tmp / "other"
    git("clone", str(bare), str(other), cwd=tmp)
    git("config", "user.email", "o@o", cwd=other)
    git("config", "user.name", "o", cwd=other)
    (other / "g.md").write_text("x\n", encoding="utf-8")
    git("add", "g.md", cwd=other)
    git("commit", "-m", "concurrent", cwd=other)
    git("push", "origin", "HEAD:main", cwd=other)
    sha, out, err = autocommit(work, "v2\n")
    check("non-FF : commit conservé, pas de repli",
          sha is not None and git("rev-parse", "dev", cwd=bare) != git("rev-parse", "HEAD", cwd=work),
          out + err)
    check("non-FF : diagnostic « remote a avancé »",
          "remote a avancé" in (out + err) and "l'emportera" in (out + err), out + err)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests pm_git push RM2298 passent")
