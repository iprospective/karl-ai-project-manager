"""pm_batch — composer un lot de tickets pour un agent : plan et consigne (RM2716, extrait par RM3208 W1).

Le geste « traiter / passer à tester / analyser ces tickets » existait dans le cockpit, sa logique enfermée
dans le serveur web : sans cockpit, aucune commande ne produisait la consigne. Elle vit ici, sans I/O, et sert
deux appelants : le cockpit (qui l'envoie dans le terminal de la session attachée) et
`pm-session-status batch` (qui l'affiche pour la session courante).

Rien de ce module ne lit le disque ni le réseau : entrées = items (rm_id, status, title, points, scope),
sorties = plan et texte. Les tests historiques (`test_karl_agent_batch*.py`) passent par le cockpit, qui
réexporte ces noms à l'identique.
"""
import re


class BatchError(ValueError):
    """Demande de lot invalide (mode inconnu). Le cockpit la traduit en HTTP 400."""


# ── RM2716 : traiter en série des tickets choisis dans le worklog ─────────────
# Le geste : cocher des tickets, cliquer « traiter », et la SESSION ATTACHÉE
# enchaîne — aucune session créée. La composition de la consigne vit ici, pas
# dans le cockpit : le mapping statut → action, le plafond et les exclusions sont
# des règles métier, elles doivent être testables sans navigateur.
BATCH_MAX = 10          # au-delà : confirmation explicite (`allow_large`)

# RM2719 — portée RESTREINTE : ne faire traiter que certains points d'un ticket
# (ses critères d'acceptation non cochés, exposés par RM2695). Deux listes, à ne
# pas confondre : `points` = ce qu'on PROPOSE de cocher (repris tel quel pour
# l'écran de confirmation), `scope` = ce qui est RETENU (la restriction). Absent
# ⇒ ticket entier, comportement de RM2716 inchangé.
BATCH_POINTS_MAX = 12   # points repris dans la consigne, par ticket
BATCH_POINT_LEN = 300   # un critère est une ligne, pas un paragraphe


def _batch_points(raw, limit=BATCH_POINTS_MAX):
    """Nettoie une liste de points : une ligne chacun, borné, dédoublonné,
    plafonné. Rend (points, nombre de points laissés de côté) — le reste du code
    ANNONCE ce nombre : une liste tronquée en silence se lirait comme la liste
    complète, et l'agent clôturerait un ticket dont il n'a pas vu la fin."""
    out, seen = [], set()
    for p in raw or []:
        t = " ".join(str(p or "").split())
        if not t or t in seen:
            continue
        seen.add(t)
        if len(t) > BATCH_POINT_LEN:
            t = t[:BATCH_POINT_LEN - 1].rstrip() + "…"
        out.append(t)
    return out[:limit], max(0, len(out) - limit)

# Ce qu'on demande à l'agent, par statut de départ. Aligné sur le flux NORMS :
# une étude se termine en validation, un dev se termine en test demandeur.
BATCH_ACTIONS = {
    # RM2786 : l'étude reste ici — un lot « traiter » sur un ticket pas encore
    # chiffré doit continuer de faire ce qu'il faisait. Le bouton « analyser »
    # (mode `etudier`) la propose SÉPARÉMENT, ce que l'UI ne pouvait pas faire
    # tant que les deux vivaient dans la même table.
    "nouveau": ("etudier", "étudier et chiffrer, puis soumettre l'étude à validation"),
    "a_etudier_chiffrer": ("etudier", "étudier et chiffrer, puis soumettre l'étude à validation"),
    "etude_chiffrage_en_cours": ("etudier", "terminer l'étude et la soumettre à validation"),
    "a_faire": ("traiter", "traiter puis livrer (MR + passage en test demandeur)"),
    "en_cours": ("traiter", "reprendre là où c'en est, puis livrer"),
    "a_corriger": ("traiter", "corriger ce qui est remonté, puis relivrer"),
    "a_tester_dev": ("tester", "faire la passe de test agent et router selon le verdict"),
}
# Statuts où l'agent n'a RIEN à faire : la balle est chez le demandeur, en MEP,
# ou le ticket est clos. Les inclure enverrait l'agent tourner à vide.
BATCH_SKIP = {
    "a_tester_demandeur": "attend TON verdict, pas celui de l'agent",
    "a_mep": "attend une mise en production",
    "en_mep": "mise en production en cours",
    "en_pause": "en pause — à relancer explicitement",
    "ferme": "fermé",
}

