#!/usr/bin/env python3
"""Tests RM3052 — le CHEMIN RÉEL du panneau compte-rendu client (pm-client-notify).

Pourquoi ce fichier existe : les tests de `pm_client_notify` couvrent la logique pure,
et c'est précisément ce qui a laissé passer le bug RM3026 (la donnée existait, le
lecteur ne l'exposait pas). Ici on part de VRAIES fiches sur disque et on vérifie ce que
le panneau recevra : qui est en file, groupé par client, restreint aux cases cochées.

Ce qui est protégé :
  1. le balayage ne retient QUE les tickets en file (ni envoyés, ni écartés, ni jamais mis
     en file) — et le pré-filtre `client_notify:` ne doit pas faire rater un ticket ;
  2. la sélection `--rm` traverse les projets d'un même client (une case cochée dans deux
     projets = UN compte-rendu) ;
  3. l'agrégat par client compte juste et n'invente pas de destinataire : union des
     contacts des projets ACTIFS, dédoublonnée, refs inconnues signalées ;
  4. le rendu suit le périmètre : projet ⇒ récap projet, client ⇒ compte-rendu client.

Lancer : python3 scripts/test_pm_client_notify_cli.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("pm_client_notify_cli", HERE / "pm-client-notify.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ── un mini-arbre PM sur disque ──────────────────────────────────────────────
ROOT = pathlib.Path(tempfile.mkdtemp(prefix="rm3052-cli-"))


def task(project_dir, rm, title, notify_block, criteria=("Le prix s'affiche",), protocol="1. Ouvrir"):
    """Une fiche de ticket réaliste : frontmatter + critères en checklist + protocole."""
    tasks = project_dir / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    fm = [f"redmine_id: {rm}", f"title: '{title}'", "status: en_mep"]
    if protocol:
        fm.append(f"test_protocol: |-\n  {protocol}")
    if notify_block:
        fm.append(notify_block)
    body = "## Critères d'acceptation\n\n" + "".join(f"- [x] {c}\n" for c in criteria)
    (tasks / f"RM{rm}_x.md").write_text("---\n" + "\n".join(fm) + "\n---\n" + body, encoding="utf-8")


QUEUED = "client_notify:\n  queued_at: '2026-09-08T10:00'\n  sent_at: null"
SENT = "client_notify:\n  queued_at: '2026-09-08T10:00'\n  sent_at: '2026-09-08T12:00'"
DISMISSED = ("client_notify:\n  queued_at: '2026-09-08T10:00'\n  sent_at: null"
             "\n  dismissed_at: '2026-09-08T13:00'")

P = {}
for ent, proj in (("calicote", "prestashop"), ("calicote", "prestasync"), ("abatik", "site")):
    P[(ent, proj)] = ROOT / ent / proj
    P[(ent, proj)].mkdir(parents=True)
    (P[(ent, proj)] / "meta.yml").write_text("name: x\n", encoding="utf-8")

task(P[("calicote", "prestashop")], 3025, "Paliers", QUEUED)
task(P[("calicote", "prestashop")], 2948, "Promotions", QUEUED)
task(P[("calicote", "prestashop")], 1111, "Déjà notifié", SENT)
task(P[("calicote", "prestashop")], 2222, "Écarté", DISMISSED)
task(P[("calicote", "prestashop")], 3333, "Jamais en file", None)
task(P[("calicote", "prestasync")], 3042, "Picking lots", QUEUED)
task(P[("abatik", "site")], 9001, "Autre client", QUEUED)

META = {
    ("calicote", "prestashop"): {"name": "Site PrestaShop",
                                 "notif_client_mep": {"actif": True, "contacts": ["sandrine", "ipro"]}},
    ("calicote", "prestasync"): {"name": "Synchro Dolibarr",
                                 "notif_client_mep": {"actif": True, "contacts": ["ipro", "inconnu"],
                                                      "protocole": False}},
    ("abatik", "site"): {"name": "Site Abatik", "notif_client_mep": {"actif": False, "contacts": ["sandrine"]}},
}
ANN = ROOT / "contacts"
ANN.mkdir()
(ANN / "sandrine.yml").write_text("ref: sandrine\nfirst_name: Sandrine\nemails:\n- s@calicote.com\n", encoding="utf-8")
(ANN / "ipro.yml").write_text("ref: ipro\nfirst_name: Mathieu\nemails:\n- m@ipro.fr\n- contact@ipro.fr\n", encoding="utf-8")


class FakeCfg:
    """Le contrat minimal dont dépendent les fonctions du panneau : parcourir les projets,
    lire un meta projet/client, situer l'annuaire."""
    def iter_projects(self, entity=None):
        for (e, p), d in sorted(P.items()):
            if entity is None or e == entity:
                yield e, p, d

    def project_meta(self, entity, project):
        return META.get((entity, project), {})

    def client_meta(self, entity):
        return {"name": "Calicote"} if entity == "calicote" else {}

    def path(self, key, **kw):
        if key == "contacts_dir":
            return ANN
        raise KeyError(key)


