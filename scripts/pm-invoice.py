#!/usr/bin/env python3
"""pm-invoice — proposer les factures d'un mois depuis les saisies Redmine (RM2891).

    mmi-pm invoice --month 2026-08               # rapport .md + proposition .yml (rien n'est créé)
    mmi-pm invoice --month 2026-08 --client pisceen

Le temps facturable est celui que tu as saisi dans Redmine — à la main ou par
`mmi-pm timesheet`. La commande le regroupe par client (projet Redmine → client PM,
projets mutualisés éclatés selon leur clé), par activité (→ service du catalogue
ERP) ou par tâche, applique le tarif de la dernière facture du client, et rédige la
note publique au modèle habituel, mises en production du mois comprises.

L'ERP est le provider de l'axe `erp` du registre (Dolibarr, `dolibarr-ipro`).
Réglages : `<core>/var/users/<user>/invoice.yml` (RM3318 ; modèle : `invoice.example.yml`).
"""
import argparse
import calendar
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_invoice as I
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


def charger_conf(chemin):
    import pm_paths
    p = Path(chemin).expanduser() if chemin else pm_paths.user_conf_file("invoice.yml")
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def titres_tickets(url, key, ids):
    """Le sujet de chaque ticket cité, pour que les lignes disent ce qu'elles couvrent.

    Lus par paquets : une requête par ticket coûterait des centaines d'allers-retours
    sur un mois chargé. Un ticket introuvable (supprimé, hors périmètre) est ignoré —
    sa ligne le nommera par son numéro.
    """
    from redmine_utils import http_json
    out = {}
    ids = sorted({int(i) for i in ids if i})
    for i in range(0, len(ids), 50):
        lot = ids[i:i + 50]
        code, b = http_json("GET", f"{url}/issues.json?issue_id={','.join(map(str, lot))}"
                                   f"&status_id=*&limit=100", key)
        if code != 200:
            continue
        for issue in b.get("issues", []):
            out[int(issue["id"])] = (issue.get("subject") or "").strip()
    return out


def saisies_redmine(url, key, user_id, debut, fin):
    """Saisies de l'utilisateur sur la période, avec l'identifiant de leur projet."""
    from redmine_utils import http_json
    projets, noms, off = {}, {}, 0
    while True:
        code, body = http_json("GET", f"{url}/projects.json?limit=100&offset={off}", key)
        if code != 200:
            break
        for p in body.get("projects", []):
            projets[p["id"]] = p.get("identifier") or str(p["id"])
            # Le NOM lisible sert à nommer un projet mutualisé au client : « Dolibarr »
            # se comprend, « synchro-prestashop-dolibarr » non.
            noms[p.get("identifier") or str(p["id"])] = (p.get("name") or "").strip()
        off += 100
        if off >= body.get("total_count", 0):
            break
    sortie, off = [], 0
    while True:
        code, body = http_json(
            "GET", f"{url}/time_entries.json?user_id={user_id}&from={debut}&to={fin}"
            f"&limit=100&offset={off}", key)
        if code != 200:
            sys.exit(f"Redmine : lecture des saisies refusée (HTTP {code}).")
        for t in body.get("time_entries", []):
            pid = (t.get("project") or {}).get("id")
            ident = projets.get(pid, str(pid))
            sortie.append(I.Saisie(
                jour=t["spent_on"], heures=float(t["hours"]),
                projet=ident, projet_nom=noms.get(ident, ""),
                ticket=(t.get("issue") or {}).get("id"),
                activite_id=(t.get("activity") or {}).get("id"),
                activite=(t.get("activity") or {}).get("name", ""),
                commentaire=t.get("comments") or ""))
        off += 100
        if off >= body.get("total_count", 0):
            break
    return sortie


def normaliser_entite(valeur):
    """Identifiant d'entité, que le résolveur rende un slug ou le chemin de son dossier."""
    return Path(str(valeur)).name if "/" in str(valeur) else str(valeur)


def table_projets(cfg, conf, identifiants):
    """Identifiant Redmine → client : table déclarée, puis manifeste PM (`redmine.project_id`)."""
    table = dict(conf.get("redmine_projects") or {})
    for ident in identifiants:
        if ident in table:
            continue
        try:
            ent, _proj = cfg.find_project_by_redmine_id(ident)
        except Exception:
            ent = None
        if ent:
            # Piège : `find_project_by_redmine_id` rend le CHEMIN du dossier client, pas son
            # identifiant. Le prendre tel quel classait tout le temps client en « interne ».
            table[ident] = normaliser_entite(ent)
    return table


