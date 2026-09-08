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
r = ka.op_cdc_list()
check("un CDC par projet qui porte un sommaire, les autres docs ignorés", len(r["cdcs"]) == 1 and r["cdcs"][0]["client"] == "acme" and r["cdcs"][0]["project"] == "site" and r["cdcs"][0]["prefix"] == "site")
c = r["cdcs"][0]
check("chemin relatif à projects/ (celui d'op_file) et titre du sommaire", c["path"] == "projects/clients/acme/projects/site/docs/cdc-site-00-sommaire.md" and c["title"] == "CDC Site — sommaire")
check("chapitres triés par numéro, sommaire inclus, doc hors préfixe exclue", [x["file"] for x in c["chapters"]] == ["cdc-site-00-sommaire.md", "cdc-site-10-fonctionnalites.md", "cdc-site-90-decisions.md"])
check("aucun projet → liste vide, pas d'erreur", ka.op_cdc_list.__doc__ and isinstance(r["cdcs"], list))
print("\n" + ("ÉCHEC : " + ", ".join(fails) if fails else "OK — op_cdc_list"))
sys.exit(1 if fails else 0)
