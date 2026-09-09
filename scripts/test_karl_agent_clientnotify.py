#!/usr/bin/env python3
"""Tests RM3052 — les endpoints du panneau compte-rendu client (karl-agent).

Ce qu'on protège : le panneau touche un envoi d'email SORTANT vers un client. Les gardes
d'entrée sont donc la moitié du sujet — un `rm` vide, un client fantaisiste ou une sortie
de script illisible ne doivent jamais se transformer en email parti « au cas où ».

  1. sélection VIDE refusée (pas d'envoi implicite de « toute la file ») ;
  2. client et identifiants validés avant tout appel ;
  3. l'option protocole voyage telle quelle (défaut = option du projet) ;
  4. une sortie de script illisible ou un `ok:false` remontent en erreur, jamais en succès.

Lancer : python3 scripts/test_karl_agent_clientnotify.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def raises(fn, code=None):
    try:
        fn()
    except ka.ApiError as e:
        return code is None or e.code == code
    except Exception:  # noqa: BLE001
        return False
    return False


# ── 1. sélection ─────────────────────────────────────────────────────────────
check("sélection vide refusée (jamais « toute la file » par défaut)",
      raises(lambda: ka._cn_rm({"rm": []}), 400))
check("sélection absente refusée", raises(lambda: ka._cn_rm({}), 400))
check("identifiant non numérique refusé", raises(lambda: ka._cn_rm({"rm": ["3025; rm -rf"]}), 400))
check("sélection valide → un --rm par ticket, dans l'ordre",
      ka._cn_rm({"rm": [3025, "2948"]}) == ["--rm", "3025", "--rm", "2948"])
check("sélection bornée (200 max) sans planter",
      len(ka._cn_rm({"rm": list(range(1, 500))})) == 400)

# ── 2. client ────────────────────────────────────────────────────────────────
check("client valide accepté", ka._cn_client({"client": "calicote"}) == "calicote")
check("client vide refusé", raises(lambda: ka._cn_client({"client": ""}), 400))
check("client avec séparateur de chemin refusé",
      raises(lambda: ka._cn_client({"client": "../etc"}), 400))
check("client avec espace/injection refusé",
      raises(lambda: ka._cn_client({"client": "cali cote"}), 400))

# ── 3. protocole ─────────────────────────────────────────────────────────────
check("protocole absent → aucun drapeau (on suit l'option du projet)", ka._cn_proto({}) == [])
check("protocole false → --sans-protocole", ka._cn_proto({"protocole": False}) == ["--sans-protocole"])
check("protocole true → --avec-protocole", ka._cn_proto({"protocole": True}) == ["--avec-protocole"])

# ── 4. dialogue avec le script (aucun envoi réel) ────────────────────────────
class FakeRun:
    def __init__(self, stdout="", stderr="", rc=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, rc


calls = []


def fake_run(cmd, **kw):
    calls.append(cmd)
    return FakeRun(FAKE_OUT)


ka.subprocess.run = fake_run

FAKE_OUT = '{"ok": true, "total": 3, "clients": [{"client": "calicote", "count": 3}]}'
res = ka.op_client_notify_pending({"client": "calicote"})
check("pending : le script est appelé en --json", calls[-1][-1] == "--json")
check("pending : sous-commande et client transmis",
      calls[-1][-3:] == ["pending", "calicote", "--json"], str(calls[-1][-3:]))
check("pending : la donnée du script est rendue telle quelle", res["total"] == 3)
ka.op_client_notify_pending({})
check("pending sans client : aucun filtre passé", "--json" == calls[-1][-1] and "pending" == calls[-1][-2])

FAKE_OUT = '{"ok": true, "to": ["a@x.fr"], "subject": "S", "body": "B", "count": 1}'
prev = ka.op_client_notify_preview({"client": "calicote", "rm": [3025], "protocole": False})
check("preview : aperçu rendu (destinataires, sujet, corps)",
      prev["subject"] == "S" and prev["to"] == ["a@x.fr"])
check("preview : n'envoie pas — sous-commande `preview`, sans --yes",
      "preview" in calls[-1] and "--yes" not in calls[-1])
check("preview : le refus de protocole est transmis", "--sans-protocole" in calls[-1])

FAKE_OUT = '{"ok": true, "sent": 2, "to": ["a@x.fr"], "rm": [3025, 2948]}'
sent = ka.op_client_notify_send({"client": "calicote", "rm": [3025, 2948]})
check("send : confirmation explicite (--yes) posée par l'API, pas par le front",
      "--yes" in calls[-1] and "send" in calls[-1])
check("send : rend ce qui est parti et à qui", sent["sent"] == 2 and sent["to"] == ["a@x.fr"])

FAKE_OUT = '{"ok": true, "dismissed": 1, "rm": [3042]}'
dis = ka.op_client_notify_dismiss({"client": "calicote", "rm": [3042]})
check("dismiss : écarte la sélection, sans email", dis["dismissed"] == 1 and "send" not in calls[-1])

FAKE_OUT = '{"ok": false, "error": "aucun destinataire résolu"}'
check("échec du script → erreur 400 portant le message, jamais un faux succès",
      raises(lambda: ka.op_client_notify_send({"client": "calicote", "rm": [1]}), 400))
FAKE_OUT = "traceback bavard sans json"
check("sortie illisible → erreur 500 explicite (on n'invente pas un résultat)",
      raises(lambda: ka.op_client_notify_pending({}), 500))
FAKE_OUT = ""
check("sortie vide → erreur, pas un panneau silencieusement vide",
      raises(lambda: ka.op_client_notify_pending({}), 500))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
