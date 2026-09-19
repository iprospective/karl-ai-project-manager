#!/usr/bin/env python3
"""Tests RM3070 L2 — le cockpit ne propose que des portées qui peuvent aboutir.

Deux portées s'offraient sans pouvoir tenir : le `.env` **global** d'un secret et l'installation
d'un moteur **pour toute la machine**. Les deux passent par `sudo -n` ; or la règle sudoers exige
un mot de passe (barrière humaine voulue, §13a), donc `-n` échoue toujours. L'utilisateur voyait
une erreur de sudo au clic, là où rien n'était cassé.

Désormais : la capacité est SONDÉE, le refus est explicite et donne la commande à taper.

Lancer : python3 scripts/test_karl_agent_portees.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("ka", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(ka)
except SystemExit:
    pass

ADMIN = {"admin": True, "user": "mathieu"}
SECRET = {"name": "redmine-ipro", "type": "redmine", "key": "API_KEY", "value": "x", "scope": "global"}


def erreur(fn, *a, **k):
    try:
        fn(*a, **k)
    except ka.ApiError as e:
        return e
    return None


# — la sonde elle-même : mise en cache, et jamais une exception qui remonte —
ka._SUDO_CACHE.update({"at": 0.0, "ok": {}})
appels = []
_vrai_run = ka.subprocess.run
ka.subprocess.run = lambda cmd, **kw: appels.append(cmd) or _vrai_run(["true"], **kw)
check("peut_sudo sonde une fois…", ka.peut_sudo("root") is True and len(appels) == 1, str(appels))
check("…puis répond de mémoire (pas un sudo par clic)", ka.peut_sudo("root") is True and len(appels) == 1)
ka.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("sudo absent"))
ka._SUDO_CACHE.update({"at": 0.0, "ok": {}})
check("sudo absent : False, pas d'exception", ka.peut_sudo("root") is False)
ka.subprocess.run = _vrai_run

# — secrets : portée globale refusée quand elle ne peut pas aboutir —
ka._SUDO_CACHE.update({"at": 9e9, "ok": {"root": False}})
e = erreur(ka.op_provider_secret, dict(SECRET), ADMIN)
check("portée globale sans sudo : refus 409 (pas une erreur de sudo au clic)", e and e.code == 409, str(e))
check("…et le refus donne la commande à taper", e and "sudo mmi-pm provider-secret" in str(e) and "--scope global" in str(e), str(e))
e = erreur(ka.op_provider_secret, {**SECRET, "scope": "user", "user": "bob"}, ADMIN)
check("écrire le .env d'un AUTRE développeur : même refus, avec --user", e and e.code == 409 and "--user bob" in str(e), str(e))
e = erreur(ka.op_provider_secret, dict(SECRET), {"admin": False})
check("un non-administrateur est refusé AVANT (403), le motif reste le privilège", e and e.code == 403, str(e))

# — avec la capacité, la portée globale repart vers le script (on n'appelle rien pour de vrai) —
ka._SUDO_CACHE.update({"at": 9e9, "ok": {"root": True}})
vus = []
ka._secret_cmd = lambda args, valeur=None, as_user=None: vus.append((args, as_user)) or ""
r = ka.op_provider_secret(dict(SECRET), ADMIN)
check("sudo possible : la portée globale passe", r.get("ok") and r.get("scope") == "global", str(r))
check("…en visant root, avec --scope global", vus and vus[0][1] == "root" and "global" in vus[0][0], str(vus))

# — moteurs : installation « pour tous » —
ka._SUDO_CACHE.update({"at": 9e9, "ok": {"root": False}})
e = erreur(ka.op_engine_install, {"recipe": "claude", "action": "install", "scope": "system"}, ADMIN)
check("installer pour toute la machine sans sudo : refus 409 avec la commande terminal",
      e and e.code == 409 and "mmi-pm engine-install" in str(e), str(e))
e = erreur(ka.op_engine_install, {"recipe": "claude", "action": "install", "scope": "system"}, {"admin": False})
check("…et un non-administrateur reste refusé en 403", e and e.code == 403, str(e))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — portées : ne montrer que le possible (RM3070 L2)")
