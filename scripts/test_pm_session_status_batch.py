#!/usr/bin/env python3
"""Tests RM3208 (W1) — `pm-session-status batch` : le lot de tickets en CLI.

Le cockpit compose une consigne de lot (traiter / passer à tester / analyser) et l'envoie dans le terminal de
la session attachée. Sans cockpit, la même consigne doit s'obtenir en CLI, lue sur les fiches.

Ce qui doit tenir :
- statut, titre et critères NON cochés viennent de la fiche ; le champ `acceptance` prime sur le corps ;
- `RM123` et `123` désignent le même ticket, un doublon ne part qu'une fois, un ticket introuvable est NOMMÉ ;
- ce qui est écarté l'est avec sa raison ; rien ne part s'il n'y a rien d'actionnable ;
- au-delà du plafond, il faut `--allow-large` ; un mode inconnu est refusé ;
- la consigne est celle du cockpit (même module `pm_batch`).
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core   # noqa: E402
hermetic_core()
import pm_batch   # noqa: E402

spec = importlib.util.spec_from_file_location("pm_session_status", HERE / "pm-session-status.py")
pss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pss)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def fiche(d, rm, status, title, body="", acceptance=None):
    p = pathlib.Path(d) / f"RM{rm}_x.md"
    acc = "" if acceptance is None else "acceptance: |\n" + "".join(f"  {l}\n" for l in acceptance.splitlines())
    p.write_text(f"---\nredmine_id: {rm}\ntitle: {title}\nstatus: {status}\n{acc}---\n\n{body}\n", encoding="utf-8")
    return p


def main():
    with tempfile.TemporaryDirectory() as d:
        paths = {
            101: fiche(d, 101, "a_faire", "Premier", "## Critères\n- [x] fait\n- [ ] reste A\n- [ ] reste B\n"),
            102: fiche(d, 102, "a_tester_demandeur", "Chez le demandeur", "- [ ] x\n"),
            103: fiche(d, 103, "en_cours", "Champ dédié", "- [ ] copie périmée du corps\n",
                       acceptance="- [ ] critère du champ\n- [x] déjà fait"),
        }
        find = lambda rm: paths.get(rm)

        print("items lus sur les fiches")
        items, missing = pss.batch_items(["RM101", "101", "102", "103", "RM999", "abc"], find)
        by = {i["rm_id"]: i for i in items}
        check("doublon RM101/101 fusionné", [i["rm_id"] for i in items] == ["101", "102", "103"], [i["rm_id"] for i in items])
        check("introuvables nommés", missing == ["RM999", "abc"], missing)
        check("statut et titre", by["101"]["status"] == "a_faire" and by["101"]["title"] == "Premier", by["101"])
        check("seuls les critères non cochés", by["101"]["points"] == ["reste A", "reste B"], by["101"]["points"])
        check("le champ acceptance prime sur le corps", by["103"]["points"] == ["critère du champ"], by["103"]["points"])

        print("rendu")
        rc, text = pss.batch_render(items, missing, "traiter", False)
        check("code 0", rc == 0, text)
        check("écarté avec sa raison", "RM102" in text and pm_batch.BATCH_SKIP["a_tester_demandeur"] in text, text)
        check("introuvable signalé", "RM999" in text and "introuvable" in text, text)
        check("consigne = celle du module partagé",
              pm_batch.batch_prompt(pm_batch.batch_plan(items, "traiter")["todo"], "traiter") in text)
        check("le ticket et son titre sont dans la consigne", "RM101" in text and "Premier" in text, text)

        rc, text = pss.batch_render([by["102"]], [], "traiter", False)
        check("rien d'actionnable → code 1, rien ne part", rc == 1 and "aucun ticket actionnable" in text, text)

        big = [{"rm_id": str(500 + i), "status": "a_faire", "title": f"t{i}", "points": []}
               for i in range(pm_batch.BATCH_MAX + 1)]
        rc, text = pss.batch_render(big, [], "traiter", False)
        check("au-delà du plafond sans --allow-large → code 2", rc == 2 and "--allow-large" in text, text)
        rc, _ = pss.batch_render(big, [], "traiter", True)
        check("avec --allow-large → part", rc == 0)

        rc, text = pss.batch_render(items, [], "atester", False)
        check("mode atester : autre table d'actions", rc == 0 and "RM102" in text, text)
        try:
            pss.batch_render(items, [], "inconnu", False)
            check("mode inconnu refusé", False)
        except pm_batch.BatchError:
            check("mode inconnu refusé", True)

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
