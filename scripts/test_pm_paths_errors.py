#!/usr/bin/env python3
"""Tests RM3119 — une bibliothèque ne tue pas son appelant parce que la config PM manque.

`PMConfig.load()` **sortait** (`sys.exit`) quand le `.env` canonique n'était pas résoluble — le cas
normal d'un clone de dev. `SystemExit` n'héritant pas d'`Exception`, tous les appelants qui se
protègent par `except Exception` — la forme normale — la laissaient remonter et mouraient. Mesuré
avant correction : **17 tests rouges** dans un worktree, avec pour seul symptôme un message d'aide
sur le `.env` et aucun nom de test. On cherchait un problème d'environnement là où il y avait un
problème de contrat.

Ce que ces tests tiennent :
  - l'erreur est une vraie `Exception`, donc attrapable par qui se protège normalement ;
  - l'ergonomie du CLI ne change pas : message identique, code 1, sans trace ;
  - les quatre résolveurs de bibliothèque répondent « je ne sais pas » au lieu de mourir ;
  - aucun `sys.exit` ne revient dans `PMConfig.load()`.

Lancer : python3 scripts/test_pm_paths_errors.py
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


#: un dossier qui a l'air d'un repo PM mais n'a ni `.env` ni `projects_root` : le clone de dev
tmp = pathlib.Path(tempfile.mkdtemp(prefix="pm-paths-3119-"))
(tmp / "pm.config.yml").write_text("roots: {}\npaths:\n  entity: '{projects_root}/{entity}'\n", encoding="utf-8")

ENV = dict(os.environ, PM_DIR=str(tmp), PM_CORE_DIR=str(tmp), HOME=str(tmp))
CODE = "import sys; sys.path.insert(0, %r)\n" % str(HERE)


def run(src, env=None):
    return subprocess.run([sys.executable, "-c", CODE + src], capture_output=True, text=True,
                          env=env or ENV, cwd=str(tmp))


# ── 1. l'erreur est une Exception, pas une sortie ───────────────────────────
r = run("from pm_paths import PMConfig, PMConfigError\n"
        "try:\n"
        "    PMConfig.load(%r)\n" % str(tmp) +
        "except Exception as e:\n"
        "    print('ATTRAPEE', type(e).__name__)\n"
        "print('ENCORE VIVANT')\n")
check("`except Exception` l'attrape — c'est TOUT l'objet du ticket",
      "ATTRAPEE PMConfigError" in r.stdout, r.stdout + r.stderr)
check("…et le programme continue après", "ENCORE VIVANT" in r.stdout, r.stdout + r.stderr)
check("PMConfigError descend d'Exception, pas de SystemExit",
      run("from pm_paths import PMConfigError\n"
          "print(issubclass(PMConfigError, Exception), issubclass(PMConfigError, SystemExit))").stdout.strip()
      == "True False")

# ── 2. le CLI, lui, ne change pas : message + code 1, sans trace ────────────
r = run("from pm_paths import PMConfig\nPMConfig.load(%r)\n" % str(tmp))
check("non attrapée : code de sortie 1 (comme avant)", r.returncode == 1, str(r.returncode))
check("…le message d'aide est rendu tel quel", "ERREUR" in r.stderr and ".env" in r.stderr, r.stderr[:200])
check("…et SANS trace d'exception : c'est une erreur d'usage, pas un plantage",
      "Traceback" not in r.stderr, r.stderr[-300:])

# ── 3. les résolveurs de bibliothèque répondent, ils ne meurent pas ─────────
for nom, src, attendu in [
    ("pm_stores.state_root", "import pm_stores; print('R=', pm_stores.state_root())", "R="),
    ("pm_stores.worklog_dir", "import pm_stores; print('R=', pm_stores.worklog_dir())", "R="),
    ("pm_log._declared_dir", "import pm_log; print('R=', pm_log._declared_dir())", "R="),
    ("pm_notify.path", "import pm_notify; print('R=', pm_notify.path())", "R="),
    ("pm_monitor.associations", "import pm_monitor; print('R=', pm_monitor.associations())", "R="),
]:
    r = run(src)
    check(f"{nom} rend une valeur au lieu de tuer l'appelant",
          r.returncode == 0 and attendu in r.stdout, (r.stdout + r.stderr)[-220:])

# ── 4. la garde : que `load()` ne se remette pas à sortir ───────────────────
src = (HERE / "pm_paths.py").read_text(encoding="utf-8")
corps = src[src.index("class PMConfig:"):]      # « class PMConfig » tout court attrape PMConfigError
appels = [l.strip() for l in corps.splitlines() if "sys.exit(" in l]
check("plus aucun `sys.exit` dans PMConfig — il tuerait de nouveau les bibliothèques (RM3119)",
      not appels, str(appels[:2]))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — la config PM manquante se RATTRAPE, elle ne tue plus (RM3119)")
