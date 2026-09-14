#!/usr/bin/env python3
"""pm-notify — le fil de notifications de l'instance : lire, marquer, émettre (RM2792).

Le journal (`mmi-pm log-tail`) est une trace où l'on cherche après coup. Ce fil-ci est une FILE : chaque
entrée attend d'être lue puis traitée. Il agrège l'ordonnanceur, les sessions et le système.

  pm-notify                       ce qui attend (tout sauf traité), du plus récent au plus ancien
  pm-notify --all                 y compris ce qui est traité
  pm-notify --origin scheduler    filtre par source (scheduler, session, agent, forge, mail, system)
  pm-notify --level warn          à partir de ce niveau
  pm-notify --read <id>…          marquer lu · --done <id>… marquer traité · --all avec --done : tout
  pm-notify --add "message" --origin system [--level warn] [--ref RM123]
  pm-notify --add "…" --user mathieu [--private]   adressée à quelqu'un ; --private = à elle seule
  pm-notify --user mathieu        ce qui CONCERNE cette personne (ses entrées + celles de l'instance)
  pm-notify --as claire           lire au nom de quelqu'un d'autre (défaut : PM_NOTIFY_OWNER, sinon
                                  l'utilisateur courant) — décide des entrées privées visibles
  --json                          pour le cockpit et les scripts

Une notification ré-émise à l'identique ne se duplique pas : elle remonte, avec son compteur. C'est
l'anti-répétition — un travail qui échoue toutes les heures produit une ligne, pas vingt-quatre.
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_notify as N                                   # noqa: E402

ICONE = {"info": "ℹ️", "warn": "⚠️", "critical": "🔴"}
MARQUE = {"neuf": "●", "lu": "○", "traite": "✓"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="inclure ce qui est traité (ou, avec --done, tout marquer)")
    ap.add_argument("--origin"); ap.add_argument("--level", choices=N.NIVEAUX)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--read", nargs="*", metavar="ID"); ap.add_argument("--done", nargs="*", metavar="ID")
    ap.add_argument("--add", metavar="MESSAGE"); ap.add_argument("--ref"); ap.add_argument("--job")
    ap.add_argument("--user", help="destinataire (avec --add) ou filtre d'affichage (en lecture)")
    ap.add_argument("--private", action="store_true", help="avec --add : visible du seul destinataire")
    ap.add_argument("--as", dest="viewer", metavar="UTILISATEUR",
                    help="lire au nom de cette personne (défaut : PM_NOTIFY_OWNER, sinon le compte courant)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    # Qui lit : c'est ce qui décide des entrées PRIVÉES rendues. En ligne de commande, l'appelant a
    # déjà le fichier sous la main — se nommer par défaut est honnête, pas laxiste.
    qui = a.viewer or N.owner() or getpass.getuser()

    if a.add:
        e = N.add(a.origin or "system", a.level or "info", a.add,
                  user=a.user, private=a.private, ref=a.ref, job=a.job)
        if not e:
            sys.exit("ERREUR : notification privée sans --user, ou fil non écrivable")
        print(json.dumps(e, ensure_ascii=False) if a.json
              else f"✓ notification {e['id']} [{e['level']}] {e['msg'][:70]}"
                   + (f" (×{e['repeats']})" if e.get("repeats", 1) > 1 else ""))
        return 0

    for gestes, etat in ((a.read, "lu"), (a.done, "traite")):
        if gestes is None:
            continue
        ids = gestes or ([e["id"] for e in N.feed(etat="ouvert", limit=1000, viewer=qui)] if a.all else [])
        if not ids:
            sys.exit(f"ERREUR : donne au moins un identifiant, ou --all pour tout marquer « {etat} »")
        print(f"✓ {N.mark(ids, etat, viewer=qui)} notification(s) → {etat}")
        return 0

    fil = N.feed(etat=None if a.all else "ouvert", origine=a.origin, niveau=a.level, limit=a.limit,
                 viewer=qui, user=a.user)
    if a.json:
        print(json.dumps({"feed": fil, "counts": N.counts(viewer=qui, user=a.user),
                          "viewer": qui, "users": N.users()}, ensure_ascii=False, indent=1))
        return 0
    if not fil:
        print("rien n'attend" if not a.all else "le fil est vide")
        return 0
    for e in fil:
        rep = f" ×{e['repeats']}" if e.get("repeats", 1) > 1 else ""
        refs = " ".join(f"{k}={e[k]}" for k in ("job", "rm", "sid", "ref") if e.get(k))
        a_qui = ("🔒 " if e.get("private") else "@") + e["user"] if e.get("user") else ""
        print(f"  {MARQUE.get(e.get('etat'), '·')} {e['id']}  {ICONE.get(e.get('level'), '•')} "
              f"{(e.get('last') or e.get('ts', ''))[:16]}  {e.get('origin', ''):9} {e.get('msg', '')[:70]}{rep}"
              + (f"  · {a_qui}" if a_qui else "") + (f"  · {refs}" if refs else ""))
    c = N.counts(viewer=qui, user=a.user)
    print(f"\n  {c['open']} en attente ({c['neuf']} non lue(s))" + (f", pire niveau : {c['worst']}" if c["worst"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