def tiers_des_clients(clients, tiers, conf):
    """Client PM → id de tiers ERP : table déclarée (par nom), sinon correspondance de nom
    ou d'alias. Une correspondance déduite est signalée, jamais tue."""
    declares = conf.get("tiers") or {}
    par_nom = {v["nom"].lower(): k for k, v in tiers.items()}
    sortie, deduits = {}, {}
    for c in clients:
        if c in declares:
            tid = par_nom.get(str(declares[c]).lower())
            if tid:
                sortie[c] = tid
            continue
        for tid, v in tiers.items():
            if c.lower() in v["nom"].lower() or c.lower() in (v["alias"] or "").lower():
                sortie[c], deduits[c] = tid, v["nom"]
                break
    return sortie, deduits


def rapport(props, debut, fin, orphelins, internes, deduits, tiers, services_ref,
            hors_facturation=None):
    L = [f"# Factures proposées — {debut:%m/%Y}", "",
         f"Période du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}. **Rien n'est créé** : relire, amender la "
         "proposition `.yml`, puis appliquer.", ""]
    total = sum(p["total_ht"] or 0 for p in props)
    L += [f"**{len(props)} facture(s), {total:,.2f} € HT**".replace(",", " "), ""]
    for p in props:
        nom = tiers.get(p["tiers"], {}).get("nom", "—") if p["tiers"] else "—"
        L += [f"## {p['client']} → {nom}" + (" *(tiers déduit par le nom)*" if p["client"] in deduits else ""),
              "", f"Tarif : **{p['tarif']} €/h** (dernière facture)" if p["tarif"] else "Tarif : **à saisir**", "",
              "| ligne | heures | montant HT |", "|---|---|---|"]
        for l in p["lignes"]:
            lib = services_ref.get(l["service"], l["libelle"]) if l["service"] else f"{l['libelle']} *(ligne libre)*"
            mt = f"{l['heures'] * p['tarif']:.2f}" if p["tarif"] else "—"
            L.append(f"| {lib} | {l['heures']:.2f} | {mt} |")
        L += [f"| **total** | **{p['heures']:.2f}** | **{p['total_ht'] or '—'}** |", "",
              "Note publique :", "", "```", p["note_publique"], "```", ""]
        L += [f"> ⚠ {a}" for a in p["alertes"]] + ([""] if p["alertes"] else [])
    if internes:
        L += ["## Non facturé — interne ou perso", ""]
        L += [f"- {c} : {h:.2f} h" for c, h in sorted(internes.items())] + [""]
    if hors_facturation:
        h = sum(x.heures for x in hors_facturation)
        L += ["## Hors facturation", "",
              f"Projets déclarés `non_facturable` : **{h:.2f} h** écartées, "
              f"{len(hors_facturation)} saisie(s).", ""]
        L += [f"- {s.jour} {s.projet} {s.heures:.2f} h — {s.commentaire[:60]}"
              for s in hors_facturation] + [""]
    if orphelins:
        L += ["## ⚠ Saisies sans client", "",
              "Projet Redmine non rattaché : à déclarer dans `redmine_projects`.", ""]
        L += [f"- {s.jour} {s.projet} {s.heures:.2f} h — {s.commentaire[:60]}" for s in orphelins] + [""]
    return "\n".join(L)


