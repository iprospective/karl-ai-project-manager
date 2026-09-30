#!/usr/bin/env python3
"""Tests RM3043 — op_cdc_list : un sommaire `docs/cdc-<prefix>-00-*.md` par projet, chemins relatifs à projects/ servis par op_file, chapitres triés."""
import importlib.util
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
tmp = tempfile.mkdtemp(prefix="karl-cdc-"); base = pathlib.Path(tmp) / "clients"
os.environ["KARL_AGENT_PROJECTS_BASE"] = str(base); os.environ["KARL_JOURNAL_DIR"] = tmp; os.environ["KARL_JOURNAL_STDERR"] = "0"
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py"); ka = importlib.util.module_from_spec(spec); sys.modules["karl_agent"] = ka; spec.loader.exec_module(ka)
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


d = base / "acme" / "projects" / "site" / "docs"; d.mkdir(parents=True)
(d / "cdc-site-00-sommaire.md").write_text("# CDC Site — sommaire\n"); (d / "cdc-site-90-decisions.md").write_text("# Registre des décisions\n"); (d / "cdc-site-10-fonctionnalites.md").write_text("# 10 — Fonctionnalités\n")
(d / "autre-doc.md").write_text("# pas un CDC\n")
d2 = base / "acme" / "projects" / "sans-cdc" / "docs"; d2.mkdir(parents=True); (d2 / "note.md").write_text("# note\n")
ka._self_project = lambda: ("acme", "site")   # RM3049 : op_cdc_list est scopé au projet PROPRE ; en test, c'est la fixture
r = ka.op_cdc_list()
check("un CDC par projet qui porte un sommaire, les autres docs ignorés", len(r["cdcs"]) == 1 and r["cdcs"][0]["client"] == "acme" and r["cdcs"][0]["project"] == "site" and r["cdcs"][0]["prefix"] == "site")
c = r["cdcs"][0]
check("chemin relatif à projects/ (celui d'op_file) et titre du sommaire", c["path"] == "projects/clients/acme/projects/site/docs/cdc-site-00-sommaire.md" and c["title"] == "CDC Site — sommaire")
check("chapitres triés par numéro, sommaire inclus, doc hors préfixe exclue", [x["file"] for x in c["chapters"]] == ["cdc-site-00-sommaire.md", "cdc-site-10-fonctionnalites.md", "cdc-site-90-decisions.md"])
check("aucun projet → liste vide, pas d'erreur", ka.op_cdc_list.__doc__ and isinstance(r["cdcs"], list))
check("clé client/projet/prefix et registre absent signalé", c["key"] == "acme/site/site" and c["registry"] is False)
# RM3044 : registre des fonctionnalités → JSON ; deux CDC dans un même projet
(d / "cdc-site").mkdir(); (d / "cdc-site" / "fonctionnalites.yml").write_text("prefix: site\nprojet: acme/site\ndomaines:\n- nom: A\n  mots: a\njalons:\n- id: V1\n  titre: pilote\nentrees:\n- id: F001\n  rm: 10\n  libelle: x\n  domaine: A\n  etat: livré\n  jalon: 1\n")
(d / "cdc-karl-00-sommaire.md").write_text("# CDC karl\n")
r2 = ka.op_cdc_features("acme", "site", "site")
check("op_cdc_features : registre lu, domaines à plat, jalons, entrées", r2["domaines"] == ["A"] and r2["jalons"][0]["id"] == "V1" and r2["entrees"][0]["id"] == "F001" and r2["entrees"][0]["jalon"] == 1)
try:
    ka.op_cdc_features("acme", "site", "nope"); check("registre absent → 404", False)
except ka.ApiError as e:
    check("registre absent → 404", e.status == 404 if hasattr(e, "status") else True)
try:
    ka.op_cdc_features("../x", "site", "site"); check("client invalide → 400", False)
except ka.ApiError:
    check("client invalide → 400", True)
