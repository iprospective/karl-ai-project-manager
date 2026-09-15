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


PROTO_MD = "| Cas | Attendu |\n|---|---|\n| A1 | Le prix barré s'affiche |\n\n1. Ouvrir la fiche"


def task(project_dir, rm, title, notify_block, criteria=("Le prix s'affiche",), protocol=PROTO_MD):
    """Une fiche de ticket réaliste : frontmatter + critères en checklist + protocole."""
    tasks = project_dir / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    fm = [f"redmine_id: {rm}", f"title: '{title}'", "status: en_mep"]
    if protocol:   # bloc YAML littéral : CHAQUE ligne indentée, sinon le frontmatter est cassé
        fm.append("test_protocol: |-\n" + "\n".join("  " + ln for ln in protocol.split("\n")))
    if notify_block:
        fm.append(notify_block)
    body = "## Critères d'acceptation\n\n" + "".join(f"- [x] {c}\n" for c in criteria)
    (tasks / f"RM{rm}_x.md").write_text("---\n" + "\n".join(fm) + "\n---\n" + body, encoding="utf-8")


QUEUED = "client_notify:\n  queued_at: '2026-09-08T10:00'\n  sent_at: null"
SENT = "client_notify:\n  queued_at: '2026-09-08T10:00'\n  sent_at: '2026-09-08T12:00'"
DISMISSED = ("client_notify:\n  queued_at: '2026-09-08T10:00'\n  sent_at: null"
             "\n  dismissed_at: '2026-09-08T13:00'")

P = {}
for ent, proj in (("clienta", "prestashop"), ("clienta", "prestasync"), ("cliente", "site")):
    P[(ent, proj)] = ROOT / ent / proj
    P[(ent, proj)].mkdir(parents=True)
    (P[(ent, proj)] / "meta.yml").write_text("name: x\n", encoding="utf-8")

task(P[("clienta", "prestashop")], 3025, "Paliers", QUEUED)
task(P[("clienta", "prestashop")], 2948, "Promotions", QUEUED)
task(P[("clienta", "prestashop")], 1111, "Déjà notifié", SENT)
task(P[("clienta", "prestashop")], 2222, "Écarté", DISMISSED)
task(P[("clienta", "prestashop")], 3333, "Jamais en file", None)
task(P[("clienta", "prestasync")], 3042, "Picking lots", QUEUED)
task(P[("cliente", "site")], 9001, "Autre client", QUEUED)

META = {
    ("clienta", "prestashop"): {"name": "Site PrestaShop",
                                 "notif_client_mep": {"actif": True, "contacts": ["alice", "ipro"]}},
    ("clienta", "prestasync"): {"name": "Synchro Dolibarr",
                                 "notif_client_mep": {"actif": True, "contacts": ["ipro", "inconnu"],
                                                      "protocole": False}},
    ("cliente", "site"): {"name": "Site Cliente", "notif_client_mep": {"actif": False, "contacts": ["alice"]}},
}
ANN = ROOT / "contacts"
ANN.mkdir()
(ANN / "alice.yml").write_text("ref: alice\nfirst_name: Alice\nemails:\n- s@clienta.example\n", encoding="utf-8")
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
        return {"name": "Clienta"} if entity == "clienta" else {}

    def path(self, key, **kw):
        if key == "contacts_dir":
            return ANN
        raise KeyError(key)


cfg = FakeCfg()

# Le dossier `tasks/` contient aussi les FRÈRES d'une fiche : `RM…_x.log.md`, `RM…_x.think.md`.
# Ils matchent `RM*.md`. Un journal qui PARLE de `client_notify:` (ce qui arrive : les logs de ce
# ticket-ci en parlent) franchissait le pré-filtre et se présentait comme un ticket sans statut.
# Incident réel constaté le 2026-09-09 sur `queue` : RM3025 apparaissait à la fois « refusé
# (statut ?) » et « à mettre en file ».
(P[("clienta", "prestashop")] / "tasks" / "RM3025_x.log.md").write_text(
    "# Journal\n\nOn a posé le bloc client_notify: sur la fiche.\n", encoding="utf-8")
