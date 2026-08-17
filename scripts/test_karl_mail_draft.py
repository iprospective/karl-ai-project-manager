#!/usr/bin/env python3
"""Tests RM2670 — rédaction assistée et création à la validation.

Unitaire, sans réseau ni appel LLM (claude et pm-task-add sont simulés) : validation
stricte de la proposition, refus d'un projet inventé, liste de projets restreinte au
client routé, création (argv, description, Message-ID journalisé), note sur un fil
existant, et le fait que rien ne se crée sans validation.

Lancer : python3 scripts/test_karl_mail_draft.py
"""
import argparse
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2670-"))
os.environ["KARL_AGENT_STATE_DIR"] = str(tmp / "state")

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kmd", HERE / "karl-mail-draft.py")
D = importlib.util.module_from_spec(spec)
sys.modules["kmd"] = D
spec.loader.exec_module(D)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


TYPES = ["feature", "bugfix", "infrastructure", "assistance", "autre"]
PROJECTS = ["calyclay/dolibarr", "calyclay/infra", "abatik/site"]


# ── validation de la proposition ─────────────────────────────────────────────
v = D.validate({"actionable": True, "title": "Panne de caisse", "type": "bugfix",
                "priority": "high", "project": "calyclay/dolibarr",
                "description": "Le TPE ne répond plus.", "confidence": 0.8},
               TYPES, PROJECTS)
check("proposition conforme conservée",
      (v["title"], v["type"], v["priority"], v["project"]) ==
      ("Panne de caisse", "bugfix", "high", "calyclay/dolibarr"))
check("confiance normalisée", v["confidence"] == 0.8 and not v["warnings"])

v = D.validate({"title": "X", "project": "calyclay/inexistant"}, TYPES, PROJECTS)
check("projet inventé écarté (jamais corrigé en douce)", v["project"] is None)
check("projet inventé signalé", any("hors liste" in w for w in v["warnings"]))

v = D.validate({"title": "X", "type": "epic", "priority": "critique"}, TYPES, PROJECTS)
check("type hors catalogue → autre", v["type"] == "autre")
check("priorité hors catalogue → normal", v["priority"] == "normal")
check("deux écarts signalés", len(v["warnings"]) == 2)

v = D.validate({"title": "  Un titre\nsur deux lignes  " + "x" * 200}, TYPES, PROJECTS)
check("titre borné et sur une ligne", "\n" not in v["title"] and len(v["title"]) == 120)
v = D.validate({"confidence": "beaucoup"}, TYPES, PROJECTS)
check("confiance illisible → 0", v["confidence"] == 0.0)
v = D.validate({"actionable": False, "title": "Remerciement"}, TYPES, PROJECTS)
check("non actionnable transmis tel quel", v["actionable"] is False)


# ── liste de projets proposés ────────────────────────────────────────────────
class FakeCfg:
    def iter_projects(self, entity=None):
        for c, p in [("calyclay", "dolibarr"), ("calyclay", "infra"), ("abatik", "site")]:
            if entity is None or c == entity:
                yield c, p, None


cfg = FakeCfg()
check("client routé → seuls ses projets sont proposables",
      D.candidate_projects(cfg, {"routing": {"client": "calyclay"}})
      == ["calyclay/dolibarr", "calyclay/infra"])
check("sans routage → tout le catalogue",
      len(D.candidate_projects(cfg, {})) == 3)
check("client routé inconnu → repli sur le catalogue",
      len(D.candidate_projects(cfg, {"routing": {"client": "fantome"}})) == 3)


# ── corps envoyé au modèle ───────────────────────────────────────────────────
entry = {"key": "abc123", "from": "client@x.fr", "from_name": "Client",
         "date": "2026-08-17T09:00", "subject": "Souci", "folder": "INBOX.Clients",
         "body": "A" * 3000, "message_id": "<m1@x.fr>", "rm_id": None}
short = D.build_payload(entry, argparse.Namespace(full_body=False, body_chars=500))
full = D.build_payload(entry, argparse.Namespace(full_body=True, body_chars=500))
check("corps tronqué par défaut", short.count("A") == 500)
check("corps complet sur demande", full.count("A") == 3000)
check("en-têtes toujours transmis", "Souci" in short and "client@x.fr" in short)


# ── création : argv, description, traçabilité ────────────────────────────────
mail = D.kmf()
mail.queue_dir().mkdir(parents=True, exist_ok=True)
entry["draft"] = {"title": "Souci de caisse", "type": "bugfix", "priority": "high",
                  "project": "calyclay/dolibarr", "description": "Le TPE ne répond plus.",
                  "model": "claude-opus-5", "confidence": 0.8, "warnings": []}