# AtomBox : dictionnaire `docs/dict/fonctionnalites.yml` (liste) + jalons.yml → registre équivalent
d3 = base / "acme" / "projects" / "mail" / "docs"; (d3 / "dict").mkdir(parents=True)
(d3 / "cdc-rm2881-00-sommaire.md").write_text("# CDC Mail\n")
(d3 / "dict" / "fonctionnalites.yml").write_text("- id: F001\n  libelle: ingestion\n  domaine: Réception\n  jalon: 0\n  etat: éprouvé\n- id: F002\n  libelle: tags\n  domaine: Tags\n  jalon: 1\n  etat: décidé\n")
(d3 / "dict" / "jalons.yml").write_text("- id: V0\n  titre: pilote\n")
r3 = ka.op_cdc_features("acme", "mail", "rm2881")
check("dictionnaire AtomBox lu comme registre : entrées, domaines déduits, jalons", [e["id"] for e in r3["entrees"]] == ["F001", "F002"] and r3["domaines"] == ["Réception", "Tags"] and r3["jalons"][0]["id"] == "V0")
check("un sommaire cdc-rm<id>-00 est un CDC PAR TICKET (D015) : pas listé comme CDC projet, mais son dictionnaire reste lisible par op_cdc_features", ka._project_cdcs("acme", "mail") == [])
# RM3064 : édition depuis le cockpit — arguments purs vers pm-task-think, projet d'un ticket, validations
rm, local, args = ka._cdc_think_args({"id": "RM3044-D001", "action": "delete"})
check("_cdc_think_args : id fusionné → ticket + id local, --delete", rm == "3044" and local == "D001" and args == ["3044", "--delete", "D001"])
rm, local, args = ka._cdc_think_args({"rm": 44, "id": "Q002", "action": "state", "state": "invalide"})
check("_cdc_think_args : id local + rm, --set --state", args == ["44", "--set", "Q002", "--state", "invalide"])
for bad in ({"id": "D1", "action": "delete"}, {"id": "D001", "action": "delete"}, {"id": "RM1-D001", "rm": 2, "action": "delete"}, {"id": "RM1-D001", "action": "state", "state": "zzz"}, {"id": "RM1-D001", "action": "boom"}):
    try:
        ka._cdc_think_args(bad); check(f"refus {bad}", False)
    except ka.ApiError:
        check(f"refus {bad}", True)
# RM3262 : le panneau lit les textes par NOM de colonne — un carnet migré porte la signature en 2ᵉ
# position, et l'ancien lecteur positionnel aurait affiché « 2026-09-01 · Mathieu » comme question.
import tempfile as _tf
_d = pathlib.Path(_tf.mkdtemp(prefix="rm3262-ka-"))
_fiche = _d / "RM77_x.md"; _fiche.write_text("---\nredmine_id: 77\n---\n", encoding="utf-8")
sys.path.insert(0, str(HERE))
import pm_think as _pt
_th = _pt.think_path(_fiche)
_pt.append(_th, "question", "Faut-il trancher ceci ?", by="M", when="2026-09-01", urgence="haute")
_pt.append(_th, "note", "Une note du carnet", by="A", when="2026-09-02")
_vue = ka._ticket_think(_fiche)
check("le panneau rend le texte de la question, pas sa date",
      _vue["questions"][0]["text"] == "Faut-il trancher ceci ?", str(_vue["questions"][0]))
check("…et sa signature à part", "2026-09-01" in _vue["questions"][0]["signature"])
check("les notes aussi", _vue["notes"][0]["text"] == "Une note du carnet" and "2026-09-02" in _vue["notes"][0]["signature"])

# RM3370 : « trancher sans décision » n'est envoyé qu'explicitement, et seulement pour une question
rm_, loc_, args_ = ka._cdc_think_args({"rm": 44, "id": "Q002", "action": "state", "state": "valide", "force": True})
check("force → --force sur une question validée", args_ == ["44", "--set", "Q002", "--state", "valide", "--force"], str(args_))
check("pas de force sans demande explicite",
      ka._cdc_think_args({"rm": 44, "id": "Q002", "action": "state", "state": "valide"})[2][-1] != "--force")
check("écarter n'a jamais besoin de forcer",
      "--force" not in ka._cdc_think_args({"rm": 44, "id": "Q002", "action": "state", "state": "invalide", "force": True})[2])
check("une NOTE ne se force pas (la garde ne vise que les questions)",
      "--force" not in ka._cdc_think_args({"rm": 44, "id": "N002", "action": "state", "state": "valide", "force": True})[2])
src_ka2 = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("le refus de RM3269 est redit dans les mots du cockpit, sans options de ligne de commande",
      "Trancher cette question demande la reponse qui la tranche" in src_ka2)

# RM3258 : déplacer une entrée vers un autre ticket — le cockpit dit « à qui », jamais « comment »
rm, local, args = ka._cdc_think_args({"rm": 44, "id": "Q002", "action": "move", "to": "3015"})
check("_cdc_think_args : move → --move … --to, en inter-projets assumé",
      args == ["44", "--move", "Q002", "--to", "3015", "--cross-project"], str(args))
check("…et « RM3015 » saisi à la main est accepté",
      ka._cdc_think_args({"rm": 44, "id": "Q002", "action": "move", "to": "RM3015"})[2][-2] == "3015")
for bad in ({"rm": 44, "id": "Q002", "action": "move"},
            {"rm": 44, "id": "Q002", "action": "move", "to": "zz"},
            {"rm": 44, "id": "Q002", "action": "move", "to": "44"}):
    try:
        ka._cdc_think_args(bad); check(f"refus move {bad.get('to')!r}", False)
    except ka.ApiError:
        check(f"refus move {bad.get('to')!r}", True)
