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


def collecter(conf, debut, fin, verbose=False, cache_dir=None):
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


def saisies_humaines(url, key, user_id, debut, fin):
    """Saisies déjà faites à la main (hors « Tick IA » de l'agent)."""
    from redmine_utils import http_json
    out, offset = [], 0
    while True:
        code, body = http_json(
            "GET", f"{url}/time_entries.json?user_id={user_id}"
            f"&from={debut:%Y-%m-%d}&to={(fin - timedelta(days=1)):%Y-%m-%d}"
            f"&limit=100&offset={offset}", key)
        if code != 200:
            break
        for t in body.get("time_entries", []):
            if (t.get("comments") or "").startswith("Tick IA"):
                continue
            out.append({"jour": t["spent_on"], "minutes": float(t["hours"]) * 60,
                        "rm": str(t["issue"]["id"]) if t.get("issue") else None,
                        "entity": None, "libelle": t.get("comments") or ""})
        offset += 100
        if offset >= body.get("total_count", 0):
            break
    return out


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

    cache_dir = Path(args.out).parent / "cache" if args.out else \
        Path(cfg.pm_dir) / "var" / "timesheet" / "cache"
    events, detail = collecter(conf, debut, fin, args.verbose, cache_dir)
    if not events:
        sys.exit(f"Aucune trace sur la période {libelle} — sources : "
                 + ", ".join(s.get("kind", "?") for s in _sources(conf)))

    resolver = W.TargetResolver(cfg, path_map=conf.get("path_map"))
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
        tours.update(W.rm_par_tour(chemin, debut, fin))
    for e in events:
        rm = tours.get((e.session, e.ts.strftime("%Y-%m-%dT%H:%M")))
        resolver.resolve(e, rm_du_tour=rm)

    regles = W.regles_depuis_config(conf, cfg)
    alloc, periodes, totaux = W.allocate(W.build_intervals(events, params), params)
    alloc = W.eclater_cles_multi(alloc, regles)
    final, ecarte, journal = W.repartir_transversal(alloc, regles, params)

    deduit = []
    if not args.sans_deduction:
        try:
            from pm_paths import PMConfig as _P  # noqa: F401  (env déjà chargé)
            from redmine_utils import redmine_creds
            url, key = redmine_creds()
            uid = args.user_id or conf.get("user_id")
            if uid:
                saisies = saisies_humaines(url, key, uid, debut, fin)
                final, deduit = W.deduire_saisies(final, saisies)
                if args.verbose:
                    print(f"  {len(saisies)} saisies humaines déduites", file=sys.stderr)
        except SystemExit:
            print("  (Redmine injoignable : déduction non appliquée)", file=sys.stderr)

    return {"resolver": resolver,
            "final": final, "ecarte": ecarte, "journal": journal, "periodes": periodes,
            "totaux": totaux, "regles": regles, "params": params, "libelle": libelle,
            "deduit": deduit, "events": len(events), "sources": detail,
            "debut": debut, "fin": fin}