D.write_entry(mail, entry)

calls = []


class FakeProc:
    returncode, stdout, stderr = 0, "9999\n", ""


def fake_run(cmd, **kw):
    calls.append(cmd)
    return FakeProc()


D.subprocess.run = fake_run


def args(**kw):
    base = dict(title=None, type=None, priority=None, project=None, note_on=None,
                dry_run=False, reason=None)
    base.update(kw)
    return argparse.Namespace(**base)


repo = HERE.parent
D.cmd_create(cfg, mail, entry, args(), repo)
argv = calls[-1]
check("création : pm-task-add appelé", any("pm-task-add.py" in str(x) for x in argv))
check("création : porcelain (id capturé, jamais prédit)", "--porcelain" in argv)
check("création : titre, type, priorité, projet transmis",
      "Souci de caisse" in argv and "bugfix" in argv and "high" in argv
      and "calyclay/dolibarr" in argv)
desc_path = pathlib.Path(argv[argv.index("--description-file") + 1])
# le fichier est supprimé après création : on relit la trace dans l'entrée
check("création : id repris de la sortie porcelain", entry.get("created_rm") == 9999)
check("création : issue marquée dans la file", entry.get("outcome") == "ticket")
check("création : fichier de description nettoyé", not desc_path.exists())

# une entrée déjà créée ne peut pas l'être deux fois
try:
    D.cmd_create(cfg, mail, entry, args(), repo)
    twice = False
except SystemExit:
    twice = True
check("création : pas de doublon sur une entrée déjà traitée", twice)

# description : contexte + traçabilité de l'email d'origine
entry2 = dict(entry, key="def456", created_rm=None, outcome=None,
              message_id="<m2@x.fr>")
D.write_entry(mail, entry2)
D.cmd_create(cfg, mail, entry2, args(project="abatik/site", dry_run=False), repo)
argv = calls[-1]
check("création : projet imposé en ligne de commande prime",
      "abatik/site" in argv)

# ── note sur un fil existant : jamais un nouveau ticket ──────────────────────
reply = {"key": "ghi789", "from": "client@x.fr", "from_name": "Client",
         "date": "2026-08-17T10:00", "subject": "Re: [RM2661] suite",
         "body": "C'est en place.", "message_id": "<m3@x.fr>", "rm_id": 2661}
D.write_entry(mail, reply)
D.cmd_create(cfg, mail, reply, args(), repo)
argv = calls[-1]
check("réponse : note posée, pas de ticket",
      any("pm-task-comment.py" in str(x) for x in argv)
      and not any("pm-task-add.py" in str(x) for x in argv))
check("réponse : note sur le bon ticket", "2661" in argv)
note = argv[argv.index("--note") + 1]
check("réponse : la note porte le Message-ID", "<m3@x.fr>" in note)
check("réponse : la note cite l'expéditeur et le sujet",
      "client@x.fr" in note and "Re: [RM2661] suite" in note)
check("réponse : entrée marquée comme note", reply.get("outcome") == "note")

# --note-on : rattachement humain d'un fil qui a perdu son marqueur
orphan = {"key": "jkl012", "from": "client@x.fr", "from_name": "Client",
          "date": "2026-08-17T11:00", "subject": "suite sans marqueur",
          "body": "et la clé ?", "message_id": "<m4@x.fr>", "rm_id": None}
D.write_entry(mail, orphan)
D.cmd_create(cfg, mail, orphan, args(note_on="2661"), repo)
check("--note-on : note posée sur le ticket désigné",
      any("pm-task-comment.py" in str(x) for x in calls[-1]) and "2661" in calls[-1])

# ── rien ne se crée sans validation ──────────────────────────────────────────
before = len(calls)
pending = {"key": "mno345", "from": "a@b.fr", "subject": "demande", "body": "…",
           "message_id": "<m5@b.fr>", "rm_id": None,
           "draft": {"title": "T", "project": "abatik/site", "type": "autre",
                     "priority": "normal", "description": "d"}}
D.write_entry(mail, pending)
D.cmd_create(cfg, mail, pending, args(dry_run=True), repo)
check("dry-run : aucun appel de création", len(calls) == before)
check("dry-run : entrée non marquée", pending.get("created_rm") is None)

D.cmd_dismiss(mail, pending, args(reason="pas une demande"))
check("écarté : motif conservé", pending["dismissed"]["reason"] == "pas une demande")
check("écarté : statut lisible", D.status_of(pending) == "écarté")

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