def appliquer(prop, erp, catalogue, factures, conf, args):
    """Crée les brouillons depuis la proposition AMENDÉE. Ne valide jamais, ne double jamais.

    On relit le fichier tel qu'il a été corrigé — aucun recalcul : ce que l'humain a
    relu est ce qui part. Une facture déjà posée pour ce client et ce mois est
    reconnue à sa marque et laissée intacte.
    """
    import pm_erp
    ref_vers_id = {v["ref"]: k for k, v in catalogue.items()}
    projet_du_tiers = {}
    for f in factures:
        projet_du_tiers.setdefault(f.tiers_id, f.projet_id)
    quand = date.fromisoformat(args.date) if args.date else date.today()
    cree, ignore, refus = [], [], []
    for f in prop.get("factures", []):
        client = f.get("client")
        if args.client and client != args.client:
            continue
        if not f.get("valide"):
            refus.append((client, ", ".join(f.get("alertes") or ["marquée non valide"])))
            continue
        m = I.marque(client, prop.get("periode", args.month))
        existante = I.deja_facture(m, erp.factures_du_tiers(f["tiers"]))
        if existante and getattr(args, "replace", False):
            # Remplacer : on supprime le BROUILLON précédent, jamais autre chose —
            # `supprimer_brouillon` relit le statut sur le serveur et refuse le reste.
            if args.dry_run:
                print(f"  [dry-run] {client:12} remplacerait "
                      f"{existante['ref'] or existante['id']}")
            else:
                try:
                    ref = erp.supprimer_brouillon(existante["id"])
                    print(f"  ↺ {client:12} ancien brouillon {ref} supprimé")
                except Exception as e:
                    refus.append((client, f"remplacement impossible : {e}"))
                    continue
            existante = None
        if existante:
            ignore.append((client, existante["ref"] or existante["id"]))
            continue
        # La description part dans le champ `desc` de Dolibarr. Sous un service du
        # catalogue elle complète son intitulé ; sans service, le libellé reste la
        # seule identité de la ligne, et la description le prolonge.
        lignes = []
        for l in f.get("lignes", []):
            if not l.get("heures"):
                continue
            desc = (l.get("description") or "").strip()
            if not l.get("service"):
                base = l.get("libelle", "")
                desc = f"{base} — {desc}" if desc and base else (desc or base)
            lignes.append(pm_erp.Ligne(quantite=l["heures"], prix_unitaire=f["tarif"],
                                       service_id=ref_vers_id.get(l.get("service")),
                                       libelle=desc, tva=f.get("tva")))
        if args.dry_run:
            print(f"  [dry-run] {client:12} {f['heures']:6.2f} h × {f['tarif']} = "
                  f"{f['total_ht']:9.2f} € HT · {len(lignes)} ligne(s) · brouillon")
            cree.append((client, "—"))
            continue
        fid = erp.creer_brouillon(f["tiers"], lignes, note_publique=f.get("note_publique", ""),
                                  note_privee=m, quand=quand,
                                  projet_id=projet_du_tiers.get(f["tiers"]))
        cree.append((client, fid))
        print(f"  ✓ {client:12} brouillon #{fid} · {f['total_ht']:.2f} € HT")
    verbe = "à créer" if args.dry_run else "créés"
    print(f"✓ factures {prop.get('periode')} : {len(cree)} brouillon(s) {verbe}"
          + (f", {len(ignore)} déjà facturé(s)" if ignore else "")
          + (f", {len(refus)} écarté(s)" if refus else ""))
    for client, ref in ignore:
        print(f"  = {client} : déjà facturé ({ref}) — rien de créé")
    for client, raison in refus:
        print(f"  ⚠ {client} : {raison}")
    return 0


#: Emplacement hérité, rapatrié une fois (RM3229, 2026-10-13). Même règle que le
#: timesheet : ce que le PM produit en tournant vit dans le dossier de son utilisateur,
#: jamais dans son home.
ETAT_HERITE = Path.home() / ".local" / "state" / "mmi-pm" / "invoice"


