#!/usr/bin/env python3
"""Tests RM3070 L2 — portées possibles — et RM3096 — le .env d'un autre développeur.

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

_VRAI_SECRET_CMD = ka._secret_cmd   # remplacé par des doubles plus bas ; restauré avant la section RM3096

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
ka._secret_cmd = lambda args, valeur=None, cible=None, globale=False: vus.append((args, "root" if globale else cible)) or ""
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

# ── RM3096 : le .env d'un AUTRE développeur passe par root + --user, et l'échec ne s'avale plus ──
ka._secret_cmd = _VRAI_SECRET_CMD
ka._SUDO_CACHE.update({"at": 9e9, "ok": {"root": True}})
import pwd as _pwd
moi = _pwd.getpwuid(__import__("os").getuid()).pw_name
lances = []


class _Faux:
    returncode = 0
    stdout = "REDMINE__X__API_KEY\tposée\n"
    stderr = ""


_vrai = ka.subprocess.run
ka.subprocess.run = lambda cmd, **kw: (lances.append(cmd), _Faux())[1]
ka._secret_cmd(["--status"], cible="unautredev")
check("un autre dev : sudo -u ROOT (ce que la règle sudoers autorise), pas sudo -u <dev>",
      lances[-1][:4] == ["sudo", "-n", "-u", "root"], str(lances[-1][:6]))
check("…et --user <dev> est passé au script (l'option existait, elle n'était jamais utilisée)",
      "--user" in lances[-1] and "unautredev" in lances[-1], str(lances[-1]))
lances.clear()
ka._secret_cmd(["--status"], cible=moi)
check("moi-même : aucun sudo", lances[-1][0] != "sudo", str(lances[-1][:3]))
lances.clear()
ka._secret_cmd(["--scope", "global"], globale=True)
check("portée globale : sudo -u root, sans --user", lances[-1][:4] == ["sudo", "-n", "-u", "root"]
      and "--user" not in lances[-1], str(lances[-1][:6]))
ka.subprocess.run = _vrai

etat = {"val": None}
ka._secret_cmd = lambda *a, **k: (_ for _ in ()).throw(ka.ApiError(400, "secret : sudo refusé"))
try:
    vue = ka.op_providers(ADMIN)
    cles = [c for i in vue["instances"] for c in i["secrets"]]
    check("lecture impossible : les clés sont « état inconnu » (None), jamais « absente » (False)",
          bool(cles) and all(c["set"] is None for c in cles), str(cles[:2]))
    check("…et la vue dit que l'état est inconnu, avec le motif",
          vue.get("states_unknown") is True and "sudo" in (vue.get("states_error") or ""), str(vue.get("states_error")))
except Exception as exc:   # noqa: BLE001
    # pm-test purge l'environnement : sans config PM résoluble, la vue n'est pas constructible ici.
    # On le DIT plutôt que de compter un échec — mais on ne le passe jamais sous silence.
    print(f"· ignoré (config PM non résoluble dans cet environnement : {type(exc).__name__}) — "
          "la garde « état inconnu ≠ absente » tourne hors purge")

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — portées possibles (RM3070 L2) et secrets d'un autre développeur (RM3096)")
