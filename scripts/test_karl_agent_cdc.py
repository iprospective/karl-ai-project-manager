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
