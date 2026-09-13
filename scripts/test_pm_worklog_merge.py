#!/usr/bin/env python3
"""Tests RM2992 — reprendre un worklog resté à l'ancien emplacement.

Le déplacement des données a copié les worklogs, puis le démon a continué d'écrire dans l'ANCIEN
jusqu'à son redémarrage. Au redémarrage il a repris le fichier copié, sans ce qui avait été écrit
entre-temps : une session active ce jour-là a vu 83 tickets devenir 2.

Ce qui doit tenir : la fusion n'ampute jamais, elle complète ; elle ne duplique pas ; elle sauvegarde
avant d'écrire ; et elle ne crie pas quand il n'y a rien à reprendre.
"""
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("wm", HERE / "pm-worklog-merge.py")
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM2992] la fusion complète, elle n'ampute pas")
ancien = {"session_id": "s1", "title": "vieux titre",
          "items": [{"id": 1, "ref": "RM1", "status": "en_cours", "note": "important"},
                    {"id": 2, "ref": "RM2", "status": "ferme"}],
          "requests": [{"ts": "t1", "text": "une demande"}],
          "mrs": [{"iid": "10", "url": "u10"}, {"iid": "11", "url": "u11"}],
          "notifications": [{"ts": "n1", "message": "attention"}]}
courant = {"session_id": "s1", "title": "titre à jour",
           "items": [{"id": 1, "ref": "RM2", "status": "ferme"},
                     {"id": 2, "ref": "RM3", "status": "a_faire"}]}
f = W.fusionne(ancien, courant)
refs = [i["ref"] for i in f["items"]]
check("les tickets des deux côtés sont là", refs == ["RM1", "RM2", "RM3"], str(refs))
check("rien n'est dupliqué", len(refs) == len(set(refs)))
check("ce que le courant ne porte pas survit", f["items"][0].get("note") == "important")
check("les demandes, MR et notifications de l'ancien reviennent",
      len(f["requests"]) == 1 and len(f["mrs"]) == 2 and len(f["notifications"]) == 1)
check("le titre COURANT gagne : c'est le plus récent", f["title"] == "titre à jour")
check("les identifiants restent contigus", [i["id"] for i in f["items"]] == [1, 2, 3])
check("refusionner ne change plus rien", W.compte(W.fusionne(ancien, f)) == W.compte(f))

print("\n[RM2992] une entrée plus riche d'un côté est complétée, pas remplacée")
a2 = {"items": [{"id": 1, "ref": "RM9", "status": "en_cours", "project": "p", "note": "détail"}]}
b2 = {"items": [{"id": 1, "ref": "RM9", "status": "ferme"}]}
i = W.fusionne(a2, b2)["items"][0]
check("le statut le plus récent gagne", i["status"] == "ferme")
check("les champs que le récent ne porte pas sont gardés", i.get("note") == "détail" and i.get("project") == "p")

print("\n[RM2992] détecter ce qui est vraiment en retard")
with tempfile.TemporaryDirectory() as tmp:
    old, new = pathlib.Path(tmp) / "old", pathlib.Path(tmp) / "new"
    old.mkdir(); new.mkdir()
    import os
    os.environ["PM_WORKLOG_OLD_DIR"], os.environ["PM_WORKLOG_DIR"] = str(old), str(new)
    (old / "sA.json").write_text(json.dumps(ancien), encoding="utf-8")
    (new / "sA.json").write_text(json.dumps(courant), encoding="utf-8")
    # une session dont l'ancien porte des DOUBLONS : la fusion n'apporte rien, ce n'est pas un retard
    dbl = {"items": [{"id": 1, "ref": "RM5"}, {"id": 2, "ref": "RM5"}]}
    (old / "sB.json").write_text(json.dumps(dbl), encoding="utf-8")
    (new / "sB.json").write_text(json.dumps({"items": [{"id": 1, "ref": "RM5"}]}), encoding="utf-8")
    retard = {s for s, _, _ in W.en_retard()}
    check("la session amputée est signalée", "sA" in retard)
    check("celle dont l'ancien n'avait que des doublons ne l'est PAS", "sB" not in retard,
          "un outil qui crie sans raison n'est plus lu")

    r = W.repare("sA", dry=True)
    check("--dry-run n'écrit rien", json.loads((new / "sA.json").read_text())["items"] == courant["items"])
    check("mais annonce ce qu'il ferait", r["apres"]["items"] == 3 and r["avant"]["items"] == 2)
    W.repare("sA")
    apres = json.loads((new / "sA.json").read_text(encoding="utf-8"))
    check("la réparation écrit la fusion", len(apres["items"]) == 3 and len(apres["mrs"]) == 2)
    check("et pose une sauvegarde avant d'écrire", (new / "sA.json.bak-merge").is_file(),
          "on ne répare pas une perte par une autre")
    check("rejouée, elle ne signale plus rien", "sA" not in {s for s, _, _ in W.en_retard()})
    try:
        W.repare("sZ-inexistante"); check("une session inconnue est refusée proprement", False)
    except FileNotFoundError:
        check("une session inconnue est refusée proprement", True)

print("\n[RM2992] l'outil vise le core qui TOURNE, pas le clone d'où on le lance")
src = (HERE / "pm-worklog-merge.py").read_text(encoding="utf-8")
check("PM_CORE_DIR prime sur la racine courante", 'os.environ.get("PM_CORE_DIR")' in src)
check("et c'est expliqué", "pas celui d'un clone de dev" in src)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-worklog-merge (RM2992)"))
sys.exit(1 if FAIL else 0)
