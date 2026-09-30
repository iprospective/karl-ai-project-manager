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
            events += W.collect_claude_transcripts(chemin, debut, fin)
        elif kind == "claude-history":
            events += W.collect_claude_history(chemin, debut, fin)
        elif kind == "opencode-db":
            events += W.collect_opencode(chemin, debut, fin)
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
    """Retrouve une saisie posée AVANT que les lignes sans ticket portent leur activité.

    Sans cela, `[timesheet:…/-@13]` ne reconnaîtrait pas `[timesheet:…/-]` déjà
    en base et la recréerait : un doublon de facturation, le défaut le plus grave
    que puisse avoir cet outil.
    """
    if "@" not in marque:
        return None
    ancienne = marque.split("@")[0] + "]"
    return ancienne if ancienne in deja else None


def _marque(ligne):
    """Clé de déduplication d'une ligne. Une ligne sans ticket porte son activité :
    plusieurs natures de travail cohabitent le même jour sur le même projet."""
    base = (f"[timesheet:{ligne['jour']}#{ligne.get('client') or '-'}"
            f"/{ligne.get('ticket') or '-'}")
    if not ligne.get("ticket") and ligne.get("activite"):
        base += f"@{ligne['activite']}"
    return base + "]"


def _libelle(ligne, marque):
    """Commentaire de la saisie — court, c'est ce que le client lira.

    Le ticket porte déjà son titre dans Redmine : le répéter n'apporterait rien.
    Seule la part d'outillage mutualisé (PM, infrastructure, produits) mérite
    d'être dite, puisqu'elle est incluse dans le temps sans être visible.
    """
    if ligne.get("pause"):
        return f"{ligne.get('commentaire') or 'repas midi'} {marque}"[:255]
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
    if not items:
        sys.exit(f"Aucune trace sur la période {libelle} — sources : "
                 + ", ".join(s.get("kind", "?") for s in _sources(conf)))

    resolver = W.TargetResolver(cfg, path_map=conf.get("path_map"))
    for e, rm in items:
        resolver.resolve(e, rm_du_tour=rm)
    events = [e for e, _rm in items]

    regles = W.regles_depuis_config(conf, cfg)
    alloc, periodes, totaux, par_heure, par_heure_cible, segments = W.allocate(
        W.build_intervals(events, params), params)
    alloc = W.eclater_cles_multi(alloc, regles)
    final, ecarte, journal, refacture = W.repartir_transversal(alloc, regles, params)

    deduit, toutes, slugs = [], [], {}
    if not args.sans_deduction:
        for nom, url, key, basic, uid in instances_redmine(conf, cfg, args):
            saisies = saisies_humaines(url, key, uid, debut, fin, basic)
            if saisies and not slugs:
                slugs = slugs_projets_redmine(url, key, basic)
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
            "conf": conf,
            "saisies": toutes, "surcharges": surcharges,
            "refacture": refacture,
            "activite_defaut": conf.get("activity_id") or 9,
            "final": final, "ecarte": ecarte, "journal": journal, "periodes": periodes,
            "totaux": totaux, "regles": regles, "params": params, "libelle": libelle,
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
                         activite_defaut=res.get("activite_defaut"),
                         refacture=res.get("refacture"),
                         meta={"periode": libelle, "genere": datetime.now().isoformat(timespec="minutes"),
                               "evenements": res["events"],
                               "sources": [{"kind": k, "path": p, "evenements": n}
                                           for k, p, n in res["sources"]]})
    ajouter_pauses(prop, res)
    chemin_yml = dossier / f"{libelle}.yml"
    chemin_yml.write_text(yaml.safe_dump(prop, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
    return chemin_md, chemin_yml, prop


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
    deja = {(s["jour"], round(float(s["minutes"]))) for s in res.get("saisies", [])
            if pconf["commentaire"] and pconf["commentaire"] in (s.get("libelle") or "")}
    for jour, surcharge in sorted((res.get("surcharges") or {}).items()):
        heures = surcharge.get("pause_h")
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
                                         args.pause, args.lieu)) \
        or args.exclusif or args.clear_override or args.validate_empty
    if ajuste and not args.day:
        ap.error("--start/--end/--client/--clear-override/--validate-empty s'utilisent avec --day")

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
        print(json.dumps(vue_json(res, prop), ensure_ascii=False, default=str))
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
                          ("projet", args.projet), ("pause_h", args.pause), ("lieu", args.lieu)):
        if valeur is not None:
            jour[champ] = valeur
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


def vue_json(res, prop, commits=True):
    """La matière de l'écran de validation (cockpit) : une entrée par journée.

    Le temps IA y figure en face du temps humain : c'est lui qui justifie une plage.
    Les traces et les commits sont la pièce à conviction — sans eux, l'écran demande
    de croire un chiffre ; avec eux, il le donne à vérifier.
    """
    jours = sorted(set(res["totaux"]) | {l["jour"] for l in prop["lignes"]}
                   | {s["jour"] for s in res.get("saisies", [])})
    table_clients = res.get("table_clients") or {}
    slugs = res.get("slugs_redmine") or {}
    sortie = []
    for j in jours:
        surcharge = (res.get("surcharges") or {}).get(j) or {}
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
            "pause": {
                "declaree_h": surcharge.get("pause_h"),
                "trou": W.trou_de_midi(
                    [[a.strftime("%H:%M"), b.strftime("%H:%M")]
                     for a, b in res["periodes"].get(j, [])]),
                "cible": {k: v for k, v in (W.conf_pause(res.get("conf") or {})).items()
                          if k in ("client", "projet", "commentaire", "heures")},
            },
            "surcharge": surcharge or None,
            "valide": any("[timesheet:" in (s.get("libelle") or "") for s in saisies)
                      or bool(surcharge.get("valide_sans_ajout")),
        })
    return {"periode": res["libelle"], "jours": sortie}


def _fmt(minutes):
    return f"{minutes/60:.1f} h"


if __name__ == "__main__":
    sys.exit(main())