# RM2720 — second MODE de lot : « passe ces tickets à tester ». Ce n'est pas un
# changement de statut en masse : rendre un ticket au demandeur, c'est le
# LIVRER (note de livraison + protocole de test, NORMS RM2229). Le mode a donc
# sa propre table de statuts éligibles — et une étude n'y est pas : elle se rend
# en validation, pas en test.
BATCH_ATESTER = {
    "en_cours": ("livrer", "livrer : note de livraison + protocole de test, puis "
                           "statut à tester approprié (a_tester_dev / a_tester_demandeur "
                           "selon requires_agent_test)"),
    "a_corriger": ("livrer", "relivrer la correction : note + protocole, puis statut "
                             "à tester approprié"),
    "a_faire": ("livrer", "VÉRIFIER d'abord que le travail est réellement fait "
                          "(branche, MR, critères) ; si oui livrer, sinon ne rien "
                          "changer et le dire"),
    "a_tester_dev": ("tester", "faire la passe de test agent, puis router selon le "
                               "verdict (a_tester_demandeur si OK)"),
}
BATCH_ATESTER_SKIP = {
    "a_tester_demandeur": "déjà en test chez toi",
    "a_mep": "attend une mise en production",
    "en_mep": "mise en production en cours",
    "ferme": "fermé",
    "nouveau": "pas encore pris en charge : rien à livrer",
    "a_etudier_chiffrer": "à étudier : une étude se rend en validation, pas en test",
    "etude_chiffrage_en_cours": "étude en cours : elle se rend en validation, pas en test",
    "etude_chiffrage_a_valider": "étude déjà rendue : attend TA validation",
}

# RM2786 — troisième MODE : « analyser », c'est-à-dire l'ÉTUDE/CHIFFRAGE PM
# (estimation, critères d'acceptation, ROI). L'action existait déjà dans la table
# « traiter », mais noyée : impossible de la proposer seule, et impossible de
# savoir depuis l'UI si elle avait un sens pour la sélection.
BATCH_ETUDIER = {
    "nouveau": ("etudier", "étudier et chiffrer, puis soumettre l'étude à validation"),
    "a_etudier_chiffrer": ("etudier", "étudier et chiffrer, puis soumettre l'étude à validation"),
    "etude_chiffrage_en_cours": ("etudier", "terminer l'étude et la soumettre à validation"),
}
BATCH_ETUDIER_SKIP = {
    "etude_chiffrage_a_valider": "étude déjà rendue : attend TA validation",
    "a_faire": "déjà chiffré et prêt à faire",
    "en_cours": "déjà en cours de réalisation",
    "a_corriger": "livré puis renvoyé : c'est une correction, pas une étude",
    "a_tester_dev": "livré, en test agent",
    "a_tester_demandeur": "livré, attend ton verdict",
    "a_mep": "attend une mise en production",
    "en_mep": "mise en production en cours",
    "en_pause": "en pause — à relancer explicitement",
    "ferme": "fermé",
}

# Un mode = une table d'actions + une table d'exclusions motivées. Le reste du
# lot (plafond, portée, envoi, garde de session) ne change pas.
BATCH_MODES = {
    "traiter": {"actions": BATCH_ACTIONS, "skip": BATCH_SKIP},
    "atester": {"actions": BATCH_ATESTER, "skip": BATCH_ATESTER_SKIP},
    "etudier": {"actions": BATCH_ETUDIER, "skip": BATCH_ETUDIER_SKIP},
}


#: Statuts d'où « fermer / résolu » a un sens : le travail est livré et attend
#: un verdict ou une MEP. Fermer ailleurs, c'est clore ce qui n'a pas été fait.
CLOSABLE_STATUSES = {"a_tester_dev", "a_tester_demandeur", "a_mep", "en_mep"}


