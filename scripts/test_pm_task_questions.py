#!/usr/bin/env python3
"""Tests RM3116 → RM3226 — les questions d'un ticket dans son CF Redmine 36 « Questions à trancher ».

Ce qui doit tenir : le CF est une VUE du `.think.md` ; une question tranchée s'affiche cochée AVEC la
décision qui l'a tranchée ; une coche posée à la main n'est ni ignorée, ni prise pour une réponse — elle
est signalée ; et l'ancienne section de description (RM3116) est retirée sans toucher au reste.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_think as T                                     # noqa: E402
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def q(id_, texte, state="attente", closed=False):
    return {"id": id_, "prefix": "Q", "closed": closed, "state": state, "cells": [id_, texte]}


def d(id_, texte, state="valide"):
    return {"id": id_, "prefix": "D", "closed": False, "state": state, "cells": [id_, texte]}


print("[RM3226] le contenu du CF")
parsed = {"question": {"rows": [q("Q001", "Faut-il trancher ceci ?"),
                                q("Q002", "Et cela ?", state="valide")]},
          "decision": {"rows": [d("D001", "Réponse à Q002 : on fait comme ça.")]}}
s = T.questions_text(parsed)
check("pas de marqueurs : le champ entier est la vue", T.QUESTIONS_BEGIN not in s and "<!--" not in s)
check("il compte ce qui reste ouvert", "**1 ouverte(s) sur 2**" in s)
check("une question en attente est décochée", "- [ ] **Q001**" in s)
check("une question tranchée est cochée", "- [x] **Q002**" in s)
check("et montre la DÉCISION qui l'a tranchée — sinon la trace mentirait par omission",
      "Réponse à Q002" in s.split("Q002", 1)[1])
check("il dit que trancher se fait dans le think, pas dans Redmine", "trancher se fait là, pas ici" in s)
vide = T.questions_text({})
check("un ticket sans question le DIT — jamais de CF vide (un PUT vide efface le champ)",
      vide.strip() and "Aucune question consignée" in vide)
check("une question tranchée sans décision reliée le signale",
      "la décision n'est pas reliée" in T.questions_text({"question": {"rows": [q("Q003", "x", state="valide")]}}))
check("Q001 ne matche pas Q0012 ni D-Q0010 : la citation est un mot entier",
      "→ *(tranchée" in T.questions_text({"question": {"rows": [q("Q001", "x", state="valide")]},
                                           "decision": {"rows": [d("D001", "voir Q0012")]}}))
deux = T.questions_text({"question": {"rows": [q("Q001", "x", state="valide")]},
                         "decision": {"rows": [d("D001", "Q001 : non"), d("D002", "Q001 : finalement oui")]}})
check("la DERNIÈRE décision qui cite la question fait foi (réponse corrigée)",
      "finalement oui" in deux and "Q001 : non" not in deux)
ecartee = T.questions_text({"question": {"rows": [q("Q001", "x", state="valide")]},
                            "decision": {"rows": [d("D001", "Q001 : oui"), d("D002", "Q001 : non", state="invalide")]}})
check("une décision invalidée ne sert pas de réponse", "Q001 : oui" in ecartee and "Q001 : non" not in ecartee)
check("cite_question reconnaît une réponse outillée", T.cite_question("Q004 : on garde") and not T.cite_question("rien"))

print("\n[RM3226] l'ancienne section sort de la description")
section = ("\n\n" + T.QUESTIONS_BEGIN + "\n\n## ❓ Questions ouvertes\n\n- [ ] **Q001** — x\n\n" + T.QUESTIONS_END + "\n")
desc = "## Contexte\n\nDu texte qui doit survivre.\n"
check("elle est retirée, marqueurs compris", T.QUESTIONS_BEGIN not in T.strip_questions(desc + section)
      and T.QUESTIONS_END not in T.strip_questions(desc + section))
check("ce qui la précède survit à l'identique", T.strip_questions(desc + section).strip() == desc.strip())
milieu = desc + section + "\n## Suite\n\nFin.\n"
net = T.strip_questions(milieu)
check("ce qui la suit survit aussi", "## Suite" in net and "Fin." in net and "Du texte" in net)
check("une description sans section est rendue telle quelle", T.strip_questions(desc) == desc)
check("retirer deux fois ne change plus rien (idempotent)", T.strip_questions(net) == net)
check("une description réduite à la section devient vide", T.strip_questions(section.strip()) == "")

print("\n[RM3116] une coche posée à la main")
cf = T.questions_text(parsed)
coche = cf.replace("- [ ] **Q001**", "- [x] **Q001**")
check("elle est DÉTECTÉE dans le CF quand le think dit la question ouverte",
      T.cochees_a_la_main(coche, parsed) == ["Q001"])
check("et encore dans une ancienne section de description",
      T.cochees_a_la_main(desc + section.replace("- [ ]", "- [x]"), parsed) == ["Q001"])
check("un CF non coché ne signale rien", T.cochees_a_la_main(cf, parsed) == [])
check("une question réellement tranchée ne remonte pas comme anomalie",
      T.cochees_a_la_main(coche, {"question": {"rows": [q("Q001", "x", state="valide")]}}) == [])
check("un texte sans case ne déclenche rien", T.cochees_a_la_main("du texte", parsed) == [])

print("\n[RM3226] l'outil et son branchement")
src = (HERE / "pm-task-questions.py").read_text(encoding="utf-8")
check("--check existe, pour servir de garde", "--check" in src)
check("--local n'écrit que le MD", '"--local"' in src)
check("le CF se résout par le contrat commun (.env puis redmine.reference.yml)", "resolve_cf_id" in src)
check("CF non résolu ⇒ la description n'est PAS vidée de ses questions", "description laissée" in src)
check("Redmine indisponible ne perd pas le MD", "MD écrit, Redmine non mis à jour" in src)
check("l'erreur réseau de fetch_issue (sys.exit) est rattrapée", "SystemExit" in src)
check("une coche à la main est expliquée à l'utilisateur", "Une coche n'est pas une réponse" in src)
check("--all parcourt vraiment les projets (cfg.tasks_dir n'existe pas)", "iter_projects" in src)
think = (HERE / "pm-task-think.py").read_text(encoding="utf-8")
check("poser une question met le CF à jour au fil de l'eau", 'kind == "question"' in think)
check("poser une décision qui cite une question aussi", "cite_question(text)" in think)
check("trancher une question aussi", "_resync_questions(a.rm_id, sheet)" in think)
check("et cela ne peut pas casser une consignation, même sur sys.exit",
      "ne doit jamais casser une consignation" in think and "SystemExit" in think)
check("PM_THINK_LOCAL permet de rester hors ligne", "PM_THINK_LOCAL" in think)
ref = (HERE.parent / "redmine.reference.yml").read_text(encoding="utf-8")
check("le CF 36 est déclaré dans redmine.reference.yml", '36: {name: "Questions à trancher"' in ref)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-task-questions (RM3116 → RM3226)"))
sys.exit(1 if FAIL else 0)
