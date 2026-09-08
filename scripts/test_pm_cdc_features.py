#!/usr/bin/env python3
"""Tests RM3043 — pm-cdc-features : init/sync/build/check sur un jeu de tickets temporaire (états, ids stables, manuel, bugfix, check rouge/vert)."""
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_cdc_features", HERE / "pm-cdc-features.py"); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def ticket(d, rm, title, status, typ="feature", reason=None, closed_at=None, parent=None):
    fm = [f"redmine_id: {rm}", f"title: '{title}'", f"type: {typ}", f"status: {status}", "updated: '2026-09-01T10:00'"]
    if reason: fm.append(f"close_reason: {reason}")
    if parent: fm.append(f"parent_task: {parent}")
    if closed_at: fm += ["status_history:", "- status: ferme", f"  at: '{closed_at}T12:00'"]
    (d / f"RM{rm}_x.md").write_text("---\n" + "\n".join(fm) + "\n---\n\ncorps\n", encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    tasks = pathlib.Path(tmp) / "tasks"; docs = pathlib.Path(tmp) / "docs"; tasks.mkdir(); docs.mkdir()
    ticket(tasks, 10, "Cockpit : onglet journal", "ferme", closed_at="2026-08-01")
    ticket(tasks, 11, "pm-task-add : bug de porcelain", "ferme", typ="bugfix", closed_at="2026-08-02")
    ticket(tasks, 12, "Un ticket en cours", "en_cours")
    ticket(tasks, 13, "Un ticket non trié", "nouveau")
    ticket(tasks, 14, "Une piste abandonnée", "ferme", reason="abandonne", closed_at="2026-08-03")
    ticket(tasks, 15, "Sous-tâche du 12", "a_faire", parent=12)
    base = [sys.executable, str(HERE / "pm-cdc-features.py"), "--docs-dir", str(docs), "--tasks-dir", str(tasks), "--project", "t/p"]
    run = lambda *a: subprocess.run(base + list(a), capture_output=True, text=True)
    r = run("--init", "--prefix", "t", "--build")
    check("init + build : registre et chapitre écrits", r.returncode == 0 and (docs / "cdc-t/fonctionnalites.yml").exists() and (docs / "cdc-t-10-fonctionnalites.md").exists(), r.stdout + r.stderr)
    reg = M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())
    ids = {e["rm"]: e for e in reg["entrees"]}
    check("nouveau exclu, les autres entrés, ids F001… dans l'ordre RM", 13 not in ids and [e["id"] for e in reg["entrees"]] == ["F001", "F002", "F003", "F004", "F005"])
    check("états dérivés : livré / en cours / prévu / écarté(raison)", ids[10]["etat"] == "livré" and ids[12]["etat"] == "en cours" and ids[15]["etat"] == "prévu" and ids[14]["etat"] == "écarté (abandonne)")
    check("date de fermeture prise dans status_history", ids[10]["date"] == "2026-08-01")
    check("domaines par mots-clés + parent conservé", ids[10]["domaine"].startswith("Cockpit") and ids[11]["domaine"].startswith("Outillage") and ids[15].get("parent") == 12)
    chap = (docs / "cdc-t-10-fonctionnalites.md").read_text()
    check("chapitre : table par domaine, bugfix en corrections, sous-tâche annotée", "| F001 | Cockpit : onglet journal | RM10 |" in chap and "- F002 · RM11 ·" in chap and "sous-tâche de RM12" in chap)
    check("check vert quand tout est à jour", run("--check").returncode == 0)
    # le ticket 12 se livre, le 13 est trié, une entrée est retouchée à la main
    ticket(tasks, 12, "Un ticket en cours", "ferme", closed_at="2026-08-05"); ticket(tasks, 13, "Un ticket trié : cockpit", "a_faire")
    reg["entrees"][0]["libelle"] = "Onglet journal (libellé retouché)"; reg["entrees"][0]["domaine"] = "Docs, wiki & knowledge"; reg["entrees"][0]["manuel"] = True
    (docs / "cdc-t/fonctionnalites.yml").write_text(M.dump(reg))
    check("check rouge quand un ticket a bougé", run("--check").returncode == 1)
    r = run("--sync", "--build"); reg2 = M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text()); ids2 = {e["rm"]: e for e in reg2["entrees"]}
    check("sync : état avancé, nouveau trié ajouté avec l'id suivant, ids existants stables", ids2[12]["etat"] == "livré" and ids2[12]["date"] == "2026-08-05" and ids2[13]["id"] == "F006" and ids2[10]["id"] == "F001")
    check("manuel: true : libellé et domaine conservés", ids2[10]["libelle"] == "Onglet journal (libellé retouché)" and ids2[10]["domaine"] == "Docs, wiki & knowledge")
    check("check vert après sync+build", run("--check").returncode == 0)
    # RM3044 : registre curé (--no-sync), tickets multiples couverts, jalon rendu
    docs2 = pathlib.Path(tmp) / "docs2"; docs2.mkdir()
    base2 = [sys.executable, str(HERE / "pm-cdc-features.py"), "--docs-dir", str(docs2), "--tasks-dir", str(tasks), "--project", "t/p"]
    run2 = lambda *a: subprocess.run(base2 + list(a), capture_output=True, text=True)
    r = run2("--init", "--prefix", "k", "--no-sync"); reg3 = M.yaml.safe_load((docs2 / "cdc-k/fonctionnalites.yml").read_text())
    check("init --no-sync : registre vide, jalons présents", r.returncode == 0 and reg3["entrees"] == [] and reg3.get("jalons") == [])
    reg3["jalons"] = [{"id": "V1", "titre": "pilote"}]
    reg3["entrees"] = [{"id": "F001", "libelle": "Capacité A (tickets 10 et 11)", "domaine": "Cockpit", "type": "feature", "etat": "livré", "date": "2026-08-02", "tickets": [10, 11], "jalon": 1, "manuel": True}]
    (docs2 / "cdc-k/fonctionnalites.yml").write_text(M.dump(reg3))
    r = run2("--sync", "--build"); reg4 = M.yaml.safe_load((docs2 / "cdc-k/fonctionnalites.yml").read_text()); rms = sorted(e.get("rm") for e in reg4["entrees"] if e.get("rm"))
    check("sync : les tickets couverts par une entrée curée ne sont pas rajoutés, les autres si", 10 not in rms and 11 not in rms and 12 in rms and reg4["entrees"][0]["id"] == "F001")
    chap2 = (docs2 / "cdc-k-10-fonctionnalites.md").read_text()
    check("chapitre : tickets multiples et colonne jalon", "| F001 | Capacité A (tickets 10 et 11) | RM10, RM11 | feature | V1 | livré |" in chap2 and "| Jalon |" in chap2)
    check("check vert sur un registre curé", run2("--check").returncode == 0)
print("\n" + ("ÉCHEC : " + ", ".join(fails) if fails else "OK — pm-cdc-features"))
sys.exit(1 if fails else 0)
