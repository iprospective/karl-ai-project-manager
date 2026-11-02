#!/usr/bin/env python3
"""pm-timesheet — reconstitue et note le temps de travail HUMAIN (RM2890).

    mmi-pm timesheet --month 2026-08              # calcule → rapport .md + proposition .yml
    $EDITOR var/timesheet/2026-08.yml             # on relit, on amende
    mmi-pm timesheet --month 2026-08 --apply      # crée les saisies dans Redmine

Le calcul lit les traces laissées par le travail assisté (transcripts Claude
Code, `history.jsonl`, bases opencode, journaux `.log.md` des tickets), en déduit
les périodes de travail effectives, répartit le temps par client / projet /
ticket, refacture le transversal aux clients du jour et retranche ce qui est déjà
saisi à la main. **Aucun modèle n'est appelé : 0 token, quelques secondes.**

Rien ne part dans Redmine sans validation : le `.yml` amendé est la source de
vérité de `--apply`, qui est idempotent (une ligne déjà posée n'est jamais
recréée).

Détail des règles et de leur justification :
`docs/cdc-rm2890-timesheet-heures-humaines.md` (projet PM `pm-ai-agents`).
"""
import argparse
import calendar
import collections
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_timesheet as W
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


def _periode(args):
    if getattr(args, "day", None):
        debut = datetime.fromisoformat(args.day)
        return debut, debut + timedelta(days=1), args.day
    if args.month:
        an, mois = (int(x) for x in args.month.split("-"))
        debut = datetime(an, mois, 1)
        fin = datetime(an + (mois == 12), (mois % 12) + 1, 1)
        return debut, fin, args.month
    debut = datetime.fromisoformat(args.depuis)
    fin = datetime.fromisoformat(args.jusqu_a) + timedelta(days=1)
    return debut, fin, f"{args.depuis}_{args.jusqu_a}"


def _sources(conf):
    """Sources déclarées, ou les emplacements par défaut de cette machine."""
    src = conf.get("sources")
    if src:
        return src
    home = Path.home()
    return [
        {"kind": "claude-transcripts", "path": str(home / ".claude/projects")},
        {"kind": "claude-history", "path": str(home / ".claude/history.jsonl")},
        {"kind": "opencode-db", "path": str(home / ".local/share/opencode/opencode.db")},
    ]


def collecter(conf, debut, fin, verbose=False, cache_dir=None, cfg=None):
    events, detail, absentes = [], [], []
    # Prompts automatiques propres à CETTE installation : un CRON qui ouvre une session
    # chaque matin laisse un texte parfaitement régulier, qui ressemble à une demande
    # mais n'en est pas une. Sans cette liste, un prompt isolé à 6h30 un samedi fabrique
    # une journée de travail entière (RM3530).
    exclusions = conf.get("exclure_prompts") or []
    for s in _sources(conf):
        kind, chemin = s.get("kind"), str(Path(s.get("path", "")).expanduser())
        avant = len(events)
        if s.get("host"):
            local = W.rapatrier(s["host"], s.get("path"), cache_dir or Path("."),
                                kind, verbose)
            if not local:
                absentes.append(f"{s['host']}:{s.get('path')}")
                continue
            chemin = local
        if kind == "claude-transcripts":
            events += W.collect_claude_transcripts(chemin, debut, fin, exclusions)
        elif kind == "claude-history":
            events += W.collect_claude_history(chemin, debut, fin, exclusions)
        elif kind == "opencode-db":
            events += W.collect_opencode(chemin, debut, fin, exclusions=exclusions)
        elif kind == "redmine-actions":
            # Créer, commenter, modifier un ticket : des gestes humains horodatés,
            # rattachés à un ticket certain. Seule source qui voit une journée de
            # régie, où le travail se trace dans le Redmine du client.
            try:
                url, key, basic, uid = _instance_creds(s, cfg)
            except Exception as e:
                absentes.append(f"{s.get('instance')} ({type(e).__name__})")
                continue
            events += W.collect_redmine_actions(
                url, key, basic, uid, debut, fin,
                project_map={k: tuple(v) for k, v in (s.get("project_map") or {}).items()},
                instance=s.get("instance"))
        else:
            continue
        # Un compte partagé porte le travail de plusieurs personnes (dercya-www :
        # Mathieu ET Yann, sans marqueur technique pour les distinguer). Les
        # journées qui ne sont pas les siennes s'excluent explicitement, source
        # par source — un tri deviné sur du temps facturable n'aurait pas sa place.
        exclus = set(str(j) for j in (s.get("exclude_days") or []))
        gardes = set(str(j) for j in (s.get("only_days") or []))
        if exclus or gardes:
            nouveaux = events[avant:]
            del events[avant:]
            events += [e for e in nouveaux
                       if e.ts.strftime("%Y-%m-%d") not in exclus
                       and (not gardes or e.ts.strftime("%Y-%m-%d") in gardes)]
        detail.append((kind, chemin, len(events) - avant))
    fusionnes = W.dedupe(events)
    if verbose:
        for kind, chemin, n in detail:
            print(f"  {n:5d}  {kind:20} {chemin}", file=sys.stderr)
    for a in absentes:
        print(f"  ⚠ source injoignable, ignorée : {a}", file=sys.stderr)
    return fusionnes, detail


def saisies_humaines(url, key, user_id, debut, fin, basic=None):
    """Saisies déjà faites à la main (hors « Tick IA » de l'agent)."""
    from redmine_utils import http_json
    out, offset = [], 0
    while True:
        code, body = http_json(
            "GET", f"{url}/time_entries.json?user_id={user_id}"
            f"&from={debut:%Y-%m-%d}&to={(fin - timedelta(days=1)):%Y-%m-%d}"
            f"&limit=100&offset={offset}", key, basic=basic)
        if code != 200:
            break
        for t in body.get("time_entries", []):
            if (t.get("comments") or "").startswith("Tick IA"):
                continue
            pr = t.get("project") or {}
            out.append({"jour": t["spent_on"], "minutes": float(t["hours"]) * 60,
                        "rm": str(t["issue"]["id"]) if t.get("issue") else None,
                        "entity": None, "libelle": t.get("comments") or "",
                        "projet_id": pr.get("id"), "projet_nom": pr.get("name") or ""})
        offset += 100
        if offset >= body.get("total_count", 0):
            break
    return out


_CACHE_PROJET_REDMINE = {}


def _marque_heritee(marque, deja):
    """Retrouve une saisie posée sous une FORME ANCIENNE de la marque.

    La marque s'est précisée deux fois : l'activité d'abord, puis le projet et le
    rang (2026-10-20). Sans ces replis, `[timesheet:…/-@13/infra]` ne reconnaîtrait
    pas `[timesheet:…/-@13]` déjà en base et la recréerait : un doublon de
    facturation, le défaut le plus grave que puisse avoir cet outil.

    Les formes sont essayées de la plus précise à la plus ancienne.
    """
    corps = marque[:-1] if marque.endswith("]") else marque
    formes = []
    # Le RANG fait partie de l'identité : `…+1` est une SECONDE ligne de même cible,
    # pas une autre écriture de la première. Le confondre avec elle empêchait de
    # créer le complément d'une ligne déjà partiellement posée (22/07/2026).
    if "+" in corps.split("#")[-1]:
        return None
    base = corps
    if "@" in base:
        tete, reste = base.split("@", 1)
        if "/" in reste:                       # @<activité>/<projet> → @<activité>
            formes.append(f"{tete}@{reste.split('/', 1)[0]}")
        formes.append(tete)                    # → sans activité du tout
    for f in formes:
        if f + "]" in deja:
            return f + "]"
    return None


def _marque(ligne):
    """Clé de déduplication d'une ligne.

    Une ligne sans ticket porte son activité ET son projet : deux projets d'un même
    client, le même jour, avec la même activité, partageaient sinon une marque — et
    la seconde n'était jamais écrite, prise pour un doublon de la première (constaté
    le 2026-10-20 : 4 cas sur le seul mois de septembre, dont `calicote/infra` et
    `calicote/prestashop` le 01/09).

    Le `rang` distingue ce qui reste indiscernable : deux morceaux d'une même ligne
    scindée. Il vient de l'ordre des CLÉS, stable d'un recalcul à l'autre.
    """
    base = (f"[timesheet:{ligne['jour']}#{ligne.get('client') or '-'}"
            f"/{ligne.get('ticket') or '-'}")
    if not ligne.get("ticket"):
        if ligne.get("activite"):
            base += f"@{ligne['activite']}"
        if ligne.get("projet"):
            base += f"/{ligne['projet']}"
    if ligne.get("rang"):
        base += f"+{ligne['rang']}"
    return base + "]"