def ecrire_sorties(res, dossier, libelle):
    dossier.mkdir(parents=True, exist_ok=True)
    md = W.rendre_markdown(res["final"], res["ecarte"], res["journal"], res["periodes"],
                           res["totaux"], res["regles"], libelle,
                           quantum=res["params"]["quantum_min"],
                           resolver=res.get("resolver"))
    chemin_md = dossier / f"{libelle}.md"
    chemin_md.write_text(md, encoding="utf-8")
    prop = W.proposition(res["final"], res["journal"], res["params"]["quantum_min"],
                         meta={"periode": libelle, "genere": datetime.now().isoformat(timespec="minutes"),
                               "evenements": res["events"],
                               "sources": [{"kind": k, "path": p, "evenements": n}
                                           for k, p, n in res["sources"]]})
    chemin_yml = dossier / f"{libelle}.yml"
    chemin_yml.write_text(yaml.safe_dump(prop, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
    return chemin_md, chemin_yml, prop


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
    deja = set()
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
                deja.add(c[c.index("[timesheet:"):].split("]")[0] + "]")
        offset += 100
        if offset >= body.get("total_count", 0):
            break

    cree = ignore = erreurs = 0
    for l in lignes:
        marque = f"[timesheet:{l['jour']}#{l.get('client') or '-'}/{l.get('ticket') or '-'}]"
        if marque in deja:
            ignore += 1
            continue
        heures = round(l["minutes"] / 60.0, 2)
        payload = {"time_entry": {
            "spent_on": l["jour"], "hours": heures, "user_id": int(uid),
            "activity_id": args.activity or conf.get("activity_id") or 9,
            "comments": f"{l.get('projet') or ''} — travail assisté {marque}".strip(" —"),
        }}
        if l.get("ticket"):
            payload["time_entry"]["issue_id"] = int(l["ticket"])
        else:
            pid = (conf.get("project_map") or {}).get(f"{l.get('client')}/{l.get('projet')}")
            if not pid:
                erreurs += 1
                continue
            payload["time_entry"]["project_id"] = pid
        if args.dry_run:
            print(f"  [dry-run] {l['jour']} {heures:5.2f} h  "
                  f"{l.get('client')}/{l.get('projet')} "
                  f"{'RM' + str(l['ticket']) if l.get('ticket') else '(projet)'}")
            cree += 1
            continue
        code, _body = http_json("POST", f"{url}/time_entries.json", key, payload)
        if code in (200, 201):
            cree += 1
        else:
            erreurs += 1
    verbe = "à créer" if args.dry_run else "créées"
    print(f"✓ timesheet {periode} : {cree} saisies {verbe}, {ignore} déjà posées"
          + (f", {erreurs} sans cible Redmine" if erreurs else ""))
    return 0 if not erreurs else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--month", help="mois à traiter (AAAA-MM)")
    ap.add_argument("--from", dest="depuis", help="date de début (AAAA-MM-JJ)")
    ap.add_argument("--to", dest="jusqu_a", help="date de fin incluse (AAAA-MM-JJ)")
    ap.add_argument("--out", help="dossier de sortie (défaut : <core>/var/timesheet)")
    ap.add_argument("--config", help="fichier de configuration (défaut : <core>/timesheet.yml)")
    ap.add_argument("--apply", action="store_true",
                    help="crée les saisies Redmine depuis la proposition validée")
    ap.add_argument("--dry-run", action="store_true", help="avec --apply : n'écrit rien")
    ap.add_argument("--user-id", type=int, help="utilisateur Redmine des saisies")
    ap.add_argument("--activity", type=int, help="activité Redmine forcée")
    ap.add_argument("--follow-cap", type=float, help="plafond du temps de suivi (min)")
    ap.add_argument("--quantum", type=int, help="tranche d'arrondi (min)")
    ap.add_argument("--sans-deduction", action="store_true",
                    help="ne pas retrancher les saisies Redmine existantes")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not args.month and not (args.depuis and args.jusqu_a):
        ap.error("--month AAAA-MM, ou --from et --to")

    cfg = PMConfig.load()
    conf = W.charger_config(args.config, cfg=cfg)
    dossier = Path(args.out) if args.out else Path(cfg.pm_dir) / "var" / "timesheet"
    _d, _f, libelle = _periode(args)

    if args.apply:
        chemin = dossier / f"{libelle}.yml"
        if not chemin.is_file():
            sys.exit(f"{chemin} absent — lancer d'abord `mmi-pm timesheet --month {libelle}`.")
        return appliquer(chemin, cfg, conf, args)

    res = calculer(args, cfg, conf)
    md, yml, prop = ecrire_sorties(res, dossier, libelle)
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


def _fmt(minutes):
    return f"{minutes/60:.1f} h"


if __name__ == "__main__":
    sys.exit(main())
