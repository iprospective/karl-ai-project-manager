#!/usr/bin/env python3
"""Tests RM3221 — domaine des environnements de recette, lu dans le pm.env de l'instance.

On source les vraies bibliothèques du framework de synchro dans un bash isolé, avec
un pm.env de test désigné par SYNCHRO_INSTANCE_ENV : aucune dépendance à la
configuration de la machine qui lance les tests, aucun accès réseau.
"""
import pathlib
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SYNCHRO = HERE.parent / "tools" / "synchro"
fails = []
BASE_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def bash(script, pm_env=None, env_extra=None):
    """Exécute `script` après avoir sourcé common.sh + helpers.sh."""
    env = dict(BASE_ENV, SYNCHRO_INSTANCE_ENV=str(pm_env) if pm_env else "/nonexistent/pm.env")
    env.update(env_extra or {})
    full = f'set -uo pipefail\n. "{SYNCHRO}/lib/common.sh"\n. "{SYNCHRO}/lib/helpers.sh"\n{script}'
    r = subprocess.run(["bash", "-c", full], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    temoin = td / "EXECUTE"
    pm_env = td / "pm.env"
    # Formes réelles d'un pm.env : commentaires, guillemets ou non, commentaire en fin de
    # ligne — et une ligne piégée qui ne doit JAMAIS être exécutée.
    pm_env.write_text(
        "# pm.env — config d'instance\n"
        "GITLAB_URL=https://gitlab.exemple.org\n"
        'TEST_DOMAIN="test.exemple.org"\n'
        "TEST_HOST=dev   # conteneur de recette\n"
        "DEV_DOMAIN='dev.exemple.org'\n"
        f"PIEGE=$(touch {temoin})\n"
    )

    # --- lecture de pm.env
    rc, out = bash('echo "[$TEST_DOMAIN|$TEST_HOST|$DEV_DOMAIN]"', pm_env=pm_env)
    check("pm.env : les trois clés sont lues (guillemets doubles, sans, simples + commentaire)",
          "[test.exemple.org|dev|dev.exemple.org]" in out, out)
    check("pm.env est LU, jamais exécuté (la ligne piégée n'a rien fait)", not temoin.exists())
    rc, out = bash('echo "[${GITLAB_URL:-absent}]"', pm_env=pm_env)
    check("les autres clés de pm.env ne fuient pas dans l'environnement", "[absent]" in out, out)

    rc, out = bash('echo "[$TEST_DOMAIN]"', pm_env=pm_env, env_extra={"TEST_DOMAIN": "surcharge.exemple.org"})
    check("une variable d'environnement l'emporte sur pm.env", "[surcharge.exemple.org]" in out, out)

    rc, out = bash('echo "[$TEST_DOMAIN|$TEST_HOST|$DEV_DOMAIN]"')
    check("pm.env absent : clés vides, sans « unbound variable » sous set -u",
          rc == 0 and "[||]" in out and "unbound" not in out, out)

    # --- garde-fou de domaine
    guard = 'DB_TO="site_test"; DOMAIN="{d}"; guard_local_target; echo "fin"'
    rc, out = bash(guard.format(d="monsite.test.exemple.org"), pm_env=pm_env)
    check("domaine sous TEST_DOMAIN : reconnu, aucun avertissement", "fin" in out and "pas l'air" not in out, out)
    rc, out = bash(guard.format(d="alice.dev.exemple.org"), pm_env=pm_env)
    check("domaine sous DEV_DOMAIN : reconnu, aucun avertissement", "fin" in out and "pas l'air" not in out, out)
    rc, out = bash(guard.format(d="www.monsite.fr"), pm_env=pm_env)
    check("domaine de prod : avertissement qui CITE la convention de l'instance",
          "pas l'air" in out and "test.exemple.org" in out and "pm.env" in out, out)
    rc, out = bash(guard.format(d="www.monsite.fr"))
    check("sans pm.env : l'avertissement dit quelle clé renseigner", "<TEST_DOMAIN>" in out, out)
    rc, out = bash(guard.format(d="site.local"))
    check("filet générique conservé sans pm.env (*.local)", "fin" in out and "pas l'air" not in out, out)

    # --- sync.sh : domaine incomplet arrêté AVANT tout accès à la prod
    env_conf = td / "essai.conf"
    env_conf.write_text('WEBSITE_TYPE="wordpress"\nWEBSITE_PATH="x"\nSSH_AUTH="prod-inexistante"\n'
                        'DB_FROM="x"\nDB_TO="x_test"\nDOMAIN="monsite.${TEST_DOMAIN}"\n')

    def sync(pm):
        r = subprocess.run(["bash", str(SYNCHRO / "sync.sh"), str(env_conf), "--yes"], capture_output=True,
                           text=True, env=dict(BASE_ENV, SYNCHRO_INSTANCE_ENV=pm))
        return r.returncode, r.stdout + r.stderr

    rc, out = sync("/nonexistent/pm.env")
    check("sync.sh sans TEST_DOMAIN : arrêt non nul", rc != 0, out[-300:])
    check("…avec un message qui dit quoi faire (pm.env)", "incomplet" in out and "pm.env" in out, out[-300:])
    check("…et avant tout contact avec la prod", "Cible fichiers" not in out, out[-300:])

    rc, out = sync(str(pm_env))
    check("sync.sh avec TEST_DOMAIN : le domaine est complété et journalisé",
          "monsite.test.exemple.org" in out, out[-300:])

# --- aucune valeur propre à une instance dans le code versionné
code = "".join((SYNCHRO / p).read_text() for p in ("sync.sh", "lib/common.sh", "lib/helpers.sh"))
check("aucun domaine d'instance en dur dans le framework", "iprospective.fr" not in code)

print(f"\n{len(fails)} échec(s)")
raise SystemExit(1 if fails else 0)
