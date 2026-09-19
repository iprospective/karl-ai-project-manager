#!/usr/bin/env python3
"""Tests RM1777 — bot Telegram : liste blanche stricte, correspondance utilisateurs, verrou au coffre.

Sans réseau : `send`, `delete_message` et le résolveur de secrets sont remplacés.

Lancer : python3 scripts/test_karl_telegram_bot.py
"""
import importlib.util
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
try:
    import requests  # noqa: F401
except ImportError:  # le bot en dépend ; les tests n'ouvrent aucune connexion
    import types
    sys.modules["requests"] = types.SimpleNamespace(RequestException=Exception)
spec = importlib.util.spec_from_file_location("tg", HERE / "karl-telegram-bot.py")
T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)
FAIL = []
ENVOIS = []
T.send = lambda token, chat_id, texte, **k: ENVOIS.append(texte)
T.delete_message = lambda *a, **k: None


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def message(uid, texte):
    return {"chat": {"id": uid}, "message_id": 1, "from": {"id": uid, "username": f"u{uid}"},
            "text": texte}


def bot(users=None, raw="", lock_hash=None):
    users = users or {}
    return {"token": "x", "whitelist": T.build_whitelist(users, raw), "users": users,
            "lock": T.Lock(lock_hash), "cfg_pm": None, "manager_id": 5, "start": time.time(),
            "version": "test"}


def dernier(b, uid, texte):
    ENVOIS.clear()
    T.handle(b, message(uid, texte))
    return ENVOIS[-1] if ENVOIS else ""


print("[RM1777] liste blanche vide = personne (plus de « mode découverte »)")
b = bot()
check("un inconnu est refusé, poliment, avec la marche à suivre",
      "pas autorisé" in dernier(b, 42, "/status") and "/whoami" in ENVOIS[-1], ENVOIS)
check("…même pour /help", "pas autorisé" in dernier(b, 42, "/help"), ENVOIS)
check("/whoami répond quand même — c'est ainsi qu'on trouve son ID",
      "<code>42</code>" in dernier(b, 42, "/whoami"), ENVOIS)
check("…et dit qu'il n'est pas reconnu", "Non reconnu" in ENVOIS[-1], ENVOIS)

print("\n[RM1777] la correspondance alimente la liste blanche et dit qui est qui")
conf = {"telegram": {"users": [
    {"telegram_id": 111, "pm_user": "iprospective", "redmine_id": 5, "name": "Mathieu"},
    {"telegram_id": "222", "pm_user": "typo"},          # chaîne : ignorée, signalée
    {"pm_user": "sans-id"},                              # pas d'ID : ignorée
]}}
users = T.load_users(conf)
check("seules les entrées à telegram_id entier sont retenues", list(users) == [111], users)
b = bot(users, raw="333")
check("un utilisateur de la correspondance passe la liste blanche",
      "pas autorisé" not in dernier(b, 111, "/help"), ENVOIS)
check("le repli TELEGRAM_WHITELIST reste accepté", "pas autorisé" not in dernier(b, 333, "/help"))
check("un ID mal saisi (chaîne) n'autorise PAS son titulaire",
      "pas autorisé" in dernier(b, 222, "/help"), ENVOIS)
check("/whoami nomme l'utilisateur reconnu", "Mathieu" in dernier(b, 111, "/whoami"), ENVOIS)

print("\n[RM1777] conf fusionnée : la correspondance vit dans pm.config.local.yml")
with tempfile.TemporaryDirectory() as d:
    pathlib.Path(d, "pm.config.yml").write_text("ia:\n  default_manager:\n    redmine_id: 5\n")
    pathlib.Path(d, "pm.config.local.yml").write_text(
        "telegram:\n  users:\n    - telegram_id: 111\n      pm_user: iprospective\n")
    c = T.load_conf(d)
check("les deux fichiers sont lus et fusionnés",
      c["ia"]["default_manager"]["redmine_id"] == 5 and T.load_users(c).get(111), c)

print("\n[RM1777] empreinte du verrou lue au coffre")
vu = []
def coffre(uri, champ):
    vu.append((uri, champ)); return "pbkdf2_sha256$200000$sel$empreinte\n"
h, src = T.resolve_lock_hash("secret:telegram/karl-lock", resolver=coffre)
check("une URI secret: est résolue, champ password",
      src == "coffre" and vu == [("secret:telegram/karl-lock", "password")] and h.endswith("empreinte"),
      (h, src, vu))
h, src = T.resolve_lock_hash("pbkdf2_sha256$1$a$b", resolver=coffre)
check("une empreinte brute (.env) reste acceptée, étiquetée comme telle", src == ".env" and len(vu) == 1)
check("rien de configuré = verrou absent", T.resolve_lock_hash("") == (None, "absente"))
def ferme(uri, champ):
    raise RuntimeError("coffre verrouillé")
try:
    T.resolve_lock_hash("secret:telegram/karl-lock", resolver=ferme); leve = False
except RuntimeError:
    leve = True
check("coffre fermé : ça LÈVE — jamais un démarrage sans verrou", leve)
try:
    T.resolve_lock_hash("vaultwarden://x/y", resolver=lambda u, c: "  "); leve = False
except RuntimeError:
    leve = True
check("empreinte vide au coffre : ça lève aussi", leve)

print("\n[RM1777] le verrou issu du coffre protège vraiment")
b = bot(users, lock_hash=T.hash_password("bon-mdp"))
check("verrouillé par défaut", "Verrouillé" in dernier(b, 111, "/status"), ENVOIS)
check("/unlock avec le bon mot de passe ouvre", "Déverrouillé" in dernier(b, 111, "/unlock bon-mdp"), ENVOIS)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — bot Telegram : liste blanche, correspondance, verrou au coffre (RM1777)"))
sys.exit(1 if FAIL else 0)