def _poser_rangs(lignes):
    """Numérote les lignes qui partageraient une marque, dans l'ordre stable des clés."""
    groupes = {}
    for l in sorted(lignes, key=lambda x: str(x.get("cle") or "")):
        l.pop("rang", None)
        m = _marque(l)
        n = groupes.get(m, 0)
        groupes[m] = n + 1
        if n:
            l["rang"] = n
    return lignes


def _libelle(ligne, marque):
    """Commentaire de la saisie — court, c'est ce que le client lira.

    Le ticket porte déjà son titre dans Redmine : le répéter n'apporterait rien.
    Seule la part d'outillage mutualisé (PM, infrastructure, produits) mérite
    d'être dite, puisqu'elle est incluse dans le temps sans être visible.
    """
    if ligne.get("pause"):
        return f"{ligne.get('commentaire') or 'repas midi'} {marque}"[:255]
    # Un commentaire écrit à la main fait foi : c'est tout l'intérêt d'ajouter une
    # ligne soi-même que de pouvoir dire ce qu'elle recouvre.
    if ligne.get("commentaire"):
        return f"{ligne['commentaire']} {marque}"[:255]
    part = ligne.get("outillage_min") or 0
    if ligne.get("ticket"):
        base = "Travail assisté" + (f", dont {part} min d'outillage" if part >= 5 else "")
    else:
        base = f"{ligne.get('projet') or 'divers'}" + (
            f", dont {part} min d'outillage" if part >= 5 else "")
    return f"{base} {marque}"[:255]


def _projet_redmine(ligne, conf, cfg, url=None, key=None, basic=None):
    """Projet Redmine d'une ligne sans ticket : `project_map`, sinon le manifeste PM.

    Sans cela, tout le travail non ticketé (régie, exploration, échanges) serait
    perdu à l'écriture — or c'est précisément le temps que personne ne note.

    ⚠ L'API `time_entries` exige un **id numérique** : un identifiant textuel
    (`pisceen-presta`, ce que porte le manifeste PM) est refusé, et Redmine répond
    « Projet n'est pas valide » **suivi de** « Utilisateur n'est pas valide » —
    l'erreur en cascade fait chercher un problème de droits là où il n'y en a pas.
    On résout donc l'identifiant en id avant d'écrire.
    """
    if ligne.get("project_id"):
        # La pause vise un projet Redmine DIRECTEMENT : inventer un projet PM « interne »
        # pour y loger un repas n'aurait pas de sens.
        return ligne["project_id"]
    cle = f"{ligne.get('client')}/{ligne.get('projet')}"
    depuis_conf = (conf.get("project_map") or {}).get(cle)
    if depuis_conf:
        return depuis_conf
    if cle in _CACHE_PROJET_REDMINE:
        return _CACHE_PROJET_REDMINE[cle]
    pid = None
    client, projet = ligne.get("client"), ligne.get("projet")
    if client and projet:
        try:
            meta = cfg.project_meta(client, projet) or {}
            pid = (meta.get("redmine") or {}).get("project_id")
        except Exception:
            pid = None
    if pid and not str(pid).isdigit() and url:
        from redmine_utils import http_json
        code, corps = http_json("GET", f"{url}/projects/{pid}.json", key, basic=basic)
        pid = corps.get("project", {}).get("id") if code == 200 else None
    _CACHE_PROJET_REDMINE[cle] = pid
    return pid


def _instance_creds(source, cfg):
    """(url, key, basic, user_id) d'une source Redmine déclarée."""
    from redmine_utils import redmine_creds
    nom, uid = source.get("instance"), source.get("user_id")
    if not uid:
        raise ValueError("user_id requis")
    if not nom:
        c = redmine_creds()
        return c[0], c[1], getattr(c, "basic", None), uid
    import yaml as _y
    from pm_registry import Registry
    brut = _y.safe_load(Path(cfg.pm_dir, "pm.config.yml").read_text(encoding="utf-8"))
    inst = Registry.from_config(brut.get("providers")).get(nom)
    c = redmine_creds(instance=inst)
    return c[0], c[1], getattr(c, "basic", None), uid


def instances_redmine(conf, cfg, args):
    """[(libellé, url, key, basic, user_id)] — toutes les instances à interroger.

    Un client peut avoir SA propre instance Redmine (MatNat) : les heures qu'on y
    a déjà saisies doivent être déduites au même titre que les autres, sinon
    elles seraient proposées une deuxième fois. Une instance injoignable est
    signalée, jamais silencieuse.
    """
    from redmine_utils import redmine_creds
    sorties = []
    uid_principal = args.user_id or conf.get("user_id")
    if uid_principal:
        try:
            c = redmine_creds()
            sorties.append(("principale", c[0], c[1], getattr(c, "basic", None),
                            uid_principal))
        except SystemExit:
            pass
    declarations = conf.get("redmine_instances") or []
    if declarations:
        try:
            import yaml as _y
            from pm_registry import Registry
            brut = _y.safe_load(Path(cfg.pm_dir, "pm.config.yml").read_text(encoding="utf-8"))
            registre = Registry.from_config(brut.get("providers"))
        except Exception:
            registre = None
        for d in declarations:
            nom, uid = d.get("instance"), d.get("user_id")
            if not nom or not uid or registre is None:
                continue
            try:
                inst = registre.get(nom)
                c = redmine_creds(instance=inst)
                sorties.append((nom, c[0], c[1], getattr(c, "basic", None), uid))
            except Exception as e:
                print(f"  ⚠ instance {nom} inaccessible ({type(e).__name__}) — "
                      "ses saisies ne seront pas déduites", file=sys.stderr)
    return sorties


