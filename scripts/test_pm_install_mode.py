#!/usr/bin/env python3
"""Tests RM3070 L0 — le mode d'installation est déclaré, résolu, et contrôlé sans bloquer.

Lancer : python3 scripts/test_pm_install_mode.py
"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pm_install_mode as M  # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[L0] résolution : env > conf > défaut")
check("rien de déclaré : mono, et on le dit « défaut »", M.resoudre({}, {})[:2] == ("mono", "défaut"))
check("la conf déclare multi", M.resoudre({"install": {"mode": "multi"}}, {})[:2]
      == ("multi", "conf install.mode"))
check("l'unité de service l'emporte sur la conf",
      M.resoudre({"install": {"mode": "multi"}}, {"KARL_INSTALL_MODE": "mono"})[:2]
      == ("mono", "env KARL_INSTALL_MODE"))
check("casse et espaces tolérés", M.resoudre({"install": {"mode": " Multi "}}, {})[0] == "multi")
m, src, av = M.resoudre({"install": {"mode": "mutli"}}, {})
check("une faute de frappe retombe sur mono EN LE DISANT", m == "mono" and av and "mutli" in av[0], av)

print("\n[L0] écarts : ce que l'installation contredit")
mono_propre = {"compte": "dev", "compte_service": False, "sudoers": False, "code_root": False, "comptes": 1}
check("mono cohérent : aucun écart", M.ecarts("mono", mono_propre) == [])
e = M.ecarts("mono", {**mono_propre, "code_root": True})
check("mono avec code root : la mise à jour exigera sudo", e and "sudo" in e[0], e)
e = M.ecarts("mono", {**mono_propre, "comptes": 3, "compte_service": True, "compte": "karl"})
check("mono avec compte de service et 3 comptes : deux écarts", len(e) == 2, e)
e = M.ecarts("multi", mono_propre)
check("multi sous un compte personnel, un seul compte : deux écarts", len(e) == 2, e)
check("multi cohérent : aucun écart",
      M.ecarts("multi", {"compte": "karl", "compte_service": True, "sudoers": True,
                         "code_root": True, "comptes": 4}) == [])
check("un signal illisible (None) n'accuse personne",
      M.ecarts("mono", {"compte": "x", "compte_service": None, "sudoers": None,
                        "code_root": None, "comptes": None}) == [])

print("\n[L0] signaux réels")
with tempfile.TemporaryDirectory() as d:
    u = pathlib.Path(d, "karl-users.json")
    check("pas de fichier de comptes : 0 compte", M.signaux(pathlib.Path(d), u)["comptes"] == 0)
    u.write_text(json.dumps({"a": {}, "b": {}}))
    s = M.signaux(pathlib.Path(d), u)
    check("deux comptes comptés", s["comptes"] == 2, s)
    check("un dossier à moi n'est pas « code root »", s["code_root"] is False, s)
    u.write_text("{pas du json")
    check("fichier de comptes illisible : None", M.signaux(None, u)["comptes"] is None)
check("le compte courant est nommé", M.signaux()["compte"])

print("\n[L0] le bloc exposé par /health")
with tempfile.TemporaryDirectory() as d:
    e = M.etat({"install": {"mode": "multi"}}, pathlib.Path(d), pathlib.Path(d, "u.json"), env={})
check("porte mode, source, signaux et avertissements",
      set(e) == {"mode", "source", "signals", "warnings"} and e["mode"] == "multi", e)
check("…et dit en clair qu'un multi à un seul compte est incohérent",
      any("un seul compte" in w for w in e["warnings"]), e["warnings"])

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — mode d'installation déclaré et contrôlé (RM3070 L0)"))
sys.exit(1 if FAIL else 0)
