#!/usr/bin/env python3
"""pm_norms_anchors — ce qui doit survivre à une réécriture dense des normes (RM3073).

Densifier un texte de normes par un LLM n'est pas anodin : une règle perdue est un garde-fou perdu, et
personne ne s'en aperçoit avant l'incident. Le contrôle de non-perte de `pm-norms-doctor` compare des
lignes verbatim — inutilisable ici, puisque justement rien n'est verbatim.

Ce qui reste vérifiable, ce sont les **ancres** : les fragments qu'une réécriture n'a pas le droit de
changer parce qu'ils désignent des choses réelles. Un nom de script, un chemin, un identifiant de statut,
un numéro de garde-fou, un champ de frontmatter, une option de ligne de commande. Si une ancre disparaît,
une règle a disparu avec elle — ou pire, elle a été paraphrasée, donc rendue inapplicable.

Une paraphrase élégante qui perd `--list-next` a perdu la seule chose qui rendait la règle exécutable.
"""
import re

#: chaque motif nomme une famille d'ancres. L'ordre n'a pas d'importance, les doublons sont fusionnés.
MOTIFS = {
    "script": r"\b(?:pm|karl|redmine|mmi)-[a-z0-9-]+(?:\.py|\.sh)?\b",
    "verbe": r"\bmmi-pm [a-z0-9-]+\b",
    "option": r"(?<![\w-])--[a-z][a-z0-9-]{2,}\b",
    "chemin": r"\b(?:norms|scripts|agents|skills|knowledge|templates|deploy)/[A-Za-z0-9_./*-]+",
    "fichier": r"\b[A-Za-z0-9_.-]+\.(?:md|yml|yaml|json|tsv|env)\b",
    "module_py": r"\bpm_[a-z_]+\.[A-Za-z_]+\b",
    "statut": r"\b(?:nouveau|a_etudier_chiffrer|a_faire|en_cours|a_tester_dev|a_tester_demandeur|"
              r"a_tester_preprod|a_mep|en_mep|ferme|a_corriger|en_pause)\b",
    "champ": r"\b(?:redmine_id|schema_version|status_history|done_ratio|assigned_to|close_reason|"
             r"target_env|updated|est_tokens|requires_agent_test)\b",
    "env": r"\b[A-Z][A-Z0-9_]{4,}\b",
}
#: mots en capitales qui ne désignent rien de vérifiable : les exiger produirait du bruit, pas de la sûreté
BRUIT = {"NORMS", "KERNEL", "JAMAIS", "TOUJOURS", "AVANT", "APRES", "APRÈS", "SEUL", "SEULE", "QUAND",
         "TOUT", "TOUTE", "RIEN", "AUCUN", "AUCUNE", "MAIS", "DONC", "ATTENTION", "IMPORTANT", "NOTE",
         "OBLIGATOIRE", "INTERDIT", "EXCEPTION", "LECTURE", "ECRITURE", "ÉCRITURE", "MÊME", "MEME",
         "CETTE", "CHAQUE", "PLUS", "MOINS", "FAUX", "VRAI", "OUI", "NON", "PROD", "DEV", "TEST"}


def ancres(texte: str) -> set:
    """Les ancres d'un texte, normalisées en minuscules pour la comparaison."""
    out = set()
    for nom, motif in MOTIFS.items():
        for m in re.findall(motif, texte or ""):
            v = m.strip()
            if nom == "env" and (v in BRUIT or "_" not in v):
                continue          # un mot crié n'est pas une variable d'environnement
            if len(v) > 2:
                out.add(v.lower())
    return out


def _presente(ancre: str, cibles: set, texte: str) -> bool:
    """Une ancre compte comme gardée si elle est là telle quelle — ou, pour un module, sous son nom nu :
    le runtime dit « git-mep » là où la source dit « modules/git-mep.md », et c'est la même chose."""
    if ancre in cibles:
        return True
    if ancre.endswith(".md"):
        nu = ancre.rsplit("/", 1)[-1][:-3]
        return nu in cibles or nu in texte
    return False


def manquantes(source: str, runtime: str) -> list:
    """Les ancres de la source absentes du runtime, triées. Vide = rien de vérifiable n'a été perdu."""
    cibles, txt = ancres(runtime), (runtime or "").lower()
    return sorted(a for a in ancres(source) if not _presente(a, cibles, txt))


def couverture(source: str, runtime: str) -> tuple:
    """(gardées, total, manquantes) — de quoi dire un taux plutôt qu'un simple oui/non.

    À faire porter sur le CORPUS, pas fichier à fichier : déplacer une règle du KERNEL vers un module est
    précisément ce que le découpage cherche, et l'interdire viderait l'exercice de son sens."""
    a = ancres(source)
    m = manquantes(source, runtime)
    return len(a) - len(m), len(a), m
