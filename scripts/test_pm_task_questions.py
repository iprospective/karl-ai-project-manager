#!/usr/bin/env python3
"""Tests RM3116 — les questions d'un ticket dans sa description.

Ce qui doit tenir : la description est une VUE du `.think.md`, régénérée entre marqueurs ; une question
tranchée s'affiche cochée AVEC la décision qui l'a tranchée ; et une coche posée à la main n'est ni
ignorée, ni prise pour une réponse — elle est signalée.
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


print("[RM3116] la section rendue")
parsed = {"question": {"rows": [q("Q001", "Faut-il trancher ceci ?"),
                                q("Q002", "Et cela ?", state="valide")]},
          "decision": {"rows": [d("D001", "Réponse à Q002 : on fait comme ça.")]}}
s = T.render_questions(parsed)
check("elle est entre marqueurs, comme les autres blocs régénérés", T.QUESTIONS_BEGIN in s and T.QUESTIONS_END in s)
check("elle compte ce qui reste ouvert", "**1 ouverte(s) sur 2**" in s)
check("une question en attente est décochée", "- [ ] **Q001**" in s)
check("une question tranchée est cochée", "- [x] **Q002**" in s)
check("et montre la DÉCISION qui l'a tranchée — sinon la trace mentirait par omission",
      "Réponse à Q002" in s.split("Q002", 1)[1])
check("elle dit que trancher se fait dans le think, pas dans la description", "trancher se fait là, pas ici" in s)
check("un ticket sans question le dit plutôt que d'afficher une section vide",
      "Aucune question consignée" in T.render_questions({}))
tranchee_sans_reponse = T.render_questions({"question": {"rows": [q("Q003", "x", state="valide")]}})
check("une question tranchée sans décision reliée le signale",
      "la décision n'est pas reliée" in tranchee_sans_reponse)

print("\n[RM3116] poser la section dans une description")
desc = "## Contexte\n\nDu texte qui doit survivre.\n"
avec = T.pose_questions(desc, parsed)
check("ce qui est hors marqueurs n'est pas touché", "Du texte qui doit survivre." in avec)
check("la section est ajoutée", T.QUESTIONS_BEGIN in avec)
parsed2 = {"question": {"rows": [q("Q001", "Faut-il trancher ceci ?", state="valide")]},
           "decision": {"rows": [d("D001", "Q001 : tranchée.")]}}
re_pose = T.pose_questions(avec, parsed2)
check("la reposer REMPLACE l'ancienne, elle ne l'empile pas", re_pose.count(T.QUESTIONS_BEGIN) == 1)
check("et le texte hors marqueurs survit encore", "Du texte qui doit survivre." in re_pose)
check("la section suit l'état réel", "- [x] **Q001**" in re_pose and "**0 ouverte(s) sur 1**" in re_pose)
check("reposer deux fois de suite ne change plus rien (idempotent)",
      T.pose_questions(re_pose, parsed2) == re_pose)

print("\n[RM3116] une coche posée à la main")
coche = avec.replace("- [ ] **Q001**", "- [x] **Q001**")
check("elle est DÉTECTÉE quand le think dit la question ouverte",
      T.cochees_a_la_main(coche, parsed) == ["Q001"])
check("une section non cochée ne signale rien", T.cochees_a_la_main(avec, parsed) == [])
check("une question réellement tranchée ne remonte pas comme anomalie",
      T.cochees_a_la_main(re_pose, parsed2) == [])
check("une description sans section ne déclenche rien", T.cochees_a_la_main("du texte", parsed) == [])
check("la coche ne vaut PAS réponse : le rendu la décoche tant que le think ne l'a pas tranchée",
      "- [ ] **Q001**" in T.pose_questions(coche, parsed))

print("\n[RM3116] l'outil et son branchement")
src = (HERE / "pm-task-questions.py").read_text(encoding="utf-8")
check("--check existe, pour servir de garde", "--check" in src)
check("--local n'écrit que le MD", '"--local"' in src)
check("Redmine indisponible ne perd pas le MD", "MD écrit, Redmine non mis à jour" in src)
check("une coche à la main est expliquée à l'utilisateur", "Une coche n'est pas une réponse" in src)
think = (HERE / "pm-task-think.py").read_text(encoding="utf-8")
check("poser une question met la section à jour au fil de l'eau", "_resync_questions" in think)
check("trancher une question aussi", think.count("_resync_questions") >= 3)
check("et cela ne peut pas casser une consignation", "ne doit jamais casser une consignation" in think)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-task-questions (RM3116)"))
sys.exit(1 if FAIL else 0)
