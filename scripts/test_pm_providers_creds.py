#!/usr/bin/env python3
"""Tests du diagnostic d'identifiants de pm-providers (RM2835).

Lancer : python3 scripts/test_pm_providers_creds.py

Ce que ça vérifie : la ligne `creds=` de `pm-providers.py resolve --axis secret`
n'attribue le repli historique global (`BW_CLIENTID` / `BW_CLIENTSECRET`) qu'à
l'instance PAR DÉFAUT de l'axe. Une instance supplémentaire sans identifiants
propres doit afficher `— aucun`, sans quoi le diagnostic contredit le backend,
qui refuse alors la résolution en `unreachable`.

Boîte noire : on lance le vrai CLI dans un core de test hermétique. Aucun réseau,
aucune valeur d'identifiant affichée — seulement des NOMS (tripwire 11).
"""
import re
import subprocess
import sys
import tempfile

import yaml
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from test_support import core_env, core_with  # noqa: E402

CLI = _HERE / "pm-providers.py"

# Une instance par défaut (celle qui a droit au repli) + une instance ajoutée qui
# n'a AUCUN identifiant propre — c'est elle qui révèle le défaut.
SERVERS = {
    "vw-ipro":    {"axis": "secret", "type": "vaultwarden", "url": "https://vault.test"},
    "ncpw-tiers": {"axis": "secret", "type": "nextcloud_passwords",
                   "url": "https://cloud.test"},
    "kdbx-perso": {"axis": "secret", "type": "keepass", "file": "/nexistepas.kdbx"},
}

ENTITE, PROJET = "clientest", "demo"


def _core(td, providers_projet):
    core = core_with(td, SERVERS)
    proj = core / "projects" / "clients" / ENTITE / "projects" / PROJET
    proj.mkdir(parents=True, exist_ok=True)
    # Écrit via yaml : un `providers.secret` peut être une LISTE de dicts
    # (primaire + secondaires) qu'un f-string rendrait en repr Python.
    (proj / "meta.yml").write_text(
        yaml.safe_dump({"client": ENTITE, "slug": PROJET,
                        "providers": providers_projet},
                       allow_unicode=True, sort_keys=False), encoding="utf-8")
    return core


def _resolve(core, **env_extra):
    """Sortie de `resolve --axis secret` pour le projet de test."""
    env = core_env(core, **env_extra)
    # Le CLI ne doit voir QUE les identifiants que le test lui donne.
    for k in list(env):
        if k.startswith("SECRET__") or k.startswith("BW_"):
            env.pop(k)
    env.update({k: str(v) for k, v in env_extra.items()})
    p = subprocess.run(
        [sys.executable, str(CLI), "resolve", "secret",
         "--client", ENTITE, "--project", PROJET],
        capture_output=True, text=True, env=env, cwd=str(core), timeout=60)
    assert p.returncode == 0, f"CLI en échec ({p.returncode}) :\n{p.stdout}\n{p.stderr}"
    return p.stdout


def _creds(sortie, instance):
    """La ligne `creds=` rattachée à `instance` dans la sortie du CLI."""
    lignes = sortie.splitlines()
    for n, ligne in enumerate(lignes):
        if re.search(rf"\b{re.escape(instance)}\b", ligne):
            for suite in lignes[n + 1:]:
                if "creds=" in suite:
                    return suite.split("creds=", 1)[1].strip()
                if re.search(r"→\s+\S", suite) or "[primaire" in suite or "[secondaire" in suite:
                    break
            raise AssertionError(f"aucune ligne creds= après {instance} :\n{sortie}")
    raise AssertionError(f"{instance} absente de la sortie :\n{sortie}")


# ── Tests ────────────────────────────────────────────────────────────────────
def test_instance_non_defaut_sans_identifiants_affiche_aucun():
    """Le défaut RM2835 : BW_* global ne doit PAS habiller une autre instance."""
    with tempfile.TemporaryDirectory(prefix="prov-") as td:
        core = _core(td, {"secret": {"instance": "ncpw-tiers"}})
        out = _resolve(core, BW_CLIENTID="id-factice", BW_CLIENTSECRET="secret-factice")
        assert _creds(out, "ncpw-tiers") == "— aucun", out


def test_instance_par_defaut_garde_le_repli_historique():
    """Non-régression : `vw-ipro` continue de voir les BW_* du poste."""
    with tempfile.TemporaryDirectory(prefix="prov-") as td:
        core = _core(td, {"secret": {"instance": "vw-ipro"}})
        out = _resolve(core, BW_CLIENTID="id-factice", BW_CLIENTSECRET="secret-factice")
        assert _creds(out, "vw-ipro") == "CLIENTID, CLIENTSECRET", out


def test_identifiants_par_slug_toujours_affiches():
    """Une instance qui porte ses propres clés les affiche, défaut ou pas."""
    with tempfile.TemporaryDirectory(prefix="prov-") as td:
        core = _core(td, {"secret": {"instance": "ncpw-tiers"}})
        out = _resolve(core, BW_CLIENTID="id-factice", BW_CLIENTSECRET="secret-factice",
                       SECRET__NCPW_TIERS__USER="agent",
                       SECRET__NCPW_TIERS__TOKEN="jeton-factice")
        assert _creds(out, "ncpw-tiers") == "TOKEN, USER", out


def test_aucune_valeur_dans_la_sortie():
    """Tripwire 11 : le diagnostic ne montre que des NOMS de clés."""
    with tempfile.TemporaryDirectory(prefix="prov-") as td:
        core = _core(td, {"secret": {"instance": "ncpw-tiers"}})
        out = _resolve(core, BW_CLIENTID="id-factice", BW_CLIENTSECRET="secret-factice",
                       SECRET__NCPW_TIERS__USER="agent",
                       SECRET__NCPW_TIERS__TOKEN="jeton-tres-reconnaissable")
        for valeur in ("jeton-tres-reconnaissable", "secret-factice", "id-factice"):
            assert valeur not in out, f"{valeur!r} fuit dans la sortie :\n{out}"


def test_les_deux_instances_dans_la_meme_resolution():
    """Le cas réel du déploiement : défaut + coffre client, côte à côte.

    `kdbx-perso` est secondaire ; sans identifiants propres elle doit, elle
    aussi, afficher `— aucun`, pendant que le primaire garde son repli.
    """
    with tempfile.TemporaryDirectory(prefix="prov-") as td:
        core = _core(td, {"secret": [{"instance": "vw-ipro", "role": "primary"},
                                     {"instance": "kdbx-perso", "role": "secondary"}]})
        out = _resolve(core, BW_CLIENTID="id-factice", BW_CLIENTSECRET="secret-factice")
        assert _creds(out, "vw-ipro") == "CLIENTID, CLIENTSECRET", out
        assert _creds(out, "kdbx-perso") == "— aucun", out


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
        except Exception as e:  # noqa: BLE001 — un runner de test rapporte tout
            echecs += 1
            print(f"  ✗ {nom} : {type(e).__name__}: {e}")
    print(f"\n{len(tests) - echecs}/{len(tests)} tests passés")
    sys.exit(1 if echecs else 0)