def dossier_etat(cfg=None, migrer=True):
    """`<core>/var/users/<user>/invoice`, l'ancien emplacement rapatrié s'il existe."""
    import pm_paths
    cible = pm_paths.user_conf_dir(pm_dir=getattr(cfg, "pm_dir", None)) / "invoice"
    cible.mkdir(parents=True, exist_ok=True)
    if migrer and ETAT_HERITE.is_dir() and ETAT_HERITE != cible and not any(cible.iterdir()):
        deplaces = 0
        for item in ETAT_HERITE.iterdir():
            if (cible / item.name).exists():
                continue
            try:
                item.rename(cible / item.name)
            except OSError:
                import shutil
                shutil.move(str(item), str(cible / item.name))
            deplaces += 1
        if deplaces:
            print(f"  ↪ factures reprises depuis {ETAT_HERITE} ({deplaces}) → {cible}",
                  file=sys.stderr)
    return cible


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--month", required=True, help="mois facturé (AAAA-MM)")
    ap.add_argument("--client", help="un seul client PM")
    ap.add_argument("--config", help="réglages (défaut : <core>/var/users/<user>/invoice.yml)")
    ap.add_argument("--out", help="dossier de sortie (défaut : <core>/var/users/<user>/invoice)")
    ap.add_argument("--apply", action="store_true",
                    help="crée les BROUILLONS dans l'ERP depuis la proposition amendée")
    ap.add_argument("--dry-run", action="store_true", help="avec --apply : n'écrit rien")
    ap.add_argument("--replace", action="store_true",
                    help="avec --apply : remplace le BROUILLON déjà créé pour ce mois "
                         "(supprimé puis recréé ; une facture validée est refusée)")
    ap.add_argument("--date", help="date des factures (AAAA-MM-JJ, défaut : aujourd'hui)")
    args = ap.parse_args()

    an, mois = (int(x) for x in args.month.split("-"))
    debut, fin = date(an, mois, 1), date(an, mois, calendar.monthrange(an, mois)[1])
    cfg = PMConfig.load()
    conf = charger_conf(args.config)
    uid = conf.get("user_id")
    if not uid:
        sys.exit("`user_id:` requis dans invoice.yml : l'utilisateur Redmine dont on facture le temps.")

    from redmine_utils import redmine_creds
    from pm_registry import Registry
    import pm_erp
    url, key = redmine_creds()[:2]
    saisies = saisies_redmine(url, key, uid, debut.isoformat(), fin.isoformat())
    types = {e: (cfg.client_meta(e) or {}).get("type") for e, _ in cfg.iter_entities()}
    table = table_projets(cfg, conf, {s.projet for s in saisies})
    # Les projets qu'on ne facture pas sortent AVANT le rattachement : sinon ils
    # reviendraient chaque mois dans les « saisies sans client », à corriger sans fin.
    saisies, hors_facturation = I.ecarter_non_facturables(
        saisies, conf.get("non_facturable"))
    rattachees, orphelins = I.rattacher(saisies, table, set(types) | set(conf.get("multi_client") or {}),
                                        {k: [(x["client"], x["weight"]) for x in v]
                                         for k, v in (conf.get("multi_client") or {}).items()})
    facturables = [s for s in rattachees if types.get(s.client) == "client"
                   and (not args.client or s.client == args.client)]
    internes = {}
    for s in rattachees:
        if types.get(s.client) != "client":
            internes[s.client] = internes.get(s.client, 0) + s.heures * s.part

    erp = pm_erp.get_erp_provider(registry=Registry.from_config(cfg.providers))
    tiers, factures, catalogue = erp.tiers(), erp.factures(), erp.services()
    if args.apply:
        chemin = (Path(args.out).expanduser() if args.out
                  else dossier_etat(cfg)) / f"{args.month}.yml"
        if not chemin.is_file():
            sys.exit(f"{chemin} absent — lancer d'abord `mmi-pm invoice --month {args.month}`.")
        prop = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        return appliquer(prop, erp, catalogue, factures, conf, args)
    clients = sorted({s.client for s in facturables})
    tiers_c, deduits = tiers_des_clients(clients, tiers, conf)
    tarifs = {c: erp.dernier_tarif(tiers_c[c], factures) for c in clients if c in tiers_c}
    # Le taux de TVA suit la même règle que le tarif : la dernière facture fait foi.
    tva = {c: erp.dernier_taux_tva(tiers_c[c], factures) for c in clients if c in tiers_c}
    services = {int(k) if str(k).isdigit() else k: v for k, v in (conf.get("services") or {}).items()}
    groupement = {c: (conf.get("clients") or {}).get(c, {}).get("groupement", "activite") for c in clients}
    meps = {c: I.mises_en_production(cfg, c, debut, fin) for c in clients}
    titres = titres_tickets(url, key, {s.ticket for s in facturables if s.ticket})
    props = I.proposer(facturables, debut, fin, tiers_par_client=tiers_c, tarifs=tarifs,
                       services_par_activite=services, groupement=groupement, meps=meps,
                       titres=titres, tva=tva)

    dossier = Path(args.out).expanduser() if args.out else dossier_etat(cfg)
    dossier.mkdir(parents=True, exist_ok=True)
    ref_libelle = {v["ref"]: f"{v['ref']} {v['libelle']}" for v in catalogue.values()}
    md = dossier / f"{args.month}.md"
    md.write_text(rapport(props, debut, fin, orphelins, internes, deduits, tiers, ref_libelle,
                          hors_facturation=hors_facturation),
                  encoding="utf-8")
    yml = dossier / f"{args.month}.yml"
    yml.write_text(yaml.safe_dump({"periode": args.month, "genere": datetime.now().isoformat(timespec="minutes"),
                                   "factures": props}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    total = sum(p["total_ht"] or 0 for p in props)
    print(f"✓ factures {args.month} : {len(props)} proposée(s), {sum(p['heures'] for p in props):.2f} h, "
          f"{total:.2f} € HT — rien n'est créé")
    for p in props:
        print(f"  {p['client']:10} {p['heures']:7.2f} h × {p['tarif'] or '?'} → "
              f"{p['total_ht'] if p['total_ht'] is not None else '?'} € HT"
              + (f"  ⚠ {', '.join(p['alertes'])}" if p["alertes"] else ""))
    if hors_facturation:
        print(f"  · {sum(x.heures for x in hors_facturation):.2f} h écartées "
              f"(projets non facturables)")
    if orphelins:
        print(f"  ⚠ {len(orphelins)} saisie(s) sans client — voir le rapport")
    print(f"  rapport : {md}\n  proposition : {yml}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