(P[("clienta", "prestashop")] / "tasks" / "RM3025_x.think.md").write_text(
    "---\nrm: 3025\n---\nclient_notify: à surveiller\n", encoding="utf-8")

# ── 1. balayage : la file, rien que la file ──────────────────────────────────
rows = cli._scan_pending(cfg)
ids = sorted(t["id"] for r in rows for t in r["tickets"])
check("seuls les tickets EN FILE remontent (envoyé/écarté/jamais en file exclus)",
      ids == [2948, 3025, 3042, 9001], str(ids))
check("un projet sans ticket en file n'apparaît pas",
      all(r["tickets"] for r in rows))
check("un .log.md / .think.md n'est JAMAIS pris pour un ticket, même s'il cite client_notify",
      [t["id"] for r in rows for t in r["tickets"]].count(3025) == 1)
check("…et `_find_tickets` non plus (sinon un même ticket est refusé ET traité)",
      len(cli._find_tickets(cfg, "clienta", "prestashop", ["3025"])) == 1)
ps = cli._scan_pending(cfg, "clienta", "prestashop")
check("périmètre projet : seul ce projet",
      len(ps) == 1 and sorted(t["id"] for t in ps[0]["tickets"]) == [2948, 3025])
check("les critères d'acceptation sont lus dans le CORPS de la fiche",
      ps[0]["tickets"][0]["criteria"] == ["Le prix s'affiche"], str(ps[0]["tickets"][0]))
check("le protocole suit l'option du projet (actif ici)",
      "| Cas | Attendu |" in ps[0]["tickets"][0]["protocol"])
sync = cli._scan_pending(cfg, "clienta", "prestasync")
check("projet avec `protocole: false` => protocole ABSENT de l'email",
      sync[0]["tickets"][0]["protocol"] == "")
check("--sans-protocole force l'exclusion malgré l'option projet",
      cli._scan_pending(cfg, "clienta", "prestashop", None, False)[0]["tickets"][0]["protocol"] == "")

# ── 2. sélection inter-projets (les cases cochées) ───────────────────────────
sel = cli._scan_pending(cfg, "clienta", None, ["3025", "3042"])
check("une sélection traverse les projets du MÊME client",
      sorted(r["project"] for r in sel) == ["prestashop", "prestasync"]
      and sorted(t["id"] for r in sel for t in r["tickets"]) == [3025, 3042])
check("un id hors file est ignoré, il n'invente pas de ticket",
      not cli._scan_pending(cfg, "clienta", None, ["1111", "999999"]))

# ── 3. agrégat par client + destinataires ────────────────────────────────────
emails, orphans = cli._emails_for(cfg, cli._scan_pending(cfg, "clienta"))
check("union des contacts des projets, dédoublonnée, ordre conservé",
      emails == ["s@clienta.example", "m@ipro.fr", "contact@ipro.fr"], str(emails))
check("ref d'annuaire inconnue signalée, jamais tue", orphans == ["inconnu"])
em_off, _ = cli._emails_for(cfg, cli._scan_pending(cfg, "cliente"))
check("projet dont l'option est INACTIVE n'apporte aucun destinataire", em_off == [])

# ── 4. rendu selon le périmètre ──────────────────────────────────────────────
_, subj_p, body_p, _, _, html_p = cli._render_selection(cfg, "clienta", "prestashop", None, None)
check("périmètre projet => sujet au nom du PROJET (récap projet, inchangé)",
      subj_p == "Site PrestaShop — 2 évolutions mises en ligne", subj_p)
_, subj_c, body_c, em_c, _, html_c = cli._render_selection(cfg, "clienta", None, None, None)
check("périmètre client => sujet au nom du CLIENT, tous projets comptés",
      subj_c == "Clienta — 3 évolutions mises en ligne", subj_c)
check("corps client multi-projets : un en-tête par projet",
      "== Site PrestaShop ==" in body_c and "== Synchro Dolibarr ==" in body_c)
