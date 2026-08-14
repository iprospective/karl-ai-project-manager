#!/usr/bin/env python3
"""Tests RM2668 — karl-mail-fetch (relève IMAP + file de triage).

Unitaire, sans réseau ni vault : décodage des messages, détection des expéditeurs
machine, sujet [RM<id>] → réponse, idempotence par index, choix des dossiers,
non-destructivité du FETCH, écriture de la file hors git.

Lancer : python3 scripts/test_karl_mail_fetch.py
"""
import argparse
import email
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2668-"))
os.environ["KARL_AGENT_STATE_DIR"] = str(tmp / "state")

spec = importlib.util.spec_from_file_location("kmf", HERE / "karl-mail-fetch.py")
kmf = importlib.util.module_from_spec(spec)
sys.modules["kmf"] = kmf
spec.loader.exec_module(kmf)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def mail(frm="client@exemple.fr", subject="Souci sur le site", body="Bonjour,\nÇa plante.",
         extra_headers=(), mid="<abc@exemple.fr>", html=None):
    lines = [f"From: {frm}", "To: karl@iprospective.fr", f"Subject: {subject}",
             f"Message-ID: {mid}", "Date: Thu, 14 Aug 2026 09:12:00 +0200"]
    lines += [f"{k}: {v}" for k, v in extra_headers]
    if html is None:
        lines += ["Content-Type: text/plain; charset=utf-8", "", body]
        raw = "\n".join(lines)
    else:
        lines += ['Content-Type: multipart/alternative; boundary="B"', "",
                  "--B", "Content-Type: text/html; charset=utf-8", "", html, "--B--"]
        raw = "\n".join(lines)
    # message_from_bytes : le corps garde son encodage d'origine, donc as_bytes()
    # (utilisé par la boîte simulée) refonctionne sur de l'accentué.
    return email.message_from_bytes(raw.encode("utf-8"))


# ── décodage ────────────────────────────────────────────────────────────────
m = mail(subject="=?utf-8?B?Q2HDrndhIA==?= marche")
check("en-tête MIME décodé", "Ca" in kmf.dec(m.get("Subject")) or "î" in kmf.dec(m.get("Subject")))
check("en-tête absent → chaîne vide", kmf.dec(None) == "")

text, trunc = kmf.body_text(mail(body="ligne 1\nligne 2"), 4000)
check("corps texte lu", "ligne 2" in text and not trunc)
text, trunc = kmf.body_text(mail(body="0123456789"), 4)
check("corps tronqué signalé", text == "0123" and trunc)
text, _ = kmf.body_text(mail(html="<p>Bonjour <b>Karl</b></p><script>x=1</script>"), 4000)
check("html dégradé en texte", "Bonjour" in text and "Karl" in text and "script" not in text)

# ── expéditeurs machine ─────────────────────────────────────────────────────
def is_machine(msg, extra=()):
    return kmf.machine_reason(msg, kmf.sender_address(msg), list(extra))


check("humain accepté", not is_machine(mail()))
check("noreply écarté", bool(is_machine(mail(frm="no-reply@ovh.com"))))
check("mailer-daemon écarté", bool(is_machine(mail(frm="MAILER-DAEMON@srv.fr"))))
check("gitlab écarté", bool(is_machine(mail(frm="gitlab@gitlab.iprospective.fr"))))
check("liste de diffusion écartée",
      bool(is_machine(mail(extra_headers=[("List-Unsubscribe", "<https://x/u>")]))))
check("auto-submitted écarté",
      bool(is_machine(mail(extra_headers=[("Auto-Submitted", "auto-replied")]))))
check("auto-submitted: no reste humain",
      not is_machine(mail(extra_headers=[("Auto-Submitted", "no")])))
check("motif supplémentaire honoré", bool(is_machine(mail(frm="compta@banque.fr"),
                                                     extra=[r"@banque\.fr$"])))
check("motif invalide non fatal", not is_machine(mail(), extra=["(("]))

# ── entrée de file ──────────────────────────────────────────────────────────
e = kmf.build_entry(mail(), "INBOX", "42", "karl@iprospective.fr", 4000)
check("entrée : expéditeur normalisé", e["from"] == "client@exemple.fr")
check("entrée : nouveau par défaut", e["kind"] == "new" and e["rm_id"] is None)
check("entrée : statut queued", e["status"] == "queued")
e2 = kmf.build_entry(mail(subject="Re: [RM2668] relance"), "INBOX", "43",
                     "karl@iprospective.fr", 4000)
check("sujet [RM<id>] → réponse", e2["kind"] == "reply" and e2["rm_id"] == 2668)
check("clé stable sur le Message-ID", e["key"] == kmf.msg_key("<abc@exemple.fr>"))
check("clés distinctes", kmf.msg_key("<a@x>") != kmf.msg_key("<b@x>"))

att = kmf.build_entry(mail(extra_headers=[("Content-Disposition", 'attachment; filename="devis.pdf"')]),
                      "INBOX", "44", "karl@iprospective.fr", 4000)
