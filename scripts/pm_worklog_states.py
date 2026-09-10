"""pm_worklog_states — comment un worklog de session CLASSE ce qu'il porte. RM3085 (lot L5 de RM3015).

Ces ensembles décident de ce que le terminal (`pm-session-status`) et le cockpit (`karl-agent`)
appellent « reste à faire », « en attente », « à tester », « en MEP » ou « fait ». Ils vivaient en
DOUBLE, recopiés d'un fichier à l'autre avec le commentaire « reprises telles quelles » — et la
copie avait déjà divergé : `MEP` n'existait que d'un côté, si bien qu'un ticket `a_mep` se rangeait
ailleurs selon qu'on regardait le terminal ou l'écran. Deux vérités sur « où on en est » est
exactement ce que le worklog est censé empêcher.

Une seule définition, donc, importée des deux côtés. Stdlib seulement : `karl-agent.py` l'importe.
"""

#: terminés — filtrés hors du « reste à faire »
DONE = {"fait", "done", "ferme", "fermé", "livré", "livre", "closed", "résolu", "resolu"}

#: vraiment bloqués : RIEN n'est demandé à personne d'identifié, le ticket dort
WAITING = {"en_attente", "attente", "bloqué", "bloque", "blocked", "waiting", "en_pause"}

#: RM2930 — « à tester / valider » n'est PAS une attente : c'est une action, et elle a un acteur.
#: Rangés avec les blocages, ces tickets se lisaient « c'est mort » là où il fallait lire « c'est à toi ».
TESTING = {"a_valider", "à_valider", "a_tester_demandeur", "a_tester_dev", "a_tester_preprod"}

#: RM2860 — le dev est fini, reste la mise en production : un travail d'une autre nature, souvent
#: porté par quelqu'un d'autre, donc sa propre section. `a_tester_preprod` n'en est pas (c'est une recette).
MEP = {"a_mep", "a_mep_prod", "en_mep"}

#: actifs : le flow NORMS moins ce qui précède, plus les variantes libres des chantiers hors ticket
TODO = {"nouveau", "a_etudier_chiffrer", "etude_chiffrage_en_cours", "etude_chiffrage_a_valider",
        "a_faire", "à_faire", "en_cours", "a_corriger", "todo", "à faire", "en cours"}

#: RM2621/RM2635 — statuts qui sortent une demande du « à traiter » : elle a trouvé sa suite.
#: `nouveau` est le seul qui appelle encore une décision.
REQUEST_DONE = {"ticketee", "repondu", "annulee", "fusionnee", "non_demande"}


def bucket(status: str) -> str:
    """La section d'un statut : done · mep · testing · waiting · todo. Pure.

    L'ordre des tests est la règle : `mep` et `testing` AVANT `waiting`, sinon un ticket livré qui
    attend un test retomberait dans « bloqué » — l'erreur que RM2930 a corrigée."""
    s = (status or "").strip().lower()
    if s in DONE:
        return "done"
    if s in MEP:
        return "mep"
    if s in TESTING:
        return "testing"
    if s in WAITING:
        return "waiting"
    return "todo"