def calculer(args, cfg, conf):
    debut, fin, libelle = _periode(args)
    params = {**W.DEFAULTS}
    for cle in ("follow_cap", "write_max", "quantum_min",
                "work_start_hour", "work_end_hour", "client_threshold_min"):
        val = conf.get(cle)
        if val is not None:
            params[cle] = val
    if args.follow_cap is not None:
        params["follow_cap"] = args.follow_cap
    if args.quantum is not None:
        params["quantum_min"] = args.quantum

    cache_dir = Path(args.out).parent / "cache" if args.out else W.ETAT / "rapatriement"
    # Cache par jour (RM3229) : une journée TERMINÉE se relit depuis son cache au lieu
    # de rejouer tous les transcripts — c'est ce qui rend la vue journée interactive.
    # Aujourd'hui n'est jamais figé : il n'est pas fini.
    jours = [(debut + timedelta(days=i)).date().isoformat() for i in range((fin - debut).days)]
    aujourdhui = date.today().isoformat()
    items, manquants = [], []
    for j in jours:
        lu = None if getattr(args, "refresh", False) or j >= aujourdhui else W.cache_lire(j)
        if lu is None:
            manquants.append(j)
        else:
            items += lu
    detail = [("cache", str(W.ETAT / "cache"), len(items))] if items else []
    if manquants:
        d0 = datetime.fromisoformat(manquants[0])
        d1 = datetime.fromisoformat(manquants[-1]) + timedelta(days=1)
        events, det = collecter(conf, d0, d1, args.verbose, cache_dir, cfg)
        detail += det
        tours = {}
        for s in _sources(conf):
            if s.get("kind") != "claude-transcripts":
                continue
            chemin = str(Path(s.get("path", "")).expanduser())
            if s.get("host"):
                chemin = str(Path(cache_dir) /
                             __import__("re").sub(r"[^A-Za-z0-9_.@-]", "_", s["host"]) / "projects")
                if not Path(chemin).is_dir():
                    continue
            tours.update(W.rm_par_tour(chemin, d0, d1))
        frais = collections.defaultdict(list)
        for e in events:
            j = e.ts.date().isoformat()
            if j in manquants:
                frais[j].append((e, tours.get((e.session, e.ts.strftime("%Y-%m-%dT%H:%M")))))
        for j in manquants:
            if j < aujourdhui:
                W.cache_ecrire(j, frais.get(j, []))
            items += frais.get(j, [])
    # Aucune trace n'est pas une erreur : un jour férié, un week-end, une journée dont
    # les transcripts sont purgés gardent ce qui compte — ce qui est DÉJÀ dans Redmine,
    # l'agenda, la note, et le droit de clore la journée. Sortir en erreur rendait ces
    # journées-là inaccessibles à l'écran (« journée illisible », 2026-10-20).
    sans_trace = not items
    if sans_trace:
        print(f"  ⚠ aucune trace sur {libelle} — sources : "
              + ", ".join(s.get("kind", "?") for s in _sources(conf))
              + ". La journée reste consultable (déjà saisi, agenda, note).",
              file=sys.stderr)

    resolver = W.TargetResolver(cfg, path_map=conf.get("path_map"))
    for e, rm in items:
        resolver.resolve(e, rm_du_tour=rm)
    events = [e for e, _rm in items]

    regles = W.regles_depuis_config(conf, cfg)
    # Les tours d'agent sont des traces au même titre que les prompts : si l'IA a
    # travaillé, un humain l'a lancée. Indispensable au-delà de la purge des
    # transcripts, où ils sont la seule mémoire qui reste de la journée.
    events += W.evenements_des_tours(
        [t for t in resolver.ticks() if debut.date().isoformat() <= t.get("jour", "")
         <= fin.date().isoformat()], regles, resolver, params)
    events.sort(key=lambda e: e.ts)
    alloc, periodes, totaux, par_heure, par_heure_cible, segments = W.allocate(
        W.build_intervals(events, params), params)
    alloc = W.eclater_cles_multi(alloc, regles)
    final, ecarte, journal, refacture = W.repartir_transversal(alloc, regles, params)

    deduit, toutes, slugs, activites = [], [], {}, {}
    if not args.sans_deduction:
        for nom, url, key, basic, uid in instances_redmine(conf, cfg, args):
            saisies = saisies_humaines(url, key, uid, debut, fin, basic)
            if not slugs:
                slugs = slugs_projets_redmine(url, key, basic)
            if not activites:
                activites = activites_redmine(url, key, basic)
            if args.verbose:
                print(f"  {len(saisies):5d}  saisies humaines à déduire "
                      f"({nom})", file=sys.stderr)
            toutes += saisies
        if toutes:
            final, deduit = W.deduire_saisies(final, toutes)

    # Les journées de régie complètent APRÈS la déduction : ce qui est déjà saisi
    # à la main compte dans le plancher, il ne s'y ajoute pas.
    surcharges = {}
    for mois in sorted({j[:7] for j in jours}):
        surcharges.update(W.surcharges_charger(mois))
    presences = W.presences_effectives(conf.get("presences"), surcharges)
    # La pause habituelle d'une journée de présence (« chez matnat, 12h30-13h30 ») :
    # un DÉFAUT, calculé à la volée. Il ne va pas dans l'état — sinon il s'y figerait
    # et survivrait à un changement d'horaires. Une pause notée à la main l'emporte.
    pauses_defaut = W.pauses_par_presence(conf.get("presences"), debut.date(),
                                          (fin - timedelta(days=1)).date(), surcharges)
    surcharges_vues = {j: {**(surcharges.get(j) or {}), **v}
                       for j, v in pauses_defaut.items()}
    for j, v in (surcharges or {}).items():
        surcharges_vues.setdefault(j, v)
    deja_par_jour = collections.Counter()
    for sa in toutes:
        deja_par_jour[sa["jour"]] += float(sa["minutes"])
    ajouts, transferts = W.appliquer_presences(final, presences, debut, fin, par_heure,
                                               par_heure_cible, deja_par_jour)
    for (jour, cible, motif), minutes in ajouts.items():
        final[(jour, cible)] = final.get((jour, cible), 0) + minutes

    return {"resolver": resolver, "items": items, "segments": segments,
            "ajouts": ajouts, "transferts": transferts,
            "table_clients": table_clients_redmine(cfg), "slugs_redmine": slugs,
            "notes": notes_du_compte(conf, cfg),
            "activites": activites,
            "conf": conf,
            "agenda": _agenda_periode(conf, cfg, debut, fin),
            "saisies": toutes, "surcharges": surcharges,
            # Ce que l'écran et la proposition VOIENT : les surcharges, complétées des
            # pauses habituelles. L'état sur disque, lui, ne contient que le saisi.
            "surcharges_vues": surcharges_vues, "pauses_defaut": pauses_defaut,
            "refacture": refacture,
            "activite_defaut": conf.get("activity_id") or 9,
            "final": final, "ecarte": ecarte, "journal": journal, "periodes": periodes,
            "totaux": totaux, "regles": regles, "params": params, "libelle": libelle,
            "sans_trace": sans_trace, "jour_demande": args.day or None,
            "deduit": deduit, "events": len(events), "sources": detail,
            "debut": debut, "fin": fin}


