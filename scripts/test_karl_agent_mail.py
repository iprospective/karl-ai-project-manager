#!/usr/bin/env python3
"""Tests RM2671 — panneau « emails » côté serveur.

Unitaire, sans réseau : forme de /mail/queue (le corps d'un email ne sort qu'au
détail), masquage des emails traités, et surtout les gardes des routes d'action —
clé de file, cible de routage et allowlist de scripts.

Lancer : python3 scripts/test_karl_agent_mail.py
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2671-"))
os.environ["KARL_AGENT_STATE_DIR"] = str(tmp)

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


q = tmp / "mail" / "queue"
q.mkdir(parents=True)
(q / "aaa111.json").write_text(json.dumps({
    "key": "aaa111", "from": "client@x.fr", "from_name": "Client", "subject": "Panne",
    "date": "2026-08-17T09:00", "folder": "INBOX.Clients", "body": "corps du client",
    "attachments": [{"name": "devis.pdf", "type": "application/pdf", "size": 12}],
    "routing": {"client": "calyclay", "project": None, "confidence": 0.8,
                "source": "contacts"},
}), encoding="utf-8")
(q / "bbb222.json").write_text(json.dumps({
    "key": "bbb222", "from": "c@d.fr", "subject": "Suite", "date": "2026-08-16",
    "body": "déjà traité", "created_rm": 2710, "outcome": "ticket",
}), encoding="utf-8")
(q / "ccc333.json").write_text(json.dumps({
    "key": "ccc333", "from": "e@f.fr", "subject": "Merci", "date": "2026-08-15",
    "body": "écarté", "dismissed": {"reason": "accusé de réception"},
}), encoding="utf-8")

# ── forme de la file ────────────────────────────────────────────────────────
r = ka.op_mail_queue({})
keys = [e["key"] for e in r["emails"]]
check("file : seuls les emails à traiter par défaut", keys == ["aaa111"])
check("file : compteur des restants", r["pending"] == 1)
check("file : le corps ne sort PAS en liste (courrier client)",
      all("body" not in e for e in r["emails"]))
check("file : pièces jointes comptées, pas détaillées",
      r["emails"][0]["attachments"] == 1)
check("file : routage transmis tel quel",
      r["emails"][0]["routing"]["source"] == "contacts")

d = ka.op_mail_queue({"key": "aaa111"})
detail = next(e for e in d["emails"] if e["key"] == "aaa111")
check("détail : corps présent sur demande explicite", detail.get("body") == "corps du client")
check("détail : pièces jointes listées", detail["attachment_list"][0]["name"] == "devis.pdf")

r = ka.op_mail_queue({"done": "1"})
states = {e["key"]: e["state"] for e in r["emails"]}
check("traités visibles sur demande", set(states) == {"aaa111", "bbb222", "ccc333"})
check("état « créé » reconnu", states["bbb222"] == "créé")
check("état « écarté » reconnu", states["ccc333"] == "écarté")
check("tri par date décroissante",
      [e["key"] for e in r["emails"]] == ["aaa111", "bbb222", "ccc333"])


# ── gardes des actions ──────────────────────────────────────────────────────
def refuses(fn, payload):
    try:
        fn(payload)
        return False
    except ka.ApiError:
        return True
    except Exception:            # noqa: BLE001 — un autre échec n'est pas un refus
        return False


for bad in ("../../etc/passwd", "ZZZ", "", "aa", "a" * 40, "aaa111; rm -rf /"):
    check(f"clé de file refusée : {bad[:18] or '(vide)'}",
          refuses(ka.op_mail_dismiss, {"key": bad}))

for bad in ("client; rm -rf /", "CLIENT/Projet!", "a" * 200, "", "../x"):
    check(f"cible de routage refusée : {bad[:18] or '(vide)'}",
          refuses(ka.op_mail_route_set, {"key": "aaa111", "to": bad}))

check("script hors allowlist refusé",
      refuses(lambda p: ka._mail_script("evil.py", []), {}))
check("script du pipeline accepté (allowlist)",
      ka._mail_script.__doc__ and "allowlist" in ka._mail_script.__doc__)

for bad in ({"priority": "URGENT!!"}, {"note_on": "abc"}, {"project": "x" * 200}):
    payload = dict({"key": "aaa111"}, **bad)
    check(f"argument de création refusé : {list(bad)[0]}",
          refuses(ka.op_mail_create, payload))

# ── argv réellement construit ───────────────────────────────────────────────
seen = {}


def spy(script, args, timeout=300):
    seen["script"], seen["args"] = script, args
    return {"ok": True, "rc": 0, "stdout": "", "stderr": ""}


ka._mail_script = spy

# --mark-seen n'est JAMAIS exposé : marquer lu agit sur une boîte de prod, ça reste
# un geste CLI explicite. Même en le glissant dans la charge utile.
ka.op_mail_fetch({"mark_seen": True, "days": 7})
check("relève : --mark-seen jamais transmis, même demandé",
      "--mark-seen" not in seen["args"])
check("relève : fenêtre transmise", seen["args"] == ["--days", "7"])

ka.op_mail_draft({"key": "aaa111", "full_body": True})
check("rédaction : corps entier transmis quand demandé",
      "--full-body" in seen["args"] and seen["script"] == "karl-mail-draft.py")
ka.op_mail_draft({"key": "aaa111"})
check("rédaction : corps entier NON transmis par défaut",
      "--full-body" not in seen["args"])

ka.op_mail_create({"key": "aaa111", "project": "calyclay/infra", "priority": "high"})
check("création : corrections humaines transmises",
      "--project" in seen["args"] and "calyclay/infra" in seen["args"]
      and "high" in seen["args"])
ka.op_mail_create({"key": "aaa111", "note_on": "2661"})
check("création : rattachement à un fil transmis",
      "--note-on" in seen["args"] and "2661" in seen["args"])

# — RM3319 : les rejets ouverts du fil remontent avec la file (boîte aux lettres 📬) —
os.environ["PM_NOTIFY_DIR"] = str(tmp / "notify")
sys.path.insert(0, str(HERE))
import pm_notify  # noqa: E402
check("rejets : aucun tant que le fil est vide", ka.op_mail_queue({}).get("bounces") == [])
n = pm_notify.add("mail", "critical", "Mail de karl rejeté : x@y — 5.1.1", job="mail-bounce", ref="<o@x>", rm=1839)
pm_notify.add("mail", "info", "autre chose venue du courrier", job="autre")
b = ka.op_mail_queue({}).get("bounces")
check("rejets : l'entrée « mail-bounce » ouverte remonte, seule",
      len(b) == 1 and b[0]["level"] == "critical" and b[0]["rm"] == 1839 and "rejeté" in b[0]["msg"])
pm_notify.mark([n["id"]], "traite")
check("rejets : marquée traitée dans le fil → l'alerte s'éteint", ka.op_mail_queue({}).get("bounces") == [])

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