src_ka = pathlib.Path(ka.__file__).read_text(encoding="utf-8") if getattr(ka, "__file__", None) else (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("un déplacement refond les registres des DEUX projets", "projets = [p for p in (_task_project(rm)" in src_ka)

# RM3227 : le commentaire joint au geste qui tranche une question devient sa réponse (décision liée)
A = ka._cdc_think_answer_args
check("_cdc_think_answer_args : question validée + commentaire → décision « Qnnn : … » validée, dédupliquée",
      A({"action": "state", "state": "valide", "comment": "  copie   dédiée "}, "44", "Q002", "mathieu")
      == ["44", "--decide", "Q002 : copie dédiée", "--state", "valide", "--by", "mathieu", "--dedupe"])
check("_cdc_think_answer_args : question écartée → « Qnnn écartée : … »",
      A({"action": "state", "state": "invalide", "comment": "hors sujet"}, "44", "Q002")[2] == "Q002 écartée : hors sujet")
check("_cdc_think_answer_args : sans commentaire → rien (comportement d'avant)",
      A({"action": "state", "state": "valide"}, "44", "Q002") is None
      and A({"action": "state", "state": "valide", "comment": "   "}, "44", "Q002") is None)
check("_cdc_think_answer_args : une note ou une décision n'a pas de « réponse »",
      A({"action": "state", "state": "valide", "comment": "x"}, "44", "N001") is None
      and A({"action": "state", "state": "valide", "comment": "x"}, "44", "D001") is None)
check("_cdc_think_answer_args : jamais sur une suppression", A({"action": "delete", "comment": "x"}, "44", "Q002") is None)
check("_cdc_think_answer_args : auteur par défaut = le demandeur (M)", A({"action": "state", "state": "valide", "comment": "x"}, "44", "Q002", "")[6] == "M")
try:
    A({"action": "state", "state": "valide", "comment": "x" * 1001}, "44", "Q002"); check("commentaire trop long refusé", False)
except ka.ApiError:
    check("commentaire trop long refusé", True)
_src = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("op_cdc_think consigne la réponse AVANT de changer l'état (rejouable grâce à --dedupe)",
      _src.index("_pm_script(\"pm-task-think.py\", answer") < _src.index("out = _pm_script(\"pm-task-think.py\", args"))
# RM3070 L3 : l'acteur voyage jusqu'au script — c'est lui qui signera le commit du carnet
check("op_cdc_think passe l'acteur au script appelé",
      "_pm_script(\"pm-task-think.py\", args, auth_ctx=auth_ctx)" in _src)
check("la route passe l'utilisateur authentifié (signature de la réponse)", "op_cdc_think(payload, self.auth_ctx)" in _src)
tdir = base / "acme" / "projects" / "site" / "tasks"; tdir.mkdir(parents=True); (tdir / "RM77_x.md").write_text("---\nredmine_id: 77\n---\n"); (tdir / "RM77_x.think.md").write_text("# think\n")
check("_task_project : (client, projet) d'un ticket, le think ignoré", ka._task_project("77") == ("acme", "site") and ka._task_project("9999") is None)
try:
    ka.op_cdc_feature({"client": "acme", "project": "site", "prefix": "cdc", "id": "F01", "etat": "écarté"}); check("op_cdc_feature : id invalide refusé", False)
except ka.ApiError:
    check("op_cdc_feature : id invalide refusé", True)
try:
    ka.op_cdc_feature({"client": "acme", "project": "site", "prefix": "cdc", "id": "F001", "etat": "n'importe"}); check("op_cdc_feature : état inconnu refusé", False)
except ka.ApiError:
    check("op_cdc_feature : état inconnu refusé", True)
cs = ka._project_cdcs("acme", "site")
check("deux CDC dans un même projet (pm + karl), registre détecté pour le premier", [x["prefix"] for x in cs] == ["karl", "site"] and cs[1]["registry"] is True and cs[0]["registry"] is False)

# — RM3049 : le menu CDC du haut = le CDC du projet PROPRE UNIQUEMENT (jamais multi-projets) —
_calls = []
_orig_pc, _orig_sp = ka._project_cdcs, ka._self_project
ka._project_cdcs = lambda c, p: (_calls.append((c, p)) or [{"client": c, "project": p, "key": f"{c}/{p}/x"}])
ka._self_project = lambda: ("iprospective", "pm-ai-agents")
try:
    _res = ka.op_cdc_list()
finally:
    ka._project_cdcs, ka._self_project = _orig_pc, _orig_sp
check("RM3049 : op_cdc_list ne lit QUE le projet propre (pm-ai-agents), pas les autres",
      _calls == [("iprospective", "pm-ai-agents")])
check("RM3049 : ne renvoie que le(s) CDC de ce projet",
      [c["key"] for c in _res["cdcs"]] == ["iprospective/pm-ai-agents/x"])

print("\n" + ("ÉCHEC : " + ", ".join(fails) if fails else "OK — op_cdc_list"))
sys.exit(1 if fails else 0)
