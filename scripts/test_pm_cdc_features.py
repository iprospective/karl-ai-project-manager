#!/usr/bin/env python3
"""Tests RM3043 — pm-cdc-features : init/sync/build/check sur un jeu de tickets temporaire (états, ids stables,
manuel, bugfix, check rouge/vert). RM3060 : les VERSIONS — une étape de travail, son rôle, son critère de
passage, et les fonctionnalités qui s'y rattachent ; la feuille de route en est générée.

RM3099 — la FUSION des deux registres. Ce que ces tests tiennent, et qui se perdait autrement :
une fonctionnalité peut n'avoir AUCUN ticket ; `--absorb` verse un registre dans l'autre sans perdre
un libellé ni une référence, avec des ids neufs (jamais réattribués) ; l'état d'une entrée
multi-tickets est celui du plus avancé, ce qui reste ouvert étant compté à part."""
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
    reg_file = docs / "cdc/fonctionnalites.yml"; chap_file = docs / "cdc-features.md"
    r = run("--init", "--build")
    check("init + build : registre et chapitre écrits", r.returncode == 0 and reg_file.exists() and chap_file.exists(), r.stdout + r.stderr)
    reg = M.yaml.safe_load(reg_file.read_text())
    ids = {e["tickets"][0]: e for e in reg["entrees"] if e.get("tickets")}
    check("nouveau exclu, les autres entrés, ids F001… dans l'ordre RM", 13 not in ids and [e["id"] for e in reg["entrees"]] == ["F001", "F002", "F003", "F004", "F005"])
    check("états dérivés : livré / en cours / prévu / écarté(raison)", ids[10]["etat"] == "livré" and ids[12]["etat"] == "en cours" and ids[15]["etat"] == "prévu" and ids[14]["etat"] == "écarté (abandonne)")
    check("date de fermeture prise dans status_history", ids[10]["date"] == "2026-08-01")
    check("le ticket est une RÉFÉRENCE, dans une liste (RM3099) — plus de champ `rm`",
          ids[10]["tickets"] == [10] and "rm" not in ids[10])
    # RM3099-D002 : le domaine d'USAGE groupe, le domaine TECHNIQUE reste en étiquette
    check("domaine d'usage posé par les mots-clés, domaine technique en étiquette, parent conservé",
          ids[10]["domaine"] == "Navigation, onglets & mobile" and ids[10]["domaine_technique"].startswith("Cockpit")
          and ids[11]["domaine"] == "Tickets & PM" and ids[11]["domaine_technique"].startswith("Outillage")
          and ids[15].get("parent") == 12, str(ids[10]) + str(ids[11]))
    chap = chap_file.read_text()
    check("chapitre : table par domaine d'usage, colonne Technique, bugfix en corrections, sous-tâche annotée",
          "| F001 | Cockpit : onglet journal | RM10 |" in chap and "| Technique |" in chap
          and "- F002 · RM11 ·" in chap and "sous-tâche de RM12" in chap, chap[:600])
    check("check vert quand tout est à jour", run("--check").returncode == 0)
    # le ticket 12 se livre, le 13 est trié, une entrée est retouchée à la main
    ticket(tasks, 12, "Un ticket en cours", "ferme", closed_at="2026-08-05"); ticket(tasks, 13, "Un ticket trié : cockpit", "a_faire")
    reg["entrees"][0]["libelle"] = "Onglet journal (libellé retouché)"; reg["entrees"][0]["domaine"] = "Méthode & normes"; reg["entrees"][0]["manuel"] = True
    reg_file.write_text(M.dump(reg))
    check("check rouge quand un ticket a bougé", run("--check").returncode == 1)
    r = run("--sync", "--build"); reg2 = M.yaml.safe_load(reg_file.read_text()); ids2 = {e["tickets"][0]: e for e in reg2["entrees"] if e.get("tickets")}
    check("sync : état avancé, nouveau trié ajouté avec l'id suivant, ids existants stables", ids2[12]["etat"] == "livré" and ids2[12]["date"] == "2026-08-05" and ids2[13]["id"] == "F006" and ids2[10]["id"] == "F001")
    check("manuel: true : libellé et domaine d'usage conservés", ids2[10]["libelle"] == "Onglet journal (libellé retouché)" and ids2[10]["domaine"] == "Méthode & normes")
    check("check vert après sync+build", run("--check").returncode == 0)

    # ── RM3099 : une fonctionnalité couvre PLUSIEURS tickets, ou AUCUN ──────
    print("\n[RM3099] une seule notion : la fonctionnalité, les tickets en référence")
    reg3 = M.yaml.safe_load(reg_file.read_text())
    reg3["entrees"] += [
        {"id": "F900", "libelle": "Capacité multi-tickets", "domaine": "Tickets & PM", "type": "feature",
         "etat": "prévu", "date": "2026-08-01", "tickets": [10, 15], "manuel": True},
        {"id": "F901", "libelle": "Capacité SANS aucun ticket", "domaine": "Tickets & PM", "type": "feature",
         "etat": "livré", "date": "2026-08-01", "manuel": True},
    ]
    reg_file.write_text(M.dump(reg3))
    r = run("--sync", "--build"); reg4 = M.yaml.safe_load(reg_file.read_text())
    f900 = next(e for e in reg4["entrees"] if e["id"] == "F900"); f901 = next(e for e in reg4["entrees"] if e["id"] == "F901")
    check("l'état d'une entrée multi-tickets est celui du PLUS AVANCÉ (RM3099-D003)", f900["etat"] == "livré", str(f900))
    check("…et ce qui reste ouvert est compté, pas caché", f900.get("restants") == 1)
    check("une fonctionnalité SANS ticket existe et n'est pas touchée (RM3099-D001)",
          f901["etat"] == "livré" and not f901.get("tickets") and not f901.get("restants"))
    chap4 = chap_file.read_text()
    check("le chapitre montre tous les tickets d'une entrée, l'état nuancé, et « — » quand il n'y en a aucun",
          "| RM10, RM15 |" in chap4 and "livré · 1 en cours" in chap4 and "| Capacité SANS aucun ticket | — |" in chap4, chap4[-1500:])
    check("un ticket déjà cité ne recrée pas d'entrée", sum(1 for e in reg4["entrees"] if 15 in (e.get("tickets") or [])) == 2
          and len([e for e in reg4["entrees"] if e.get("tickets") == [15]]) == 1)
    # RM3064 : --set-etat fige l'ÉTAT (etat_manuel), sans figer le libellé (manuel) — deux choses distinctes
    r = run("--set-etat", "F006", "en pause", "--build")
    reg5 = M.yaml.safe_load(reg_file.read_text()); f6 = next(e for e in reg5["entrees"] if e["id"] == "F006")
    check("--set-etat fige l'état et lui seul", r.returncode == 0 and f6["etat"] == "en pause" and f6.get("etat_manuel") is True and not f6.get("manuel"))
    run("--sync", "--build"); f6b = next(e for e in M.yaml.safe_load(reg_file.read_text())["entrees"] if e["id"] == "F006")
    check("…et sync ne le réécrit pas, mais réécrit toujours le libellé", f6b["etat"] == "en pause" and f6b["libelle"] == "Un ticket trié : cockpit")
    check("un état inconnu est refusé", run("--set-etat", "F006", "presque").returncode != 0)

    # ── RM3099 : --absorb, la fusion des deux registres ─────────────────────
    print("\n[RM3099] --absorb : deux registres deviennent un, sans perte")
    autre = pathlib.Path(tmp) / "autre.yml"
    autre.write_text(M.yaml.safe_dump({
        "prefix": "karl", "cure": True, "titre": "Capacités",
        "domaines": [{"nom": "Un domaine d'usage à moi", "mots": ""}],
        "entrees": [
            {"id": "F001", "libelle": "Faire le café", "domaine": "Un domaine d'usage à moi", "etat": "livré",
             "date": "2026-09-10", "manuel": True, "type": "feature", "tickets": [10, 12], "rm": 10},
            {"id": "F002", "libelle": "Capacité sans ticket du tout", "domaine": "Un domaine d'usage à moi",
             "etat": "livré", "date": "2026-09-10", "manuel": True, "type": "feature"},
        ]}, allow_unicode=True), encoding="utf-8")
    avant = M.yaml.safe_load(reg_file.read_text())
    avant_ids = {e["id"] for e in avant["entrees"]}
    avant_tickets = {t for e in avant["entrees"] for t in M.tickets_de(e)}
    r = run("--absorb", str(autre), "--sync", "--build")
    apres = M.yaml.safe_load(reg_file.read_text())
    apres_ids = [e["id"] for e in apres["entrees"]]
    cafe = next((e for e in apres["entrees"] if e["libelle"] == "Faire le café"), None)
    check("absorb : les entrées de l'autre registre arrivent, avec des ids NEUFS (aucune collision)",
          r.returncode == 0 and cafe and cafe["id"] not in avant_ids and len(set(apres_ids)) == len(apres_ids), r.stdout + r.stderr)
    check("…leurs libellés sont conservés mot pour mot, tickets compris (rm fondu dans tickets)",
          cafe["libelle"] == "Faire le café" and cafe["tickets"] == [10, 12] and cafe.get("manuel") is True)
    check("…une capacité sans ticket passe aussi", any(e["libelle"] == "Capacité sans ticket du tout" for e in apres["entrees"]))
    check("les entrées DÉRIVÉES dont le ticket est désormais cité sont ABSORBÉES, pas doublées",
          not any(e.get("tickets") == [10] and e["libelle"] != "Faire le café" for e in apres["entrees"]))
    check("aucun ticket n'a perdu sa référence",
          avant_tickets <= {t for e in apres["entrees"] for t in M.tickets_de(e)})
    check("les domaines d'USAGE de l'autre registre prennent la tête du plan (D002)",
          apres["domaines"][0]["nom"] == "Un domaine d'usage à moi" and apres.get("domaines_techniques"))
    check("le registre absorbé n'a plus ni prefix ni cure : il n'y a plus qu'un registre",
          "prefix" not in apres and "cure" not in apres)
    check("check vert après absorption", run("--check").returncode == 0)

    # ── RM3060 : les versions ──────────────────────────────────────────────
    print("\n[RM3060] versions : des étapes de travail, pas une copie des fonctionnalités")
    r = run("--add-version", "V0", "--role", "alpha : ça tourne pour un dev", "--critere", "utilisable au quotidien", "--etat-version", "en cours")
    reg = M.yaml.safe_load(reg_file.read_text())
    v0 = next((v for v in (reg.get("versions") or []) if v["id"] == "V0"), None)
    check("une version se crée avec son rôle, son critère et son état",
          r.returncode == 0 and v0 and v0["role"].startswith("alpha") and v0["critere"] and v0["etat"] == "en cours", r.stdout + r.stderr)
    r = run("--add-version", "V0", "--role", "alpha, reformulé")
    reg = M.yaml.safe_load(reg_file.read_text())
    v0 = next(v for v in reg["versions"] if v["id"] == "V0")
    check("la recréer la complète sans rien perdre", v0["role"] == "alpha, reformulé" and v0["critere"] and v0["etat"] == "en cours")
    check("un identifiant de version douteux est refusé", run("--add-version", "V1 ; rm -rf /").returncode != 0)

    fid = reg["entrees"][0]["id"]
    r = run("--set-version", fid, "V0", "--build")
    reg = M.yaml.safe_load(reg_file.read_text())
    check("une fonctionnalité se rattache à une version",
          r.returncode == 0 and next(e for e in reg["entrees"] if e["id"] == fid).get("version") == "V0", r.stdout + r.stderr)
    road = docs / "cdc-roadmap.md"
    txt = road.read_text(encoding="utf-8") if road.is_file() else ""
    check("la feuille de route est GÉNÉRÉE, pas tenue à la main", road.is_file() and "Généré" in txt)
    check("elle montre le rôle, l'état et le critère de passage", "alpha, reformulé" in txt and "utilisable au quotidien" in txt)
    check("elle compte les fonctionnalités rattachées, sans les recopier en tête", "| 0/1 |" in txt or "| 1/1 |" in txt)
    check("et les liste sous leur version", f"**{fid}**" in txt)
    check("les fonctionnalités en cours sans version sont signalées", "Sans version" in txt)

    r = run("--set-version", fid, "-", "--build")
    reg = M.yaml.safe_load(reg_file.read_text())
    check("on peut la détacher", r.returncode == 0 and "version" not in next(e for e in reg["entrees"] if e["id"] == fid))
    check("rattacher à une version inconnue la déclare au passage",
          run("--set-version", fid, "V9").returncode == 0
          and any(v["id"] == "V9" for v in M.yaml.safe_load(reg_file.read_text())["versions"]))
    check("une entrée inconnue est refusée", run("--set-version", "F999", "V0").returncode != 0)

    r = run("--drop-version", "V9", "--build")
    reg = M.yaml.safe_load(reg_file.read_text())
    check("retirer une version la retire aussi des entrées, sans supprimer aucune fonctionnalité",
          r.returncode == 0 and not any(v["id"] == "V9" for v in reg["versions"])
          and not any(e.get("version") == "V9" for e in reg["entrees"])
          and len(reg["entrees"]) == len(M.yaml.safe_load(reg_file.read_text())["entrees"]))
    r = run("--assign-version", "V0", "--etat", "livré", "--build")
    reg = M.yaml.safe_load(reg_file.read_text())
    check("--assign-version : posée sur les livrées sans version, les autres intactes",
          r.returncode == 0 and all(e.get("version") == "V0" for e in reg["entrees"] if e["etat"] == "livré")
          and all(not e.get("version") for e in reg["entrees"] if e["etat"] != "livré"))
    check("--check couvre désormais la feuille de route", "feuille de route" in run("--check").stdout)
    road.write_text("édité à la main\n", encoding="utf-8")
    check("une feuille de route éditée à la main rend --check rouge", run("--check").returncode != 0)
    check("et --build la remet d'aplomb", run("--build").returncode == 0 and run("--check").returncode == 0)

print("\n" + ("ÉCHEC : " + ", ".join(fails) if fails else "OK — pm-cdc-features"))
sys.exit(1 if fails else 0)