check("pièce jointe listée, non téléchargée",
      att["attachments"] and att["attachments"][0]["name"] == "devis.pdf"
      and "content" not in att["attachments"][0])

# ── dossiers ────────────────────────────────────────────────────────────────
check("virtual.* exclu", kmf.excluded("virtual.Flagged", kmf.EXCLUDE_FOLDERS_DEFAULT))
check("Sent exclu", kmf.excluded("Sent", kmf.EXCLUDE_FOLDERS_DEFAULT))
check("INBOX non exclue", not kmf.excluded("INBOX", kmf.EXCLUDE_FOLDERS_DEFAULT))
check("dossier client non exclu", not kmf.excluded("clients", kmf.EXCLUDE_FOLDERS_DEFAULT))


class FakeIMAP:
    """Boîte simulée : LIST/SELECT/UID SEARCH/UID FETCH, et journal des commandes."""

    def __init__(self, folders, messages):
        self.folders, self.messages = folders, messages
        self.calls, self.selected = [], None

    def list(self):
        return "OK", [f'(\\HasNoChildren) "." "{f}"'.encode() for f in self.folders]

    def select(self, folder, readonly=False):
        self.selected = folder.strip('"')
        self.calls.append(("select", self.selected, readonly))
        return ("OK", [b"1"]) if self.selected in self.folders else ("NO", [b""])

    def uid(self, cmd, *rest):
        self.calls.append((cmd,) + tuple(str(r) for r in rest if r is not None))
        if cmd == "SEARCH":
            uids = [str(i).encode() for i, (f, _) in enumerate(self.messages, 1)
                    if f == self.selected]
            return "OK", [b" ".join(uids)]
        uid = int(rest[0])
        raw = self.messages[uid - 1][1].as_bytes()
        return "OK", [(b"1 (BODY[] {%d}" % len(raw), raw)]

    def logout(self):
        self.calls.append(("logout",))


msgs = [
    ("INBOX", mail(mid="<1@x>", frm="client@abatik.fr", subject="Panne de caisse")),
    ("INBOX", mail(mid="<2@x>", frm="no-reply@gitlab.iprospective.fr", subject="Pipeline failed")),
    ("INBOX", mail(mid="<3@x>", frm="karl@iprospective.fr", subject="[RM2666] point")),
    ("clients", mail(mid="<4@x>", frm="contact@pisceen.fr", subject="Devis")),
]
fake = FakeIMAP(["INBOX", "clients", "Sent", "virtual.All"], msgs)
args = argparse.Namespace(days=30, limit=0, body_chars=4000, unseen_only=False,
                          mark_seen=False)
index = {}
res = kmf.collect(fake, ["clients", "INBOX"], args, "karl@iprospective.fr", index, [])
st = res["stats"]
check("relève : 2 humains retenus", st["new"] == 2)
check("relève : robot écarté", st["machine"] == 1)
check("relève : envoi de karl écarté", st["self"] == 1)
check("relève : dossier de confiance d'abord",
      [e["folder"] for e in res["entries"]][0] == "clients")
check("SELECT en lecture seule", all(c[2] is True for c in fake.calls if c[0] == "select"))
fetches = [" ".join(c) for c in fake.calls if c[0] == "FETCH"]
check("FETCH non destructif (PEEK)",
      fetches and all("BODY.PEEK[]" in c for c in fetches))
check("aucun STORE/DELETE/MOVE",
      not any(c[0] in ("STORE", "COPY", "MOVE", "EXPUNGE") for c in fake.calls))

# — idempotence : deuxième passe sur le même index —
res2 = kmf.collect(fake, ["clients", "INBOX"], args, "karl@iprospective.fr", index, [])
check("2e relève : aucun doublon", res2["stats"]["new"] == 0)
check("2e relève : tout est connu", res2["stats"]["known"] == len(msgs))

# — écriture de la file, hors repo git —
kmf.write_queue(res["entries"])
kmf.save_index(index)
q = kmf.read_queue()
check("file relue", len(q) == 2)
check("file triée par date décroissante",
      [x["key"] for x in q] == sorted([x["key"] for x in q],
                                      key=lambda k: next(e["date"] for e in q if e["key"] == k),
                                      reverse=True))
check("file hors du repo PM", str(kmf.queue_dir()).startswith(str(tmp)))
check("index persisté", json.loads(kmf.index_file().read_text())  # noqa: E501
      .get(kmf.msg_key("<2@x>"), {}).get("status") == "machine")
check("droits restreints sur la file", oct(kmf.queue_dir().stat().st_mode)[-3:] == "700")
check("droits restreints sur une entrée",
      oct(next(kmf.queue_dir().glob("*.json")).stat().st_mode)[-3:] == "600")

# — index illisible : on repart à vide, sans planter —
kmf.index_file().write_text("{ pas du json")
check("index corrompu → vide, non fatal", kmf.load_index() == {})

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
