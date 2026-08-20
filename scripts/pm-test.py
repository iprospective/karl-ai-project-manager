#!/usr/bin/env python3
"""mmi-pm test — lance la suite de tests hors ligne du système PM (RM2749).

    mmi-pm test                 toute la suite, en parallèle
    mmi-pm test vault secrets   seulement les tests dont le nom contient ça
    mmi-pm test --list          ce qui serait lancé
    mmi-pm test -j 1 -v         séquentiel, sortie complète de chaque test

Ce que ce script EXIGE de l'environnement : rien. C'est le point.

Avant RM2749, il n'existait pas de façon unique de lancer la suite, et son
résultat changeait selon que `PM_CORE_DIR` était exporté ou non : trois tests
tombaient d'un côté, cinq autres de l'autre. « La suite passe » ne voulait donc
rien dire tant qu'on ne précisait pas le shell — et une vraie régression pouvait
se cacher derrière un échec réputé « préexistant ». Ce lanceur PURGE au contraire
les variables qui pointent le runtime (cf. `test_support.INHERITED`) : chaque
test doit se suffire à lui-même, comme il le ferait sur une machine neuve.
`--inherit` lève la purge, pour vérifier qu'un test tient aussi dans un shell
équipé — les deux verdicts doivent être identiques, c'est le contrat.

Conventions de sortie d'un test : 0 = vert, 77 = ignoré volontairement (avec sa
raison sur stdout), tout le reste = rouge.
"""
import argparse
import concurrent.futures
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKIP_RC = 77          # convention Unix (automake) : test non applicable ici

#: Variables qui ramèneraient un test vers le runtime réel. Alignées sur
#: `test_support.INHERITED` — un test hermétique ne doit dépendre d'aucune.
INHERITED = ("PM_CORE_DIR", "PM_DEV_DIR", "PM_CONFIG", "PM_DIR", "PROJECTS_PATH",
             "PM_CONF_DIR", "PM_STATE_DIR", "PM_LOG_DIR", "PM_USER_ENV")


def discover(motifs):
    """Fichiers de test du dépôt, filtrés par sous-chaîne (motifs = OU)."""
    files = sorted(set(SCRIPTS.glob("test_*.py")) | set(SCRIPTS.glob("test-*.py")))
    files = [f for f in files if f.name != "test_support.py"]
    if motifs:
        files = [f for f in files if any(m in f.name for m in motifs)]
    return files


def run_one(path, env, timeout):
    t0 = time.monotonic()
    try:
        r = subprocess.run([sys.executable, str(path)], env=env, cwd=str(SCRIPTS),
                           capture_output=True, text=True, timeout=timeout)
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = 124, f"— pas de verdict après {timeout} s (interrompu)"
    return path.name, rc, out, time.monotonic() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Suite de tests hors ligne du système PM.",
        epilog="Sans argument : tout, en parallèle, dans un environnement purgé.")
    ap.add_argument("motifs", nargs="*", help="ne lancer que les tests dont le nom contient …")
    ap.add_argument("-j", "--jobs", type=int, default=min(8, os.cpu_count() or 4),
                    help="tests en parallèle (défaut : %(default)s ; -j 1 pour isoler un doute)")
    ap.add_argument("-v", "--verbose", action="store_true", help="sortie complète de chaque test")
    ap.add_argument("--list", action="store_true", help="lister sans lancer")
    ap.add_argument("--inherit", action="store_true",
                    help="garder l'environnement du shell (PM_CORE_DIR…) au lieu de le purger")
    ap.add_argument("--timeout", type=int, default=300, help="par test, en secondes")
    a = ap.parse_args(argv)

    files = discover(a.motifs)
    if not files:
        print("aucun test ne correspond", file=sys.stderr)
        return 2
    if a.list:
        for f in files:
            print(f.name)
        return 0

    env = dict(os.environ)
    if not a.inherit:
        for k in INHERITED:
            env.pop(k, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    verts, rouges, ignores = [], [], []
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        for name, rc, out, dt in pool.map(lambda f: run_one(f, env, a.timeout), files):
            if rc == 0:
                verts.append(name)
                print(f"✓ {name}  ({dt:.1f}s)")
            elif rc == SKIP_RC:
                ignores.append((name, out.strip().splitlines()[-1] if out.strip() else ""))
                print(f"⊘ {name} — {ignores[-1][1]}")
            else:
                rouges.append((name, rc, out))
                print(f"✗ {name}  (code {rc}, {dt:.1f}s)")
            if a.verbose and out:
                print("".join(f"    {l}\n" for l in out.rstrip().splitlines()))

    dt = time.monotonic() - t0
    print(f"\n{len(verts)} vert(s), {len(rouges)} rouge(s), {len(ignores)} ignoré(s) "
          f"— {dt:.0f}s, environnement {'hérité' if a.inherit else 'purgé'}")
    for name, rc, out in rouges:
        # Les dernières lignes suffisent presque toujours à situer l'échec ; le
        # reste est à un `-v` près. Tronquer sans le dire serait pire que tout.
        lignes = out.rstrip().splitlines()
        print(f"\n── {name} (code {rc}) " + "─" * max(0, 50 - len(name)))
        if len(lignes) > 15 and not a.verbose:
            print(f"   … {len(lignes) - 15} ligne(s) plus haut, `-v` pour tout voir")
        for l in lignes[-15:]:
            print(f"   {l}")
    return 1 if rouges else 0


if __name__ == "__main__":
    sys.exit(main())
