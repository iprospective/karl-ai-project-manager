#!/usr/bin/env python3
"""Tests RM3043 — pm-cdc-features : init/sync/build/check sur un jeu de tickets temporaire (états, ids stables,
manuel, bugfix, check rouge/vert). RM3060 : les VERSIONS — une étape de travail, son rôle, son critère de
passage, et les fonctionnalités qui s'y rattachent ; la feuille de route en est générée."""
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
    check("chapitre : tickets multiples et colonne jalon", "| F001 | Capacité A (tickets 10 et 11) | RM10, RM11 | feature | V1 | livré |" in chap2 and "| Version |" in chap2)
    check("check vert sur un registre curé", run2("--check").returncode == 0)
    # RM3060 : version par entrée, --assign-version en masse (filtre état), colonne Version
    r = run2("--assign-version", "V0", "--etat", "livré", "--build"); reg5 = M.yaml.safe_load((docs2 / "cdc-k/fonctionnalites.yml").read_text())
    check("--assign-version : posée sur les livrées sans version ni jalon, les autres intactes", r.returncode == 0 and all(e.get("version") == "V0" for e in reg5["entrees"] if e["etat"] == "livré" and e.get("jalon") is None) and not reg5["entrees"][0].get("version") and all(not e.get("version") for e in reg5["entrees"] if e["etat"] != "livré"))
    chap5 = (docs2 / "cdc-k-10-fonctionnalites.md").read_text()
    check("chapitre : colonne Version (jalon AtomBox rendu V<n>, version telle quelle)", "| Version |" in chap5 and "| V1 | livré |" in chap5)
    check("check vert après assignation", run2("--check").returncode == 0)
    # ── RM3060 : les versions ──────────────────────────────────────────────
    print("\n[RM3060] versions : des étapes de travail, pas une copie des fonctionnalités")
    r = run("--add-version", "V0", "--role", "alpha : ça tourne pour un dev", "--critere", "utilisable au quotidien", "--etat-version", "en cours")
    reg = M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())
    v0 = next((v for v in (reg.get("versions") or []) if v["id"] == "V0"), None)
    check("une version se crée avec son rôle, son critère et son état",
          r.returncode == 0 and v0 and v0["role"].startswith("alpha") and v0["critere"] and v0["etat"] == "en cours", r.stdout + r.stderr)
    r = run("--add-version", "V0", "--role", "alpha, reformulé")
    reg = M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())
    v0 = next(v for v in reg["versions"] if v["id"] == "V0")
    check("la recréer la complète sans rien perdre", v0["role"] == "alpha, reformulé" and v0["critere"] and v0["etat"] == "en cours")
    check("un identifiant de version douteux est refusé", run("--add-version", "V1 ; rm -rf /").returncode != 0)

    fid = reg["entrees"][0]["id"]
    r = run("--set-version", fid, "V0", "--build")
    reg = M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())
    check("une fonctionnalité se rattache à une version",
          r.returncode == 0 and next(e for e in reg["entrees"] if e["id"] == fid).get("version") == "V0", r.stdout + r.stderr)
    road = docs / "cdc-t-roadmap.md"
    txt = road.read_text(encoding="utf-8") if road.is_file() else ""
    check("la feuille de route est GÉNÉRÉE, pas tenue à la main", road.is_file() and "Généré" in txt)
    check("elle montre le rôle, l'état et le critère de passage", "alpha, reformulé" in txt and "utilisable au quotidien" in txt)
    check("elle compte les fonctionnalités rattachées, sans les recopier en tête", "| 0/1 |" in txt or "| 1/1 |" in txt)
    check("et les liste sous leur version", f"**{fid}**" in txt)
    check("les fonctionnalités en cours sans version sont signalées", "Sans version" in txt)

    r = run("--set-version", fid, "-", "--build")
    reg = M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())
    check("on peut la détacher", r.returncode == 0 and "version" not in next(e for e in reg["entrees"] if e["id"] == fid))
    check("rattacher à une version inconnue la déclare au passage",
          run("--set-version", fid, "V9").returncode == 0
          and any(v["id"] == "V9" for v in M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())["versions"]))
    check("une entrée inconnue est refusée", run("--set-version", "F999", "V0").returncode != 0)

    r = run("--drop-version", "V9", "--build")
    reg = M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())
    check("retirer une version la retire aussi des entrées, sans supprimer aucune fonctionnalité",
          r.returncode == 0 and not any(v["id"] == "V9" for v in reg["versions"])
          and not any(e.get("version") == "V9" for e in reg["entrees"])
          and len(reg["entrees"]) == len(M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())["entrees"]))
    check("--check couvre désormais la feuille de route", "feuille de route" in run("--check").stdout)
    road.write_text("édité à la main\n", encoding="utf-8")
    check("une feuille de route éditée à la main rend --check rouge", run("--check").returncode != 0)
    check("et --build la remet d'aplomb", run("--build").returncode == 0 and run("--check").returncode == 0)

    # ── RM3048 : un registre CURÉ, tenu à la main, à côté du registre dérivé des tickets ──
    print("\n[RM3048] registre curé par capacité")
    r = run("--init", "--prefix", "k", "--no-sync")
    check("un registre curé se crée vide", r.returncode == 0 and (docs / "cdc-k/fonctionnalites.yml").exists())
    reg = M.yaml.safe_load((docs / "cdc-k/fonctionnalites.yml").read_text())
    check("créé vide, il ne contient aucun ticket", not reg.get("entrees"))
    reg.update({"cure": True, "titre": "Capacités du machin",
                "entrees": [{"id": "F001", "libelle": "Faire le café", "domaine": "Divers", "etat": "livré",
                             "date": "2026-09-10", "manuel": True, "type": "feature", "tickets": [10, 12], "rm": 10}]})
    (docs / "cdc-k/fonctionnalites.yml").write_text(M.dump(reg), encoding="utf-8")
    r = run("--prefix", "k", "--build")
    check("--prefix vise CE registre quand le projet en porte plusieurs", r.returncode == 0 and "cdc-k" in r.stdout)
    chap = (docs / "cdc-k-10-fonctionnalites.md").read_text(encoding="utf-8")
    check("le chapitre porte le titre du registre, pas celui du projet", chap.startswith("# Capacités du machin"))
    check("une capacité montre TOUS ses tickets", "RM10, RM12" in chap)
    r = run("--prefix", "k", "--sync")
    check("--sync est REFUSÉ sur un registre curé, en disant pourquoi",
          r.returncode != 0 and "CURÉ" in (r.stdout + r.stderr))
    reg2 = M.yaml.safe_load((docs / "cdc-k/fonctionnalites.yml").read_text())
    check("et le registre n'a pas bougé", len(reg2["entrees"]) == 1)
    check("--check ne compare que le chapitre sur un registre curé", run("--prefix", "k", "--check").returncode == 0)
    check("l'autre registre, lui, dérive toujours des tickets", run("--prefix", "t", "--check").returncode == 0
          and len(M.yaml.safe_load((docs / "cdc-t/fonctionnalites.yml").read_text())["entrees"]) > 1)

print("\n" + ("ÉCHEC : " + ", ".join(fails) if fails else "OK — pm-cdc-features"))
sys.exit(1 if fails else 0)