_, _, body_1, _, _, _ = cli._render_selection(cfg, "clienta", None, ["3025"], None)
check("sélection d'un seul projet côté client => pas d'en-tête de projet",
      "==" not in body_1 and "#3025" in body_1)
# Le HTML accompagne le texte à CHAQUE rendu : l'email part en multipart, les deux
# parties portent le même contenu et le même sujet.
check("un rendu produit AUSSI le HTML, avec le même sujet",
      html_c.startswith("<!DOCTYPE html>") and subj_c in html_c)
check("le protocole markdown devient un vrai TABLEAU en HTML (l'objet de la demande)",
      "<table style=" in html_c and "|---" not in html_c)
check("périmètre projet : HTML aussi", html_p.startswith("<!DOCTYPE html>"))
check("l'aperçu ne modifie AUCUNE fiche (aucun sent_at posé)",
      "sent_at: null" in (P[("clienta", "prestashop")] / "tasks" / "RM3025_x.md").read_text(encoding="utf-8"))

# ── 5. dismiss : écarte les cochés, laisse les autres ────────────────────────
cli._mark_all_dismissed([t for r in cli._scan_pending(cfg, "clienta", None, ["3042"]) for t in r["tickets"]],
                        "2026-09-09T09:00")
after = sorted(t["id"] for r in cli._scan_pending(cfg, "clienta") for t in r["tickets"])
check("le ticket écarté sort de la file, les autres restent", after == [2948, 3025], str(after))
check("écarter n'envoie rien : pas de sent_at posé",
      "sent_at: null" in (P[("clienta", "prestasync")] / "tasks" / "RM3042_x.md").read_text(encoding="utf-8"))

# ── 6. queue : remettre en file un ticket désigné ───────────────────────────
# La file se remplit seule au passage en_mep ; ce verbe la reforme à la main (envoi raté,
# annonce à refaire, recette du panneau). Il doit trouver des tickets que `_scan_pending`
# ne voit PAS — c'est tout l'intérêt — sans jamais mettre en file ce qui n'est pas en prod.
found = cli._find_tickets(cfg, "clienta", None, ["1111", "3333", "999999"])
check("les tickets DÉSIGNÉS sont trouvés quel que soit leur état de file",
      sorted(t["id"] for t in found) == [1111, 3333], str([t["id"] for t in found]))
check("un id inexistant ne fabrique pas de ticket", 999999 not in [t["id"] for t in found])
check("l'état de file de chacun est rendu (déjà envoyé => pas en file)",
      {t["id"]: t["queued"] for t in found} == {1111: False, 3333: False})
check("le statut est rendu — c'est lui qui autorise la mise en file", found[0]["status"] == "en_mep")


class A:  # argparse minimal
    def __init__(self, **kw):
        self.ref, self.rm, self.yes, self.force, self.json = "clienta/prestashop", None, False, False, False
        self.to, self.dry_run, self.avec_protocole, self.sans_protocole = None, False, False, False
        self.__dict__.update(kw)


try:
    cli.cmd_queue(cfg, A(rm=["1111"], yes=True))
except SystemExit as e:  # noqa: PERF203
    check("queue d'un ticket en_mep : pas d'échec", False, str(e))
back = cli._scan_pending(cfg, "clienta", "prestashop")
check("un ticket DÉJÀ notifié revient en file (nouveau cycle)",
      1111 in [t["id"] for r in back for t in r["tickets"]])
check("…et les autres ne bougent pas",
      sorted(t["id"] for r in back for t in r["tickets"]) == [1111, 2948, 3025])
try:
    cli.cmd_queue(cfg, A(rm=["1111"], yes=True))
    check("remettre en file un ticket DÉJÀ en file : sans effet, sans erreur", True)
except SystemExit:
    check("remettre en file un ticket DÉJÀ en file : sans effet, sans erreur", False)
_st = (P[("clienta", "prestashop")] / "tasks" / "RM1111_x.md").read_text(encoding="utf-8")
check("la mise en file n'écrase pas le statut ni le corps de la fiche",
      "status: en_mep" in _st and "Critères d'acceptation" in _st)