cfg = FakeCfg()

# ── 1. balayage : la file, rien que la file ──────────────────────────────────
rows = cli._scan_pending(cfg)
ids = sorted(t["id"] for r in rows for t in r["tickets"])
check("seuls les tickets EN FILE remontent (envoyé/écarté/jamais en file exclus)",
      ids == [2948, 3025, 3042, 9001], str(ids))
check("un projet sans ticket en file n'apparaît pas",
      all(r["tickets"] for r in rows))
ps = cli._scan_pending(cfg, "calicote", "prestashop")
check("périmètre projet : seul ce projet",
      len(ps) == 1 and sorted(t["id"] for t in ps[0]["tickets"]) == [2948, 3025])
check("les critères d'acceptation sont lus dans le CORPS de la fiche",
      ps[0]["tickets"][0]["criteria"] == ["Le prix s'affiche"], str(ps[0]["tickets"][0]))
check("le protocole suit l'option du projet (actif ici)",
      ps[0]["tickets"][0]["protocol"].startswith("1. Ouvrir"))
sync = cli._scan_pending(cfg, "calicote", "prestasync")
check("projet avec `protocole: false` => protocole ABSENT de l'email",
      sync[0]["tickets"][0]["protocol"] == "")
check("--sans-protocole force l'exclusion malgré l'option projet",
      cli._scan_pending(cfg, "calicote", "prestashop", None, False)[0]["tickets"][0]["protocol"] == "")

# ── 2. sélection inter-projets (les cases cochées) ───────────────────────────
sel = cli._scan_pending(cfg, "calicote", None, ["3025", "3042"])
check("une sélection traverse les projets du MÊME client",
      sorted(r["project"] for r in sel) == ["prestashop", "prestasync"]
      and sorted(t["id"] for r in sel for t in r["tickets"]) == [3025, 3042])
check("un id hors file est ignoré, il n'invente pas de ticket",
      not cli._scan_pending(cfg, "calicote", None, ["1111", "999999"]))

# ── 3. agrégat par client + destinataires ────────────────────────────────────
emails, orphans = cli._emails_for(cfg, cli._scan_pending(cfg, "calicote"))
check("union des contacts des projets, dédoublonnée, ordre conservé",
      emails == ["s@calicote.com", "m@ipro.fr", "contact@ipro.fr"], str(emails))
check("ref d'annuaire inconnue signalée, jamais tue", orphans == ["inconnu"])
em_off, _ = cli._emails_for(cfg, cli._scan_pending(cfg, "abatik"))
check("projet dont l'option est INACTIVE n'apporte aucun destinataire", em_off == [])

# ── 4. rendu selon le périmètre ──────────────────────────────────────────────
_, subj_p, body_p, _, _ = cli._render_selection(cfg, "calicote", "prestashop", None, None)
check("périmètre projet => sujet au nom du PROJET (récap projet, inchangé)",
      subj_p == "Site PrestaShop — 2 évolutions mises en ligne", subj_p)
_, subj_c, body_c, em_c, _ = cli._render_selection(cfg, "calicote", None, None, None)
check("périmètre client => sujet au nom du CLIENT, tous projets comptés",
      subj_c == "Calicote — 3 évolutions mises en ligne", subj_c)
check("corps client multi-projets : un en-tête par projet",
      "== Site PrestaShop ==" in body_c and "== Synchro Dolibarr ==" in body_c)
_, _, body_1, _, _ = cli._render_selection(cfg, "calicote", None, ["3025"], None)
check("sélection d'un seul projet côté client => pas d'en-tête de projet",
      "==" not in body_1 and "#3025" in body_1)
check("l'aperçu ne modifie AUCUNE fiche (aucun sent_at posé)",
      "sent_at: null" in (P[("calicote", "prestashop")] / "tasks" / "RM3025_x.md").read_text(encoding="utf-8"))

# ── 5. dismiss : écarte les cochés, laisse les autres ────────────────────────
cli._mark_all_dismissed([t for r in cli._scan_pending(cfg, "calicote", None, ["3042"]) for t in r["tickets"]],
                        "2026-09-09T09:00")
after = sorted(t["id"] for r in cli._scan_pending(cfg, "calicote") for t in r["tickets"])
check("le ticket écarté sort de la file, les autres restent", after == [2948, 3025], str(after))
check("écarter n'envoie rien : pas de sent_at posé",
      "sent_at: null" in (P[("calicote", "prestasync")] / "tasks" / "RM3042_x.md").read_text(encoding="utf-8"))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