# >>> batch_modes_for — pure (testée par test_karl_agent_batch_actions.py)
def batch_modes_for(statuses):
    """RM2786 : pour une sélection de statuts, combien de tickets chaque mode
    concerne — c'est ce qui décide des boutons à AFFICHER, et du compte à écrire
    dessus.

    Un lot est presque toujours mixte : le bouton s'affiche dès qu'un ticket le
    justifie, et son compteur annonce les tickets CONCERNÉS, pas le total coché.
    « traiter (3) » sur 5 sélectionnés dit la vérité ; « (5) » ment sur ce qui
    va partir.

    Un statut INCONNU compte pour tous les modes : mieux vaut un bouton de trop
    qu'une action devenue inatteignable parce qu'un statut a changé de nom — le
    plan de lot, lui, écartera le ticket avec sa raison.
    """
    connus = set()
    for m in BATCH_MODES.values():
        connus |= set(m["actions"]) | set(m["skip"])
    out = {name: 0 for name in BATCH_MODES}
    out["fermer"] = 0
    for st in (statuses or []):
        st = str(st or "").lower()
        inconnu = st not in connus
        for name, m in BATCH_MODES.items():
            if inconnu or st in m["actions"]:
                out[name] += 1
        # « fermer / résolu » n'est pas une consigne à l'agent : c'est le verdict
        # du demandeur sur un ticket LIVRÉ. Il n'a de sens que là.
        if inconnu or st in CLOSABLE_STATUSES:
            out["fermer"] += 1
    return out
# <<< batch_modes_for


# >>> batch_plan — pure (testée par test_karl_agent_batch.py)
def batch_plan(items, mode: str = "traiter") -> dict:
    """Répartit les tickets demandés entre CE QUI PART et ce qui est écarté.

    Rien n'est écarté en silence : chaque exclusion porte sa raison, que l'UI
    affiche avant l'envoi. Un statut inconnu (nouveau statut NORMS pas encore
    connu ici) est écarté aussi — deviner l'action à faire sur un ticket serait
    pire que de le dire.

    RM2719 — un item peut porter une PORTÉE : `scope` = les seuls points à
    traiter. Absente, le ticket part en entier (RM2716). Présente mais VIDE,
    le ticket est écarté avec sa raison — décocher tous les points d'un ticket
    veut dire « rien à y faire », pas « fais tout ».

    RM2720 — `mode` choisit la table d'actions : « traiter » (défaut) ou
    « atester » (rendre au demandeur). Un mode inconnu est refusé plutôt que
    rabattu sur le défaut : envoyer « traite ces tickets » à qui a demandé
    « passe-les à tester » serait la pire des tolérances."""
    m = BATCH_MODES.get(mode)
    if m is None:
        raise BatchError(f"mode de lot inconnu : {mode}")
    actions, skips = m["actions"], m["skip"]
    todo, skipped = [], []
    seen = set()
    for it in items or []:
        rm = re.sub(r"^RM", "", str((it or {}).get("rm_id") or "").strip())
        if not rm.isdigit() or rm in seen:
            continue
        seen.add(rm)
        status = str((it or {}).get("status") or "").strip()
        act = actions.get(status)
        raw_scope = (it or {}).get("scope")
        scoped = isinstance(raw_scope, list)
        scope, scope_cut = _batch_points(raw_scope) if scoped else ([], 0)
        if act and scoped and not scope:
            skipped.append({"rm_id": rm, "status": status,
                            "reason": "aucun point retenu dans la sélection",
                            "title": (it or {}).get("title") or ""})
            continue
        if act:
            points, pcut = _batch_points((it or {}).get("points"))
            todo.append({"rm_id": rm, "status": status, "action": act[0],
                         "instruction": act[1], "title": (it or {}).get("title") or "",
                         "points": points, "scope": scope,
                         "scope_truncated": scope_cut,
                         # La liste des critères peut déjà arriver incomplète du
                         # worklog (plafond de `parse_checklist`) : on le REDIT
                         # ici, sinon l'écran de sélection se lirait comme la
                         # liste complète des points du ticket.
                         "points_truncated": bool(pcut or (it or {}).get("points_truncated"))})
        else:
            todo_reason = skips.get(status) or f"statut « {status or '?'} » : aucune action définie"
            skipped.append({"rm_id": rm, "status": status, "reason": todo_reason,
                            "title": (it or {}).get("title") or ""})
    return {"todo": todo, "skipped": skipped}
# <<< batch_plan