def ecrire_sorties(res, dossier, libelle):
    dossier.mkdir(parents=True, exist_ok=True)
    md = W.rendre_markdown(res["final"], res["ecarte"], res["journal"], res["periodes"],
                           res["totaux"], res["regles"], libelle,
                           quantum=res["params"]["quantum_min"],
                           resolver=res.get("resolver"), ajouts=res.get("ajouts"),
                           transferts=res.get("transferts"))
    chemin_md = dossier / f"{libelle}.md"
    chemin_md.write_text(md, encoding="utf-8")
    prop = W.proposition(res["final"], res["journal"], res["params"]["quantum_min"],
                         resolver=res.get("resolver"), regles=res.get("regles"),
                         minimum_client=(res.get("conf") or {}).get("minimum_client_min", 0),
                         activite_defaut=res.get("activite_defaut"),
                         refacture=res.get("refacture"),
                         meta={"periode": libelle, "genere": datetime.now().isoformat(timespec="minutes"),
                               "evenements": res["events"],
                               "sources": [{"kind": k, "path": p, "evenements": n}
                                           for k, p, n in res["sources"]]})
    ajouter_pauses(prop, res)
    # Les rattachements corrigés à la main s'appliquent APRÈS la pause : elle aussi
    # est une ligne, et elle doit pouvoir être recollée ailleurs.
    # La pause est ajoutée après coup : sans ce rappel elle n'aurait pas de clé, donc
    # ni bouton « corriger » ni bouton « écrire ». Reposer les clés est idempotent.
    W._poser_cles(prop["lignes"])
    orphelins = W.amender_lignes(prop["lignes"], res.get("surcharges") or {},
                                 res.get("regles"))
    W._poser_cles(prop["lignes"])
    # Le commentaire qui partira dans Redmine, calculé APRÈS les corrections : il
    # dépend du projet et du ticket, qu'on vient peut-être de changer. L'écran le
    # montre — on ne valide pas à l'aveugle un texte que le client lira.
    _poser_rangs(prop["lignes"])
    for _l in prop["lignes"]:
        _l["description"] = _libelle(_l, _marque(_l))
    _retirer_deja_posees(prop, res)
    if orphelins:
        apercu = ", ".join(f"{j} {c}" for j, c in orphelins[:3])
        print(f"  ⚠ {len(orphelins)} correction(s) de ligne sans cible "
              f"({apercu}{'…' if len(orphelins) > 3 else ''}) — la ligne a changé "
              f"depuis, la correction n'a PAS été appliquée.", file=sys.stderr)
    chemin_yml = dossier / f"{libelle}.yml"
    chemin_yml.write_text(yaml.safe_dump(prop, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
    return chemin_md, chemin_yml, prop


def _retirer_deja_posees(prop, res):
    """Défalque de la proposition ce qui est DÉJÀ posé sous la même marque.

    `--apply` reconnaît une ligne déjà posée à sa marque et ne la recrée pas : c'est
    la garde contre les doublons. Mais l'écran continuait de proposer la ligne
    ENTIÈRE — on cliquait, rien ne se créait, elle restait. « Il reste 2 h 45 déjà
    écrites qu'il veut réécrire, il n'y arrive pas » (22/07/2026).

    On ne la supprime pas pour autant : une ligne de 105 min dont 60 sont posées
    doit encore 45 min. On retranche donc, et ce qui reste prend un RANG libre —
    sans quoi sa marque resterait celle de la saisie existante, et `--apply` la
    prendrait de nouveau pour un doublon.
    """
    deja = {}
    for saisie in (res.get("saisies") or []):
        lib = saisie.get("libelle") or ""
        if "[timesheet:" not in lib:
            continue
        m = lib[lib.index("[timesheet:"):].split("]")[0] + "]"
        deja[m] = deja.get(m, 0.0) + float(saisie.get("minutes") or 0)
    if not deja:
        return prop
    gardees = []
    for l in prop["lignes"]:
        m = _marque(l)
        cle = m if m in deja else _marque_heritee(m, deja)
        if not cle:
            gardees.append(l)
            continue
        reste = int(round(float(l.get("minutes") or 0) - deja[cle]))
        if reste <= 0:
            continue                    # tout est déjà écrit : plus rien à proposer
        l["minutes"] = reste
        l["deja_pose_min"] = int(round(deja[cle]))
        # Un rang libre, pour que la marque ne soit plus celle de la saisie en place.
        rang = (l.get("rang") or 0) + 1
        while True:
            essai = dict(l, rang=rang)
            if _marque(essai) not in deja:
                break
            rang += 1
        l["rang"] = rang
        l["description"] = _libelle(l, _marque(l))
        gardees.append(l)
    prop["lignes"] = gardees
    return prop


def _agenda_periode(conf, cfg, debut, fin):
    """Les rendez-vous de la période, par jour. Silencieux si l'agenda ne répond pas.

    Une seule requête pour tout le mois : c'est l'agenda qui dit chez QUI on était,
    ce qu'aucune trace de travail ne sait.
    """
    aconf = dict(conf.get("agenda") or {})
    if aconf.get("actif") is False:
        return {}
    if not aconf.get("env_path"):
        try:
            import pm_paths
            aconf["env_path"] = str(pm_paths.user_conf_dir(pm_dir=cfg.pm_dir) / ".env")
        except Exception:
            return {}
    try:
        import pm_agenda
    except ImportError:
        return {}
    return pm_agenda.evenements_periode(debut.date().isoformat(),
                                        fin.date().isoformat(), aconf)


def ajouter_pauses(prop, res):
    """Ajoute à la proposition la pause de midi DÉCLARÉE sur une journée.

    Déclarée seulement : une pause qu'on n'a pas notée ne se crée pas toute seule. Elle
    se note sur soi (entité `self`), avec l'activité « Pause » — c'est du temps qui ne
    se facture pas, mais qui manque à la journée tant qu'il n'est pas noté.

    La déduction en amont la protège d'un doublon : sa marque lui est propre
    (`…#<client>/-@<activité pause>`), et `--apply` ne recrée jamais une marque connue.
    """
    pconf = W.conf_pause(res.get("conf") or {})
    if not pconf.get("client"):
        return prop
    # Les surcharges sont chargées par MOIS entier : sans ce bornage, la pause d'une
    # journée hors période s'invitait dans la proposition — et comme le serveur rendait
    # la première journée venue, l'écran affichait cette journée-là (constaté le
    # 2026-10-13 : « 08/06 je lis 45 min proposé… et la note du 04/06 »).
    debut = res.get("debut")
    fin = res.get("fin")
    dans_periode = (lambda j: True) if not (debut and fin) else (
        lambda j: debut.strftime("%Y-%m-%d") <= j < fin.strftime("%Y-%m-%d"))
    deja = {(s["jour"], round(float(s["minutes"]))) for s in res.get("saisies", [])
            if pconf["commentaire"] and pconf["commentaire"] in (s.get("libelle") or "")}
    for jour, surcharge in sorted((res.get("surcharges_vues")
                                   or res.get("surcharges") or {}).items()):
        if not dans_periode(jour):
            continue
        heures = W.duree_pause(surcharge)
        if not heures or float(heures) <= 0:
            continue
        minutes = int(round(float(heures) * 60))
        if (jour, minutes) in deja:
            continue
        prop["lignes"].append({
            "jour": jour, "client": pconf["client"], "projet": pconf.get("projet"),
            "ticket": None, "minutes": minutes,
            "activite": pconf.get("activity_id") or 27,
            "outillage_min": None, "valide": True, "facturable": False,
            "pause": True, "commentaire": pconf.get("commentaire") or "repas midi",
            "project_id": pconf.get("project_id"),
        })
    return prop


def appliquer(chemin_yml, cfg, conf, args):
    """Crée les saisies Redmine depuis la proposition validée. Idempotent."""
    from redmine_utils import redmine_creds, http_json, activity_for_type
    url, key = redmine_creds()
    uid = args.user_id or conf.get("user_id")
    if not uid:
        sys.exit("--user-id (ou `user_id:` dans timesheet.yml) requis : "
                 "les saisies sont créées au nom de cet utilisateur Redmine.")
    prop = yaml.safe_load(Path(chemin_yml).read_text(encoding="utf-8")) or {}
    lignes = [l for l in prop.get("lignes", []) if l.get("valide", True) and l.get("minutes")]
    # Écrire UNE ligne : l'unité de validation n'est plus forcément la journée entière.
    # On vise par la clé, jamais par le rang — un recalcul réordonne les lignes.
    if getattr(args, "ligne", None):
        voulues = [l for l in lignes if l.get("cle") == args.ligne]
        if not voulues:
            sys.exit(f"Aucune ligne « {args.ligne} » dans {chemin_yml}. "
                     f"Clés disponibles : {', '.join(sorted(l.get('cle') or '?' for l in lignes)[:8])}")
        lignes = voulues
    if not lignes:
        sys.exit(f"Aucune ligne validée dans {chemin_yml}.")

    # empreintes déjà posées (re-run sans doublon)
    deja = {}
    periode = prop.get("meta", {}).get("periode", "")
    offset = 0
    while True:
        code, body = http_json("GET", f"{url}/time_entries.json?user_id={uid}"
                                      f"&limit=100&offset={offset}", key)
        if code != 200:
            break
        for t in body.get("time_entries", []):
            c = t.get("comments") or ""
            if "[timesheet:" in c:
                deja[c[c.index("[timesheet:"):].split("]")[0] + "]"] = {
                    "id": t["id"], "activity_id": (t.get("activity") or {}).get("id")}
        offset += 100
        if offset >= body.get("total_count", 0):
            break

    cree = ignore = erreurs = corriges = 0
    sans_cible, echecs = [], []
    for l in lignes:
        marque = _marque(l)
        connue = marque if marque in deja else _marque_heritee(marque, deja)
        if connue:
            marque = connue
            ignore += 1
            # L'activité a pu être affinée depuis (journal du ticket, type) :
            # une saisie déjà posée se CORRIGE, elle ne se duplique pas.
            voulue = args.activity or l.get("activite") or conf.get("activity_id") or 9
            posee = deja[marque]
            if not args.dry_run and posee.get("activity_id") and voulue != posee["activity_id"]:
                code, _ = http_json("PUT", f"{url}/time_entries/{posee['id']}.json", key,
                                    {"time_entry": {"activity_id": voulue}})
                if code in (200, 204):
                    corriges += 1
            continue
        heures = round(l["minutes"] / 60.0, 2)
        payload = {"time_entry": {
            "spent_on": l["jour"], "hours": heures, "user_id": int(uid),
            "activity_id": (args.activity or l.get("activite")
                            or conf.get("activity_id") or 9),
            "comments": _libelle(l, marque),
        }}
        if l.get("ticket"):
            payload["time_entry"]["issue_id"] = int(l["ticket"])
        else:
            pid = _projet_redmine(l, conf, cfg, url, key)
            if not pid:
                sans_cible.append(f"{l['jour']} {l.get('client')}/{l.get('projet')}")
                erreurs += 1
                continue
            payload["time_entry"]["project_id"] = pid
        if args.dry_run:
            print(f"  [dry-run] {l['jour']} {heures:5.2f} h  "
                  f"{l.get('client')}/{l.get('projet')} "
                  f"{'RM' + str(l['ticket']) if l.get('ticket') else '(projet)'}")
            cree += 1
            continue
        code, corps = http_json("POST", f"{url}/time_entries.json", key, payload)
        if code in (200, 201):
            cree += 1
        else:
            echecs.append((l["jour"], f"{l.get('client')}/{l.get('projet')}", code,
                           str(corps)[:160]))
    if echecs:
        print(f"  ⚠ {len(echecs)} saisie(s) REFUSÉE(S) par Redmine :", file=sys.stderr)
        for jour, cible, code, detail in echecs[:6]:
            print(f"      {jour} {cible} → HTTP {code} {detail}", file=sys.stderr)
    if sans_cible:
        apercu = ", ".join(sorted(set(sans_cible))[:4])
        print(f"  ⚠ {len(sans_cible)} ligne(s) sans projet Redmine résolu ({apercu}"
              f"{'…' if len(set(sans_cible)) > 4 else ''}) — déclarer `project_map` "
              "ou `redmine.project_id` au projet PM", file=sys.stderr)
    verbe = "à créer" if args.dry_run else "créées"
    print(f"✓ timesheet {periode} : {cree} saisies {verbe}, {ignore} déjà posées"
          + (f" (dont {corriges} activité corrigée)" if corriges else "")
          + (f", {len(sans_cible)} sans projet résolu" if sans_cible else "")
          + (f", {len(echecs)} refusées par Redmine" if echecs else ""))
    return 0 if not (echecs or sans_cible) else 1


def reprendre_journee(cfg, conf, args):
    """Retire de Redmine les saisies POSÉES PAR CET OUTIL sur une journée, pour la refaire.

    Geste À LA DEMANDE, jamais automatique (arbitrage du 2026-09-21) : ni l'ouverture d'une
    journée, ni son rafraîchissement, ni sa validation n'appellent cette fonction. Elle ne
    s'exécute que si l'humain l'a explicitement demandée, sur une journée précise, après
    avoir constaté une incohérence.

    Deux garde-fous, non négociables :
      — seules les saisies portant la marque `[timesheet:<jour>#…]` sont touchées ; une
        saisie notée à la main par un humain n'est JAMAIS supprimée ;
      — tout est sauvegardé en JSONL avant la première suppression (incident RM2409 :
        334 notes supprimées sans sauvegarde). La sauvegarde s'écrit aussi en simulation.
    """
    from redmine_utils import redmine_creds, http_json
    url, key = redmine_creds()
    uid = args.user_id or conf.get("user_id")
    if not uid:
        sys.exit("--user-id (ou `user_id:` dans timesheet.yml) requis.")
    jour = args.day

    saisies, offset = [], 0
    while True:
        code, body = http_json("GET", f"{url}/time_entries.json?user_id={uid}"
                                      f"&from={jour}&to={jour}&limit=100&offset={offset}", key)
        if code != 200:
            sys.exit(f"Redmine a refusé la lecture des saisies du {jour} (HTTP {code}).")
        saisies += body.get("time_entries", [])
        offset += 100
        if offset >= body.get("total_count", 0):
            break

    marque = f"[timesheet:{jour}#"
    a_retirer = [t for t in saisies if marque in (t.get("comments") or "")]
    gardees = len(saisies) - len(a_retirer)
    if not a_retirer:
        print(f"✓ journée {jour} : aucune saisie posée automatiquement à retirer"
              + (f" ({gardees} saisie(s) notée(s) à la main, intactes)" if gardees else ""))
        return 0

    dossier = W.ETAT / "reprises"
    dossier.mkdir(parents=True, exist_ok=True)
    sauvegarde = dossier / f"{jour}-{datetime.now():%Y%m%dT%H%M%S}.jsonl"
    with sauvegarde.open("w", encoding="utf-8") as f:
        for t in a_retirer:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    heures = sum(float(t.get("hours") or 0) for t in a_retirer)

    if args.dry_run:
        print(f"  [simulation] {len(a_retirer)} saisie(s) seraient retirée(s) "
              f"({heures:.2f} h) — sauvegarde {sauvegarde}")
        return 0

    retires, echecs = 0, []
    for t in a_retirer:
        code, corps = http_json("DELETE", f"{url}/time_entries/{t['id']}.json", key)
        if code in (200, 204):
            retires += 1
        else:
            echecs.append((t["id"], code, str(corps)[:120]))

    # La journée redevient à valider : la marque « validée sans ajout » tombe avec elle.
    donnees = W.surcharges_charger(jour[:7])
    if (donnees.get(jour) or {}).pop("valide_sans_ajout", None) is not None:
        W.surcharges_ecrire(jour[:7], donnees)

    for tid, code, detail in echecs[:6]:
        print(f"  ⚠ saisie {tid} non retirée : HTTP {code} {detail}", file=sys.stderr)
    print(f"✓ journée {jour} reprise : {retires} saisie(s) retirée(s) ({heures:.2f} h)"
          + (f", {len(echecs)} en échec" if echecs else "")
          + (f" — {gardees} saisie(s) notée(s) à la main conservée(s)" if gardees else "")
          + f"\n  sauvegarde : {sauvegarde}"
          + f"\n  puis : mmi-pm timesheet --day {jour} --refresh")
    return 0 if not echecs else 1


def corriger_activites(cfg, conf, args, libelle):  # noqa: C901
    """Réaligne l'activité des saisies déjà posées. Ne crée ni ne supprime rien.

    Séparé d'`--apply` volontairement : recalculer une proposition sans déduction
    pour corriger des activités re-proposerait à la création tout ce qui est déjà
    saisi À LA MAIN — un doublon de facturation. Ici on ne touche qu'aux lignes
    portant la marque `[timesheet:…]`, et uniquement leur activité.
    """
    from redmine_utils import http_json, redmine_creds
    debut, fin, _ = _periode(args)
    url, key = redmine_creds()[:2]
    uid = args.user_id or conf.get("user_id")
    if not uid:
        sys.exit("--user-id (ou `user_id:` dans timesheet.yml) requis.")
    resolver = W.TargetResolver(cfg, path_map=conf.get("path_map"))
    defaut = conf.get("activity_id") or 9

    # Recalcul SANS déduction, en mémoire seulement : il faut toutes les lignes
    # pour retrouver celles déjà posées. Rien n'est créé depuis cette
    # proposition — on ne touche qu'aux saisies portant déjà une marque.
    args_recalc = argparse.Namespace(**{**vars(args), "sans_deduction": True})
    attendu = {}
    try:
        res = calculer(args_recalc, cfg, conf)
        prop = W.proposition(res["final"], res["journal"], res["params"]["quantum_min"],
                             resolver=res.get("resolver"),
                             activite_defaut=res.get("activite_defaut"),
                             refacture=res.get("refacture"))
        for l in prop["lignes"]:
            marque = _marque(l)
            attendu[marque] = l
    except SystemExit:
        pass

    offset, posees = 0, []
    while True:
        code, body = http_json(
            "GET", f"{url}/time_entries.json?user_id={uid}"
            f"&from={debut:%Y-%m-%d}&to={(fin - timedelta(days=1)):%Y-%m-%d}"
            f"&limit=100&offset={offset}", key)
        if code != 200:
            sys.exit(f"Redmine a répondu {code}.")
        posees += [t for t in body.get("time_entries", [])
                   if "[timesheet:" in (t.get("comments") or "")]
        offset += 100
        if offset >= body.get("total_count", 0):
            break

    change = inchange = rate = 0
    for t in posees:
        commentaire = t.get("comments") or ""
        marque = commentaire[commentaire.index("[timesheet:"):].split("]")[0] + "]"
        rm = str(t["issue"]["id"]) if t.get("issue") else None
        ligne = attendu.get(marque)
        if ligne is None and marque.endswith("/-]"):
            # saisie posée avant que les lignes sans ticket portent leur activité
            prefixe = marque[:-1] + "@"
            candidates = [v for k, v in attendu.items() if k.startswith(prefixe)]
            ligne = max(candidates, key=lambda l: l["minutes"]) if candidates else None
        voulue = (ligne or {}).get("activite") or resolver.activite(
            rm, t["spent_on"], defaut) or defaut
        actuelle = (t.get("activity") or {}).get("id")
        texte = _libelle(ligne, marque) if ligne else commentaire
        maj = {}
        if voulue != actuelle:
            maj["activity_id"] = voulue
        if texte != commentaire:
            maj["comments"] = texte
        if not maj:
            inchange += 1
            continue
        if args.dry_run:
            quoi = " · ".join(
                ([f"activité {actuelle} → {voulue}"] if "activity_id" in maj else [])
                + ([f"libellé → {texte[:56]}"] if "comments" in maj else []))
            print(f"  [dry-run] {t['spent_on']} {t['hours']:5.2f} h "
                  f"{'RM' + rm if rm else '(projet)':10} {quoi}")
            change += 1
            continue
        code, _ = http_json("PUT", f"{url}/time_entries/{t['id']}.json", key,
                            {"time_entry": maj})
        if code in (200, 204):
            change += 1
        else:
            rate += 1
    verbe = "à corriger" if args.dry_run else "corrigées"
    print(f"✓ timesheet {libelle} : {change} saisie(s) {verbe}, {inchange} déjà justes"
          + (f", {rate} refusée(s)" if rate else "")
          + f" (sur {len(posees)} saisies posées) — aucune création")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--month", help="mois à traiter (AAAA-MM)")
    ap.add_argument("--day", help="une journée (AAAA-MM-JJ) — l'unité de validation")
    ap.add_argument("--start", help="avec --day : heure de début normale (HH:MM)")
    ap.add_argument("--end", help="avec --day : heure de fin normale (HH:MM)")
    ap.add_argument("--client", help="avec --day : client principal de la journée")
    ap.add_argument("--projet", help="avec --day : projet PM du client principal")
    ap.add_argument("--pause", type=float, help="avec --day : pause en heures (défaut 1 h au-delà de 6 h)")
    ap.add_argument("--pause-debut", dest="pause_debut",
                    help="avec --day : début de la pause (HH:MM) — plus précis que --pause")
    ap.add_argument("--pause-fin", dest="pause_fin",
                    help="avec --day : fin de la pause (HH:MM)")
    ap.add_argument("--ligne", help="avec --day : clé d'UNE ligne proposée "
                                    "(client/projet#ticket@activité), à corriger ou à écrire seule")
    ap.add_argument("--set-client", dest="set_client",
                    help="avec --ligne : rattacher cette ligne à un autre client")
    ap.add_argument("--set-projet", dest="set_projet",
                    help="avec --ligne : rattacher cette ligne à un autre projet PM")
    ap.add_argument("--set-ticket", dest="set_ticket",
                    help="avec --ligne : rattacher cette ligne à un autre ticket (ou `-` pour aucun)")
    ap.add_argument("--set-activite", dest="set_activite",
                    help="avec --ligne : changer l'activité Redmine de cette ligne")
    ap.add_argument("--clear-ligne", dest="clear_ligne", action="store_true",
                    help="avec --ligne : retirer la correction, la ligne redevient ce que le calcul dit")
    ap.add_argument("--set-minutes", dest="set_minutes", type=int,
                    help="avec --ligne : forcer la durée de cette ligne, en minutes")
    ap.add_argument("--split", dest="split", type=int,
                    help="avec --ligne : scinder en deux — cette ligne garde N minutes, "
                         "une seconde reçoit le reste")
    ap.add_argument("--delete-ligne", dest="delete_ligne", action="store_true",
                    help="avec --ligne : retirer cette ligne de la proposition")
    ap.add_argument("--add-ligne", dest="add_ligne", action="store_true",
                    help="avec --day : ajouter une ligne à la main (--set-client/--set-projet/"
                         "--set-ticket/--set-activite/--set-minutes/--commentaire)")
    ap.add_argument("--commentaire", dest="commentaire",
                    help="avec --add-ligne : commentaire de la saisie Redmine")
    ap.add_argument("--set-commentaire", dest="set_commentaire",
                    help="avec --ligne : ce que cette ligne dira au client — c'est ce "
                         "texte qui part dans Redmine, puis sur la facture "
                         "(`-` pour revenir au texte calculé)")
    ap.add_argument("--heures", type=float,
                    help="avec --day : heures de travail de la journée, quand elles ne se "
                         "déduisent pas de début/fin (demi-journée sur site, par exemple)")
    ap.add_argument("--lieu", choices=["presentiel", "distanciel"],
                    help="avec --day : journée chez le client (présentiel) ou à la maison "
                         "(distanciel). Noté avec la journée — il conditionne le déplacement.")
    ap.add_argument("--exclusif", action="store_true",
                    help="avec --day : journée presque exclusivement pour le client principal")
    ap.add_argument("--clear-override", action="store_true", help="avec --day : retire l'ajustement")
    ap.add_argument("--validate-empty", action="store_true",
                    help="avec --day : valider une journée saisie entièrement à la main")
    ap.add_argument("--refresh", action="store_true", help="ignorer le cache par jour")
    ap.add_argument("--json", action="store_true", help="sortie JSON (cockpit)")
    ap.add_argument("--from", dest="depuis", help="date de début (AAAA-MM-JJ)")
    ap.add_argument("--to", dest="jusqu_a", help="date de fin incluse (AAAA-MM-JJ)")
    ap.add_argument("--out", help="dossier de sortie (défaut : <core>/var/timesheet)")
    ap.add_argument("--config", help="réglages (défaut : <core>/var/users/<user>/timesheet.yml)")
    ap.add_argument("--apply", action="store_true",
                    help="crée les saisies Redmine depuis la proposition validée")
    ap.add_argument("--dry-run", action="store_true", help="avec --apply : n'écrit rien")
    ap.add_argument("--user-id", type=int, help="utilisateur Redmine des saisies")
    ap.add_argument("--activity", type=int, help="activité Redmine forcée")
    ap.add_argument("--follow-cap", type=float, help="plafond du temps de suivi (min)")
    ap.add_argument("--quantum", type=int, help="tranche d'arrondi (min)")
    ap.add_argument("--revoke", action="store_true",
                    help="avec --day : RETIRE les saisies que cet outil a posées ce jour-là "
                         "(jamais celles notées à la main), après sauvegarde, pour refaire "
                         "la journée. Geste à la demande — rien ne l'appelle tout seul.")
    ap.add_argument("--fix-activities", "--fix", dest="fix_activities",
                    action="store_true",
                    help="réaligne activité ET commentaire des saisies DÉJÀ posées ; "
                         "n'en crée, ni n'en supprime aucune")
    ap.add_argument("--sans-deduction", action="store_true",
                    help="ne pas retrancher les saisies Redmine existantes")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not args.month and not args.day and not (args.depuis and args.jusqu_a):
        ap.error("--month AAAA-MM, --day AAAA-MM-JJ, ou --from et --to")
    ajuste = any(v is not None for v in (args.start, args.end, args.client, args.projet,
                                         args.pause, args.lieu, args.heures,
                                         args.pause_debut, args.pause_fin)) \
        or args.exclusif or args.clear_override or args.validate_empty or args.add_ligne \
        or (args.ligne and (args.clear_ligne or args.delete_ligne
                            or args.split is not None or args.set_minutes is not None
                            or any(v is not None for v in (args.set_client, args.set_projet,
                                                           args.set_ticket, args.set_activite,
                                                           args.set_commentaire))))
    if ajuste and not args.day:
        ap.error("--start/--end/--client/--clear-override/--validate-empty/--ligne "
                 "s'utilisent avec --day")

    cfg = PMConfig.load()
    W.configurer_etat(cfg)          # <core>/var/timesheet — données d'exploitation du PM
    conf = W.charger_config(args.config, cfg=cfg)
    dossier = Path(args.out) if args.out else W.ETAT
    _d, _f, libelle = _periode(args)
    if ajuste:
        ajuster_journee(args)

    if args.revoke:
        if not args.day:
            ap.error("--revoke s'utilise avec --day : on ne reprend qu'une journée à la fois")
        return reprendre_journee(cfg, conf, args)

    if args.fix_activities:
        return corriger_activites(cfg, conf, args, libelle)

    if args.apply:
        chemin = dossier / f"{libelle}.yml"
        # Une JOURNÉE se valide depuis l'écran : sa proposition se recalcule ici même,
        # juste avant d'écrire. Sans cela on appliquerait la proposition d'avant le
        # dernier ajustement (début/fin, client principal) — l'écran montrerait une
        # chose, Redmine en recevrait une autre. Un MOIS garde son yml amendable à la
        # main : c'est le geste prévu pour lui.
        if args.day:
            ecrire_sorties(calculer(args, cfg, conf), dossier, libelle)
        elif not chemin.is_file():
            sys.exit(f"{chemin} absent — lancer d'abord `mmi-pm timesheet --month {libelle}`.")
        return appliquer(chemin, cfg, conf, args)

    res = calculer(args, cfg, conf)
    md, yml, prop = ecrire_sorties(res, dossier, libelle)
    if args.json:
        vue = vue_json(res, prop)
        # La fenêtre de collecte déborde la journée (une trace à 23h50 tire la
        # suivante), donc le calcul porte sur plusieurs dates. En `--day`, on ne rend
        # QUE celle demandée : sinon le premier élément de la liste est une autre
        # journée, et qui lit `jours[0]` analyse le mauvais jour — ça m'est arrivé.
        if args.day:
            vue["jours"] = [j for j in vue["jours"] if j.get("date") == args.day]
        print(json.dumps(vue, ensure_ascii=False, default=str))
        return 0
    total = sum(res["final"].values())
    print(f"✓ timesheet {libelle} : {_fmt(sum(res['totaux'].values()))} mesurées sur "
          f"{len(res['totaux'])} journées → {_fmt(total)} à noter "
          f"({len(prop['lignes'])} lignes), {_fmt(sum(res['ecarte'].values()))} écartées")
    alertes = sum(1 for d in res["journal"].values() if d.get("alerte_absence"))
    if alertes:
        print(f"  ⚠ {alertes} journée(s) d'absence avec activité cliente — à trancher")
    print(f"  rapport : {md}\n  proposition (à amender) : {yml}")
    print(f"  puis : mmi-pm timesheet --month {libelle} --apply")
    return 0


def _proposition_courante(args):
    """La proposition déjà calculée pour cette journée, si elle est sur disque.

    Scinder suppose de connaître la durée de la ligne : on la lit, on ne la devine pas.
    """
    chemin = W.ETAT / f"{args.day}.yml"
    if yaml is None or not chemin.is_file():
        return {}
    return yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}


def _ligne_courante(args):
    for l in (_proposition_courante(args).get("lignes") or []):
        if l.get("cle") == args.ligne and l.get("jour") == args.day:
            return l
    return {}


def _reste_a_scinder(args, chg):
    """Ce qui revient à la seconde ligne. Refuse une coupure qui ne tient pas."""
    src = _ligne_courante(args)
    total = chg.get("minutes", src.get("minutes"))
    if total is None:
        sys.exit(f"ligne « {args.ligne} » introuvable dans la proposition du {args.day} — "
                 f"relancer `mmi-pm timesheet --day {args.day}` d'abord.")
    reste = int(total) - int(args.split)
    if int(args.split) <= 0 or reste <= 0:
        sys.exit(f"--split {args.split} impossible sur une ligne de {total} min : "
                 f"les deux morceaux doivent être > 0.")
    return reste


def ajuster_journee(args):
    """Pose, modifie ou efface la surcharge d'une journée (début, fin, client principal).

    C'est le geste de l'écran de validation : la journée se recalcule aussitôt, depuis
    son cache. Une journée DÉJÀ validée ne bouge plus — ses saisies sont déduites —
    et on le dit, plutôt que de laisser croire à un recalcul silencieux.
    """
    mois = args.day[:7]
    donnees = W.surcharges_charger(mois)
    jour = dict(donnees.get(args.day) or {})
    if args.clear_override:
        donnees.pop(args.day, None)
        W.surcharges_ecrire(mois, donnees)
        print(f"✓ journée {args.day} : surcharge retirée")
        return
    for champ, valeur in (("debut", args.start), ("fin", args.end), ("client", args.client),
                          ("projet", args.projet), ("pause_h", args.pause), ("lieu", args.lieu),
                          ("heures", args.heures),
                          ("pause_debut", args.pause_debut), ("pause_fin", args.pause_fin)):
        if valeur is not None:
            jour[champ] = valeur
    # Correction du rattachement d'UNE ligne : elle vit à part des réglages de la
    # journée, sous sa clé, pour qu'un recalcul la retrouve sans la confondre.
    if args.ligne:
        lignes = dict(jour.get("lignes") or {})
        if args.clear_ligne:
            lignes.pop(args.ligne, None)
        elif args.delete_ligne:
            lignes[args.ligne] = {**(lignes.get(args.ligne) or {}), "supprimee": True}
        else:
            chg = dict(lignes.get(args.ligne) or {})
            for champ, valeur in (("client", args.set_client), ("projet", args.set_projet),
                                  ("ticket", args.set_ticket), ("activite", args.set_activite),
                                  ("commentaire", args.set_commentaire)):
                if valeur is not None:
                    chg[champ] = None if str(valeur) in ("-", "") else valeur
            if args.set_minutes is not None:
                chg["minutes"] = int(args.set_minutes)
            # Scinder : la ligne d'origine garde N minutes, une ligne manuelle reçoit
            # le reste. Le TOTAL de la journée ne change pas — c'est une coupure, pas
            # un ajout. Le reste se lit sur la proposition courante, pas sur une
            # supposition : scinder une ligne qu'on n'a pas sous les yeux n'a pas de sens.
            if args.split is not None:
                reste = _reste_a_scinder(args, chg)
                chg["minutes"] = int(args.split)
                manuelles = list(jour.get("lignes_manuelles") or [])
                src = _ligne_courante(args)
                manuelles.append({
                    "client": chg.get("client", src.get("client")),
                    "projet": chg.get("projet", src.get("projet")),
                    "ticket": chg.get("ticket", src.get("ticket")),
                    "activite": chg.get("activite", src.get("activite")),
                    "minutes": reste,
                    "commentaire": args.commentaire or None,
                    "cle": f"man{len(manuelles) + 1}",
                })
                jour["lignes_manuelles"] = manuelles
            if chg:
                lignes[args.ligne] = chg
        if lignes:
            jour["lignes"] = lignes
        else:
            jour.pop("lignes", None)
    if args.add_ligne:
        manuelles = list(jour.get("lignes_manuelles") or [])
        if args.set_minutes is None or int(args.set_minutes) <= 0:
            sys.exit("--add-ligne exige --set-minutes (durée en minutes, > 0)")
        if not args.set_client:
            sys.exit("--add-ligne exige --set-client")
        manuelles.append({
            "client": args.set_client, "projet": args.set_projet,
            "ticket": args.set_ticket if args.set_ticket not in ("-", "") else None,
            "activite": args.set_activite, "minutes": int(args.set_minutes),
            "commentaire": args.commentaire or None,
            "cle": f"man{len(manuelles) + 1}",
        })
        jour["lignes_manuelles"] = manuelles
    if args.exclusif:
        jour["exclusif"] = True
    if args.validate_empty:
        jour["valide_sans_ajout"] = True
    donnees[args.day] = jour
    W.surcharges_ecrire(mois, donnees)
    if jour.get("debut") and jour.get("fin"):
        h = W.heures_travaillees(jour["debut"], jour["fin"], jour.get("pause_h"))
        print(f"✓ journée {args.day} : {jour['debut']}–{jour['fin']} ({h:g} h)"
              + (f", client principal {jour['client']}" if jour.get("client") else "")
              + (f", {jour['lieu']}" if jour.get("lieu") else ""))
    elif args.validate_empty:
        print(f"✓ journée {args.day} : validée sans ajout")


def slugs_projets_redmine(url, key, basic=None):
    """{id numérique → identifiant textuel} des projets Redmine.

    Le chaînon manquant : une saisie de temps porte l'id NUMÉRIQUE de son projet,
    quand les manifestes PM déclarent l'identifiant TEXTUEL (`matnat-infra`). Sans
    cette table, aucune saisie ne se rattache à son client.
    """
    from redmine_utils import http_json
    out, offset = {}, 0
    while True:
        code, body = http_json("GET", f"{url}/projects.json?limit=100&offset={offset}",
                               key, basic=basic)
        if code != 200:
            break
        for pr in body.get("projects", []):
            out[str(pr.get("id"))] = pr.get("identifier") or ""
        offset += 100
        if offset >= body.get("total_count", 0):
            break
    return out


def table_clients_redmine(cfg):
    """{id de projet Redmine → (client PM, projet PM)}, parcourue UNE fois.

    `find_project_by_redmine_id` re-balaye tous les projets à chaque appel : l'utiliser
    par saisie ferait des centaines de parcours pour une seule journée.
    """
    table = {}
    try:
        for ent, proj, _chemin in cfg.iter_projects():
            fm = cfg.project_meta(ent, proj)
            rid = (fm.get("redmine") or {}).get("project_id")
            if rid is not None:
                table[str(rid)] = (ent, proj)
    except Exception:
        pass
    return table


def _cible_lisible(event):
    """La cible la mieux notée d'une trace : (client, projet, ticket). Inerte."""
    if not getattr(event, "scores", None):
        return {"client": None, "projet": None, "ticket": None}
    (ent, pr, rm), _poids = max(event.scores.items(), key=lambda kv: kv[1])
    return {"client": ent, "projet": pr, "ticket": rm}


def _extrait(texte, n=140):
    """Une ligne lisible d'une trace : ce que Mathieu a écrit, sans les retours."""
    return " ".join(str(texte or "").split())[:n]


def traces_du_jour(res, jour):
    """Toutes les traces horodatées d'une journée, humaines ET d'agent.

    C'est la pièce à conviction de la journée : chaque minute proposée vient de là.
    Les traces d'AGENT (`extends: false`) sont marquées — elles ne créent pas de
    temps, elles servent seulement à savoir sur quoi le temps créé portait.
    """
    sortie = []
    for event, _rm in res.get("items") or []:
        if event.ts.date().isoformat() != jour:
            continue
        sortie.append({"heure": event.ts.strftime("%H:%M"), "source": event.source,
                       "humain": bool(event.extends), "chars": event.chars,
                       "extrait": _extrait(event.text), **_cible_lisible(event)})
    return sorted(sortie, key=lambda t: t["heure"])


_ACTIVITES_CACHE = {}


def activites_redmine(url, key, basic=None):
    """{id → nom} des activités Redmine. Un bloc doit dire « Développement », pas « 9 »."""
    if _ACTIVITES_CACHE:
        return _ACTIVITES_CACHE
    from redmine_utils import http_json
    code, body = http_json("GET", f"{url}/enumerations/time_entry_activities.json",
                           key, basic=basic)
    if code == 200:
        for a in body.get("time_entry_activities", []):
            _ACTIVITES_CACHE[str(a.get("id"))] = a.get("name") or ""
    return _ACTIVITES_CACHE


_NOTES = {}


def notes_du_compte(conf, cfg):
    """L'accès aux notes de journée, ou None si les identifiants manquent.

    Lecture seule, et jamais bloquante : une note illisible ne doit pas empêcher de
    valider une journée. Les identifiants sont dans le `.env` de l'utilisateur.
    """
    if "n" in _NOTES:
        return _NOTES["n"]
    _NOTES["n"] = None
    try:
        import pm_notes
        import pm_paths
        env = pm_paths.user_conf_dir(pm_dir=getattr(cfg, "pm_dir", None)) / ".env"
        creds = pm_notes.identifiants(env)
        if creds:
            _NOTES["n"] = pm_notes.Notes(creds, (conf or {}).get("notes_racines"))
    except Exception:
        pass
    return _NOTES["n"]


def _cumul_transversal(res, jour):
    """Combien de temps transversal chaque client a reçu ce jour-là.

    La clé de répartition dit des pourcentages ; ce cumul dit des minutes. C'est
    lui qu'on relit pour juger si la refacturation est juste.
    """
    cumul = collections.Counter()
    for (j, cible), minutes in (res.get("refacture") or {}).items():
        if j == jour:
            cumul[cible[0]] += minutes
    return cumul


def _ou(saisie, table, slugs=None):
    """Où une saisie a été notée : client PM si on le connaît, et le projet.

    Deux colonnes plutôt qu'un libellé collé : un client se lit d'un coup d'œil, et
    c'est à cette maille que la facture se fait. La résolution tente l'id numérique,
    puis l'identifiant textuel ; à défaut, le nom Redmine tient lieu de projet.
    """
    pid = str(saisie.get("projet_id"))
    ent, proj = (table or {}).get(pid, (None, None))
    if not ent and slugs:
        ent, proj = (table or {}).get(slugs.get(pid) or "", (None, None))
    return {"client": ent, "projet": proj or saisie.get("projet_nom") or ""}


def _client_suggere(res, jour, surcharge):
    """Ce que l'agenda dit du client de la journée — tant que rien n'est choisi.

    « ok si pas déjà renseigné » : une suggestion ne discute pas un choix fait.
    """
    if (surcharge or {}).get("client"):
        return None
    evs = (res.get("agenda") or {}).get(jour) or []
    if not evs:
        return None
    regles = res.get("regles")
    clients = [e for e, t in ((regles.types if regles else {}) or {}).items() if t == "client"]
    if not clients:
        return None
    try:
        import pm_agenda
    except ImportError:
        return None
    alias = ((res.get("conf") or {}).get("agenda") or {}).get("alias") or {}
    return pm_agenda.client_du_jour(evs, clients, alias)


def vue_json(res, prop, commits=True):
    """La matière de l'écran de validation (cockpit) : une entrée par journée.

    Le temps IA y figure en face du temps humain : c'est lui qui justifie une plage.
    Les traces et les commits sont la pièce à conviction — sans eux, l'écran demande
    de croire un chiffre ; avec eux, il le donne à vérifier.
    """
    jours = sorted(set(res["totaux"]) | {l["jour"] for l in prop["lignes"]}
                   | {s["jour"] for s in res.get("saisies", [])}
                   # La journée DEMANDÉE figure toujours, même si rien ne la peuple :
                   # sans cela une journée sans aucune trace ni saisie n'existait pas
                   # pour l'écran, et ne pouvait donc être ni consultée ni close.
                   | ({res["jour_demande"]} if res.get("jour_demande") else set()))
    table_clients = res.get("table_clients") or {}
    slugs = res.get("slugs_redmine") or {}
    sortie = []
    for j in jours:
        surcharge = (res.get("surcharges") or {}).get(j) or {}
        # Ce que l'écran montre inclut la pause habituelle de la présence ; `surcharge`
        # reste ce qui est VRAIMENT écrit dans l'état, pour que « retirer l'ajustement »
        # ne prétende pas effacer un défaut qu'il ne possède pas.
        vue = (res.get("surcharges_vues") or {}).get(j) or surcharge
        saisies = [s for s in res.get("saisies", []) if s["jour"] == j]
        sortie.append({
            "date": j,
            "mesure_min": round(res["totaux"].get(j, 0)),
            "periodes": [[a.strftime("%H:%M"), b.strftime("%H:%M")]
                         for a, b in res["periodes"].get(j, [])],
            "journal": res["journal"].get(j, {}),
            "proposition": [l for l in prop["lignes"] if l["jour"] == j],
            "deja_saisi": [{"minutes": round(s["minutes"]), "ticket": s.get("rm"),
                            "libelle": s.get("libelle", ""),
                            **_ou(s, table_clients, slugs)} for s in saisies],
            "regie": [{"client": c[0], "motif": m, "minutes": round(v)}
                      for (d, c, m), v in res["ajouts"].items() if d == j],
            "bandes": [{"debut": b["debut"].strftime("%H:%M"),
                        "fin": b["fin"].strftime("%H:%M"),
                        "client": b["client"], "minutes": round(b["minutes"]),
                        "parts": {c: round(m) for c, m in sorted(
                            b["parts"].items(), key=lambda kv: -kv[1]) if round(m)}}
                       for b in W.bandes_par_client((res.get("segments") or {}).get(j, []))],
            "activites": res.get("activites") or {},
            "transversal_par_client": {
                c: round(v) for c, v in sorted(
                    _cumul_transversal(res, j).items(), key=lambda kv: -kv[1]) if round(v)},
            "ia": [{"heure": k["heure"], "ticket": k["ticket"], "client": k["client"],
                    "projet": k["projet"], "modele": k["modele"], "tokens": k["tokens"],
                    "minutes": k["minutes"], "minutes_reelles": k["minutes_reelles"],
                    "borne": k["borne"]}
                   for k in W.ticks_sans_chevauchement(
                       res.get("resolver").ticks(j) if res.get("resolver") else [])],
            "traces": traces_du_jour(res, j),
            "commits": (W.commits_du_jour(j, auteur=(res.get("params") or {}).get("git_author")
                                          or "Mathieu Moulin") if commits else []),
            "note": (res.get("notes").note(j) if res.get("notes") else None),
            "pause": {
                "declaree_h": W.duree_pause(vue),
                "debut": vue.get("pause_debut"),
                "fin": vue.get("pause_fin"),
                # D'où vient cette pause : notée à la main sur la journée, ou héritée
                # des horaires habituels de la présence.
                "origine": ("presence" if (res.get("pauses_defaut") or {}).get(j)
                            and not (surcharge.get("pause_debut") or surcharge.get("pause_fin")
                                     or surcharge.get("pause_h"))
                            else ("journee" if W.duree_pause(surcharge) else None)),
                "trou": W.trou_de_midi(
                    [[a.strftime("%H:%M"), b.strftime("%H:%M")]
                     for a, b in res["periodes"].get(j, [])]),
                "cible": {k: v for k, v in (W.conf_pause(res.get("conf") or {})).items()
                          if k in ("client", "projet", "commentaire", "heures")},
            },
            "agenda": (res.get("agenda") or {}).get(j) or [],
            # Le client que l'agenda désigne. PROPOSÉ, jamais imposé : il pré-remplit
            # le champ tant qu'on n'a rien choisi, et s'efface dès qu'on choisit.
            "client_suggere": _client_suggere(res, j, surcharge),
            "surcharge": surcharge or None,
            "valide": any("[timesheet:" in (s.get("libelle") or "") for s in saisies)
                      or bool(surcharge.get("valide_sans_ajout")),
        })
    return {"periode": res["libelle"], "jours": sortie}


def _fmt(minutes):
    return f"{minutes/60:.1f} h"


if __name__ == "__main__":
    sys.exit(main())
