#!/usr/bin/env python3
"""Tests du miroir CF : délai d'attente, relecture après écriture (RM3366).

Ce qu'on vérifie ici n'est pas le bon fonctionnement nominal — il était déjà
acquis — mais les trois comportements qui manquaient le jour où l'API a traîné :
le PUT passe un délai, l'écriture est RELUE, et une divergence se dit.
"""
import io
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_cf_mirror

FAILURES = []
PASSED = 0


def check(condition, label):
    """Assertion élémentaire, sans dépendance."""
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ok   {label}")
    else:
        FAILURES.append(label)
        print(f"  FAIL {label}")


def main():
    print("== Délai d'attente du PUT")

    check(hasattr(pm_cf_mirror, "HTTP_TIMEOUT"), "un délai d'attente est défini")
    check(isinstance(pm_cf_mirror.HTTP_TIMEOUT, int) and pm_cf_mirror.HTTP_TIMEOUT > 0,
          "il vaut un nombre de secondes positif")

    # Environnement minimal pour que push_text_cf aille jusqu'au PUT.
    import os
    os.environ.setdefault("REDMINE_URL", "https://exemple.invalide")
    os.environ.setdefault("REDMINE_API_KEY", "factice")

    vu = {}

    def faux_urlopen(req, timeout=None):
        """Capture le délai transmis, et rend une réponse vide."""
        vu["timeout"] = timeout
        return io.BytesIO(b"{}")

    original_urlopen = pm_cf_mirror.urllib.request.urlopen
    original_resolve = pm_cf_mirror.resolve_cf_id
    original_pull = pm_cf_mirror.pull_text_cf
    pm_cf_mirror.urllib.request.urlopen = faux_urlopen
    pm_cf_mirror.resolve_cf_id = lambda env_var, cf_name: 33
    try:
        # Relecture conforme : le champ porte bien ce qu'on a écrit.
        pm_cf_mirror.pull_text_cf = lambda rm_id, env_var, cf_name, verbose=True: "- [x] fait"
        ok = pm_cf_mirror.push_text_cf(1, "- [x] fait", env_var="X", cf_name="Y")
        check(vu.get("timeout") == pm_cf_mirror.HTTP_TIMEOUT, "le PUT transmet le délai d'attente")
        check(ok is True, "une écriture relue conforme est un succès")

        print("\n== Relecture après écriture")

        # Relecture NON conforme : l'écriture n'a pas pris.
        pm_cf_mirror.pull_text_cf = lambda rm_id, env_var, cf_name, verbose=True: "- [ ] pas fait"
        err = io.StringIO()
        vrai_stderr, sys.stderr = sys.stderr, err
        try:
            ok = pm_cf_mirror.push_text_cf(2, "- [x] fait", env_var="X", cf_name="Y")
        finally:
            sys.stderr = vrai_stderr
        check(ok is False, "une écriture qui n'a pas pris est un ÉCHEC, pas un succès silencieux")
        message = err.getvalue()
        check("DIVERG" in message.upper(), "la divergence est annoncée")
        check("pm-task-cf-resync" in message, "et la commande de réparation est donnée")

        # Relecture impossible (API muette) : on ne peut pas conclure à la réussite.
        pm_cf_mirror.pull_text_cf = lambda rm_id, env_var, cf_name, verbose=True: None
        err = io.StringIO()
        vrai_stderr, sys.stderr = sys.stderr, err
        try:
            ok = pm_cf_mirror.push_text_cf(3, "- [x] fait", env_var="X", cf_name="Y")
        finally:
            sys.stderr = vrai_stderr
        check(ok is False, "une relecture impossible ne compte pas pour une réussite")

        # Sans vérification demandée, le PUT seul suffit (chemins internes rapides).
        pm_cf_mirror.pull_text_cf = lambda rm_id, env_var, cf_name, verbose=True: None
        ok = pm_cf_mirror.push_text_cf(4, "- [x] fait", env_var="X", cf_name="Y", verify=False)
        check(ok is True, "verify=False rend la main sans relire")

        print("\n== Pannes réseau")

        def urlopen_qui_traine(req, timeout=None):
            raise OSError("timed out")

        pm_cf_mirror.urllib.request.urlopen = urlopen_qui_traine
        err = io.StringIO()
        vrai_stderr, sys.stderr = sys.stderr, err
        try:
            ok = pm_cf_mirror.push_text_cf(5, "- [x] fait", env_var="X", cf_name="Y")
        finally:
            sys.stderr = vrai_stderr
        check(ok is False, "un délai dépassé rend False au lieu de remonter une exception")
        check("timed out" in err.getvalue(), "et la cause est dite")
    finally:
        pm_cf_mirror.urllib.request.urlopen = original_urlopen
        pm_cf_mirror.resolve_cf_id = original_resolve
        pm_cf_mirror.pull_text_cf = original_pull

    print(f"\n{PASSED} test(s) OK, {len(FAILURES)} échec(s)")
    for one in FAILURES:
        print(f"  - {one}")

    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