# >>> batch_prompt — pure (testée par test_karl_agent_batch.py)
def batch_prompt(todo, mode: str = "traiter") -> str:
    """La consigne envoyée à l'agent. Elle est AUTO-PORTANTE : l'agent qui la
    reçoit ne voit pas l'écran d'où elle vient.

    Elle exige les trois retours arbitrés : le statut de fin du flux NORMS (qui
    réattribue au demandeur), la notification de fin de lot, et le récapitulatif
    au worklog. Sans ça, « traite ces tickets » laisserait le demandeur surveiller
    des sessions pour savoir où ça en est.

    RM2719 — un ticket à PORTÉE RESTREINTE porte ses points sous sa ligne, et la
    règle qui va avec : il ne se clôture pas et ne repart pas au demandeur tant
    qu'il en reste. La règle n'est ajoutée que s'il y a au moins un ticket
    restreint — une consigne qui liste des cas absents se lit moins bien.

    RM2720 — en mode « atester », la consigne dit autre chose : rendre un ticket
    au demandeur, c'est le LIVRER. Elle exige donc la note de livraison et le
    protocole de test, et interdit de bouger le statut d'un ticket dont le
    travail n'est pas réellement livré. La fin (worklog, notification, bilan)
    est commune aux deux modes.

    RM2762 — **à UN seul ticket il n'y a pas de lot**, et le mot disparaît. Tout le
    cadre de série (« EN SÉRIE, dans cet ordre », « un ticket à la fois », « passe au
    suivant », « bilan ticket par ticket », notification de fin de lot) n'a alors pas
    d'objet : le garder noie l'unique consigne utile sous des règles qui ne
    s'appliquent à rien. Ce qui est substantiel est conservé — protocole NORMS,
    statut de fin, interdiction de forcer, portée restreinte."""
    n = len(todo or [])
    solo = n == 1
    lignes = []
    scoped = False
    for i, t in enumerate(todo or [], 1):
        titre = (" — " + t["title"]) if t.get("title") else ""
        puce = "" if solo else f"{i}. "      # rien à ordonner : pas de numérotation
        lignes.append(f"{puce}RM{t['rm_id']} [{t['status']}]{titre} → {t['instruction']}")
        pts = t.get("scope") or []
        if pts:
            scoped = True
            lignes.append("   PORTÉE RESTREINTE — ne traite QUE ces points :")
            lignes += [f"   - {p}" for p in pts]
            cut = t.get("scope_truncated") or 0
            if cut:
                lignes.append(f"   ({cut} autre(s) point(s) retenu(s) mais non repris "
                              "ici : reprends-les depuis la checklist du ticket.)")
    corps = "\n".join(lignes)
    regle_scope = ((
        "- à PORTÉE RESTREINTE, le ticket ne se clôture PAS et ne repart PAS au "
        "demandeur : traite uniquement les points listés, ne coche que ces "
        "critères-là, laisse-le en `en_cours` et dis en note ce qui reste ;\n"
    ) if solo else (
        "- un ticket à PORTÉE RESTREINTE ne se clôture PAS et ne repart PAS au "
        "demandeur : traite uniquement les points listés, ne coche que ces "
        "critères-là, laisse le ticket en `en_cours` et dis en note ce qui reste ;\n"
    )) if scoped else ""
    # Fin commune : sans ces trois retours, un lot laisse le demandeur
    # surveiller des sessions pour savoir où ça en est.
    # `--kind autre` et pas `--kind lot` : `lot` n'existe pas dans NOTIFY_KINDS
    # (pm-session-status.py), la commande échouait donc telle qu'écrite (RM2762).
    fin = (
        "- consigne l'avancement du lot au worklog "
        "(`pm-session-status.py set <ref> <statut>`) au fil de l'eau ;\n"
        "- si un ticket te bloque (question, dépendance, ambiguïté), NE FORCE PAS : "
        "consigne le blocage, passe au suivant, et rends-le dans le bilan ;\n"
        "- à la fin du lot, notifie : `pm-session-status.py notify --level info "
        "--kind autre \"lot terminé : <n> rendu(s), <n> bloqué(s)\"`, puis donne le "
        "bilan ticket par ticket."
    )
    # Fin SOLO : pas de notification de fin de lot — le statut de fin réattribue déjà
    # au demandeur, et un « lot terminé : 1 rendu » n'apprend rien à personne.
    solo_worklog = ("- consigne l'avancement au worklog "
                    "(`pm-session-status.py set <ref> <statut>`) au fil de l'eau ;\n")
    solo_bloc = ("- s'il te bloque (question, dépendance, ambiguïté), NE FORCE PAS : consigne "
                 "le blocage, laisse le ticket en l'état et dis-le dans ton compte rendu ;\n")
    solo_cr = "- termine par un compte rendu : ce qui a été fait, ce qui reste."
    fin_solo = solo_worklog + solo_bloc + solo_cr
    # En mode « atester », la règle « travail non livré → ne force pas » couvre déjà
    # le blocage : répéter NE FORCE PAS deux puces plus bas se lit comme du remplissage.
    fin_solo_atester = solo_worklog + solo_cr
    if mode == "atester":
        if solo:
            return (
                "Passe ce ticket « à tester » en appliquant le protocole worker "
                "NORMS :\n"
                f"{corps}\n\n"
                "Règles :\n"
                "- passer un ticket « à tester », c'est le LIVRER : il part avec sa "
                "note de livraison ET son protocole de test (norme RM2229) — pas un "
                "simple changement de statut ;\n"
                "- si le travail n'est PAS réellement livré (branche non poussée, MR "
                "absente, critères d'acceptation non cochés), NE FORCE PAS : laisse "
                "le statut en l'état et dis pourquoi ;\n"
                f"{fin_solo_atester}"
            )
        return (
            f"Passe ces {n} ticket(s) « à tester », un par un, en appliquant le "
            "protocole worker NORMS :\n"
            f"{corps}\n\n"
            "Règles du lot :\n"
            "- passer un ticket « à tester », c'est le LIVRER : chacun part avec sa "
            "note de livraison ET son protocole de test (norme RM2229) — pas un "
            "simple changement de statut ;\n"
            "- si le travail n'est PAS réellement livré (branche non poussée, MR "
            "absente, critères d'acceptation non cochés), NE FORCE PAS : laisse le "
            "statut en l'état, dis pourquoi, passe au suivant ;\n"
            "- un ticket à la fois, jusqu'à son statut de fin ;\n"
            f"{fin}"
        )
    if solo:
        return (
            "Traite ce ticket en appliquant le protocole worker NORMS "
            "(prise en charge, travail, livraison) :\n"
            f"{corps}\n\n"
            "Règles :\n"
            "- il revient au demandeur par son statut de fin NORMS "
            "(étude → etude_chiffrage_a_valider, dev → a_tester_demandeur) ;\n"
            f"{regle_scope}"
            f"{fin_solo}"
        )
    return (
        f"Traite ces {n} ticket(s) EN SÉRIE, dans cet ordre, en "
        "appliquant le protocole worker NORMS à chacun (prise en charge, travail, "
        "livraison) :\n"
        f"{corps}\n\n"
        "Règles du lot :\n"
        "- un ticket à la fois, jusqu'à son statut de fin ; ne passe au suivant "
        "qu'une fois le précédent rendu ;\n"
        "- chaque ticket revient au demandeur par son statut de fin NORMS "
        "(étude → etude_chiffrage_a_valider, dev → a_tester_demandeur) ;\n"
        f"{regle_scope}"
        f"{fin}"
    )
