#!/usr/bin/env python3
"""pm-bus-drain — exécute les abonnements des modules sur les événements en attente (RM3145, lot 2).

Les émetteurs de PM sont des processus courts : ils DÉPOSENT un événement et meurent. Ce drain est
ce qui le fait vivre — il lit ce qui attend, cherche qui s'y est abonné parmi les modules actifs,
lance, et marque. L'ordonnanceur l'appelle : pas de minuterie de plus (RM3013).

Trois règles, qui tiennent le reste debout :

  1. **Un abonné qui échoue n'affecte ni l'émetteur ni les autres.** L'émetteur est parti depuis
     longtemps ; les autres abonnés du même événement sont lancés quoi qu'il arrive.
  2. **Un échec ne rejoue pas indéfiniment.** L'événement est marqué drainé AVEC son erreur, et le
     fil de notifications le dit. Un abonné cassé qui rejouerait en boucle noierait le journal, et
     l'erreur passerait d'autant plus inaperçue.
  3. **Un module bloqué ou désactivé n'écoute pas.** Réagir sans être chargé serait le pire des deux
     mondes : actif à moitié, et impossible à diagnostiquer.

  pm-bus-drain                 draine ce qui attend
  pm-bus-drain --dry-run       dit ce qui serait lancé, ne lance rien, ne marque rien
  pm-bus-drain --limit 50      borne le nombre d'événements traités en un passage
  --json                          pour les scripts
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_bus as BUS                                   # noqa: E402
import pm_modules as MOD                                 # noqa: E402

TIMEOUT = 120


def _notifie(niveau, message, **champs):
    try:
        import pm_notify
        pm_notify.add("system", niveau, message, **champs)
    except Exception:      # noqa: BLE001 — le fil indisponible ne casse pas le drain
        pass


def lance(t, evenement, racine: Path, dry=False) -> dict:
    """Exécute un abonnement. Rend le compte rendu — jamais d'exception vers l'appelant."""
    cmd = list(t.run)
    env_extra = {"PM_EVENT_NAME": evenement.get("name", ""),
                 "PM_EVENT_ID": evenement.get("id", ""),
                 "PM_EVENT_PAYLOAD": json.dumps(evenement.get("payload") or {}, ensure_ascii=False)}
    if dry:
        return {"module": t.module, "cmd": " ".join(cmd), "dry_run": True, "ok": True}
    import os
    env = dict(os.environ)
    env.update(env_extra)
    try:
        p = subprocess.run(cmd, cwd=str(racine), capture_output=True, text=True,
                           timeout=TIMEOUT, env=env)
    except (OSError, subprocess.SubprocessError) as e:
        return {"module": t.module, "cmd": " ".join(cmd), "ok": False, "error": str(e)[:300]}
    return {"module": t.module, "cmd": " ".join(cmd), "ok": p.returncode == 0,
            "rc": p.returncode, "err": (p.stderr or "").strip()[-300:]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    racine = HERE.parent
    attente = BUS.pending(limit=a.limit)
    abonnes = [t for t in MOD.triggers() if t.ok]
    casses = [t for t in MOD.triggers() if not t.ok]
    for t in casses:
        # Un abonnement invalide ne s'exécute pas, mais il ne se tait pas non plus : sinon le module
        # semble branché et ne réagit jamais.
        _notifie("warn", f"abonnement invalide dans le module « {t.module} » : " + " ; ".join(t.errors),
                 job="events-drain", ref=str(t.file))

    traites, lancements = [], []
    for e in attente:
        concernes = [t for t in abonnes if t.concerne(e)]
        if not concernes:
            # Personne n'écoute : l'événement est drainé quand même. Le garder « en attente » pour un
            # abonné qui n'existe pas ferait grossir le journal sans fin.
            traites.append((e["id"], None))
            continue
        echecs = []
        for t in concernes:
            r = lance(t, e, racine, dry=a.dry_run)
            lancements.append(dict(r, event=e["name"], event_id=e["id"]))
            if not r.get("ok"):
                echecs.append(f"{t.module} : " + (r.get("error") or f"code {r.get('rc')}" ))
        if echecs and not a.dry_run:
            _notifie("warn", f"abonné en échec sur « {e['name']} »", job="events-drain",
                     ref=e["id"], detail=" ; ".join(echecs)[:300])
        traites.append((e["id"], " ; ".join(echecs) if echecs else None))

    if not a.dry_run:
        for eid, err in traites:
            BUS.mark_drained(eid, erreur=err)

    resume = {"pending": len(attente), "drained": 0 if a.dry_run else len(traites),
              "runs": lancements, "subscriptions": len(abonnes), "invalid": len(casses),
              "dry_run": bool(a.dry_run)}
    if a.json:
        print(json.dumps(resume, ensure_ascii=False, indent=1))
        return 0
    if not attente:
        print(f"rien à drainer ({len(abonnes)} abonnement(s) déclaré(s))")
        return 0
    print(f"{len(attente)} événement(s) · {len(abonnes)} abonnement(s)"
          + (" · [dry-run]" if a.dry_run else ""))
    for r in lancements:
        print(("  ✓ " if r.get("ok") else "  ✗ ") + f"{r['event']:26} {r['module']:20} {r['cmd'][:60]}")
        if r.get("err"):
            print("      " + r["err"][:200])
    if not lancements:
        print("  (aucun abonné concerné — les événements sont drainés)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