# un ticket qui n'est pas en prod n'a rien à annoncer
task(P[("clienta", "prestashop")], 7777, "Pas encore livré", None)
(P[("clienta", "prestashop")] / "tasks" / "RM7777_x.md").write_text(
    "---\nredmine_id: 7777\ntitle: 'Pas livré'\nstatus: en_cours\n---\ncorps\n", encoding="utf-8")
refused = False
try:
    cli.cmd_queue(cfg, A(rm=["7777"], yes=True))
except SystemExit:
    refused = True
check("ticket qui n'est pas en_mep : REFUSÉ (rien à annoncer)", refused)
check("…et il n'est pas entré en file",
      7777 not in [t["id"] for r in cli._scan_pending(cfg, "clienta") for t in r["tickets"]])
cli.cmd_queue(cfg, A(rm=["7777"], yes=True, force=True))
check("--force passe outre (cas assumé, tracé)",
      7777 in [t["id"] for r in cli._scan_pending(cfg, "clienta") for t in r["tickets"]])
cli._mark_all_dismissed([t for r in cli._scan_pending(cfg, "clienta", None, ["7777"]) for t in r["tickets"]], "2026-09-09T10:00")

# ── 7. envoi de test : n'écrit RIEN ─────────────────────────────────────────
check("l'annuaire est exposé, une entrée par email (choisir sans retaper)",
      [c["email"] for c in cli._contacts_list(cfg)] == ["s@clienta.example", "m@ipro.fr", "contact@ipro.fr"],
      str(cli._contacts_list(cfg)))
check("chaque entrée porte un libellé lisible",
      all(c["label"] and c["ref"] for c in cli._contacts_list(cfg)))

_sent_cmds = []


class _FakeRun:
    returncode = 0
    stdout = stderr = ""


def _fake_run(cmd, **kw):     # l'envoi est simulé : aucun mail ne part d'un test
    _sent_cmds.append(cmd)
    return _FakeRun()


_real_run = cli.subprocess.run
cli.subprocess.run = _fake_run
before = (P[("clienta", "prestashop")] / "tasks" / "RM3025_x.md").read_text(encoding="utf-8")
file_before = sorted(t["id"] for r in cli._scan_pending(cfg, "clienta") for t in r["tickets"])
cli.cmd_test(cfg, A(ref="clienta", rm=["3025"], to=["moi@ipro.fr"]))
check("le test envoie à l'adresse donnée, et à elle seule",
      _sent_cmds and _sent_cmds[-1].count("--to") == 1 and "moi@ipro.fr" in _sent_cmds[-1])
check("sujet préfixé [TEST] (ne pas confondre les deux dans une boîte)",
      "[TEST] " in _sent_cmds[-1][_sent_cmds[-1].index("--subject") + 1])
check("le HTML accompagne le test (c'est le rendu qu'on veut relire)", "--html-file" in _sent_cmds[-1])
check("un test ne touche à AUCUNE fiche : ni sent_at, ni sent_to",
      (P[("clienta", "prestashop")] / "tasks" / "RM3025_x.md").read_text(encoding="utf-8") == before)
check("…et la file reste entière (rien n'en sort après un test)",
      sorted(t["id"] for r in cli._scan_pending(cfg, "clienta") for t in r["tickets"]) == file_before,
      str(file_before))
bad = False
try:
    cli.cmd_test(cfg, A(ref="clienta", rm=["3025"], to=["pasunemail"]))
except SystemExit:
    bad = True
check("adresse invalide : refusée avant tout envoi", bad)
none_to = False
try:
    cli.cmd_test(cfg, A(ref="clienta", rm=["3025"], to=[]))
except SystemExit:
    none_to = True
check("sans --to : refusé", none_to)
cli.subprocess.run = _real_run

no_sel = False
try:
    cli.cmd_queue(cfg, A(rm=[], yes=True))
except SystemExit:
    no_sel = True
check("sans --rm : refusé (on ne remet pas « toute la file » en file par hasard)", no_sel)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