# <<< batch_prompt


# >>> parse_checklist — pure (testée par test_karl_agent_worklog_checklist.py)
_CHECKLIST_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.*\S)\s*$")


def parse_checklist(body: str, max_items: int = 40, acceptance: str = None) -> dict:
    """RM2695 : l'avancement d'un ticket, lu là où il est DÉJÀ tenu — la
    checklist des critères d'acceptation de sa description (tripwire #9
    « description vivante », miroir du `done_ratio`).

    Aucun référentiel de tâches à créer : un second endroit à maintenir
    divergerait du premier en une semaine. On lit `- [ ]` / `- [x]`, puces `*` et
    `+` comprises, indentation tolérée (sous-items d'une liste).

    `items` est plafonné (l'UI n'affiche que le RESTE à faire, et une description
    n'est pas un backlog) ; `done`/`total` comptent tout, eux, sinon le compteur
    mentirait sur les tickets longs.

    RM2882 — `acceptance` est le champ dédié (miroir du CF 33). Non vide, il fait foi :
    le corps du MD n'en garde alors qu'une copie, que plus rien ne met à jour. Vide, on
    lit le corps exactement comme avant : un ticket non migré s'affiche à l'identique."""
    done = total = 0
    items = []
    source = acceptance if (acceptance or "").strip() else body
    for line in (source or "").splitlines():
        m = _CHECKLIST_RE.match(line)
        if not m:
            continue
        checked = m.group(1) in ("x", "X")
        total += 1
        if checked:
            done += 1
        elif len(items) < max_items:
            items.append(m.group(2))
    return {"done": done, "total": total, "items": items,
            "truncated": total - done > len(items)}
# <<< parse_checklist
