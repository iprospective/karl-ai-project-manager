#!/usr/bin/env python3
"""pm-mep-watch — la file « à vérifier en prod » se rappelle à nous (RM3278, lot B de RM2853).

`en_mep` veut dire, depuis RM2893 : **déployé en prod, dernière vérification avant fermeture**,
et le ticket est réassigné au demandeur. Mesuré le 2026-09-20 sur les 21 tickets en attente de
prod de `pm-ai-agents` : **18 avaient déjà leur code en prod**, et le plus ancien attendait
depuis 14 jours (RM2889). Ce n'est donc pas une file de déploiement, c'est une **file d'attente
humaine** — invisible parce que rien ne la relance. L'étude RM2853 en a fait son lot le plus
rentable : l'acte de MEP tient en un `core update`, c'est la vérification qui ne se fait pas.

Ce que fait cet outil : il cherche les tickets dont on peut **prouver** que le code est en prod,
mesure depuis combien de temps ils attendent, et le dit dans le fil de notifications
(`pm_notify`, RM2792/RM3177) — une entrée par ticket, dont la clé est stable : ré-émettre ne
duplique pas, ça remonte. Quand le ticket bouge, l'entrée est marquée traitée.

## Deux niveaux de preuve, et on dit lequel

    checkout  le checkout de prod est LOCAL (le projet PM : `.mmi-pm-core`) → filiation directe
              des commits : `merge-base --is-ancestor <branche du ticket> <HEAD de prod>`.
    branche   la prod suit une branche déclarée dans `project/environments.md` (`branch:`) → on
              prouve que le code y est mergé. Que le serveur ait tiré cette branche n'est PAS
              vérifiable sans SSH : le message le dit, il ne le suppose pas.

Jamais les dates : les horloges des machines sont décalées, et `git log --grep` attrape le
commit qui *cite* le ticket (leçon « Prod réelle ≠ main »).

## Ce qui est notifié, et ce qui ne l'est pas

    en_mep + preuve + attente ≥ N jours  → warn  : « à vérifier en prod, puis fermer »
    a_mep  + preuve                      → info  : le code est en prod, le statut est en retard
    pas de preuve                        → RIEN  : compté, dit dans le rapport, jamais notifié —
                                           un ticket dont la MEP n'a pas eu lieu est un AUTRE
                                           problème (et le supposer déployé serait un mensonge).

Usage :
    pm-mep-watch.py                 # rapport, aucune écriture
    pm-mep-watch.py --days 7        # autre seuil (défaut : 3)
    pm-mep-watch.py --apply         # émet et résout les notifications (le job du scheduler)
    pm-mep-watch.py --json          # pour le cockpit
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig      # noqa: E402
from pm_output import out          # noqa: E402
from pm_think import is_task_sheet  # noqa: E402
import pm_notify                   # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

JOB = "mep-watch"
SUIVIS = ("en_mep", "a_mep")
DEFAUT_JOURS = 3


# ── fonctions pures ───────────────────────────────────────────────────────────

def jours_attente(fm, aujourdhui=None):
    """Jours écoulés depuis l'entrée dans le statut COURANT. None si indatable.

    On lit `status_history` (la dernière entrée qui porte le statut courant) et non
    `updated` : une note, un tick de conso ou un cochage rafraîchissent `updated` et
    feraient croire le ticket jeune alors qu'il attend depuis un mois.
    """
    courant = (fm or {}).get("status")
    at = None
    for h in reversed((fm or {}).get("status_history") or []):
        if isinstance(h, dict) and h.get("status") == courant and h.get("at"):
            at = str(h["at"])[:10]
            break
    if not at:
        at = str((fm or {}).get("updated") or "")[:10] or None
    if not at:
        return None
    try:
        d = datetime.strptime(at, "%Y-%m-%d").date()
    except ValueError:
        return None
    return max(0, ((aujourdhui or date.today()) - d).days)


def verdict(statut, preuve, jours, seuil=DEFAUT_JOURS):
    """(niveau, message) à notifier, ou (None, motif) s'il n'y a rien à dire. PURE.

    `preuve` : None (pas de preuve), "checkout" ou "branche <nom>".
    """
    if statut not in SUIVIS:
        return None, "statut hors file de MEP"
    if not preuve:
        return None, "code en prod non prouvable — non notifié"
    comment = ("filiation des commits depuis le checkout de prod" if preuve == "checkout"
               else f"mergé dans la branche que la prod suit ({preuve.split(' ', 1)[-1]}) — "
                    "le pull côté serveur n'est pas vérifié")
    if statut == "a_mep":
        return "info", ("le code est déjà en prod alors que le ticket attend encore sa MEP — "
                        f"statut en retard ({comment}). Passer en `en_mep`, ou dire ce qui manque.")
    if jours is None:
        return None, "attente indatable"
    if jours < seuil:
        return None, f"en prod depuis {jours} j (< {seuil})"
    return "warn", (f"déployé en prod depuis {jours} jours et toujours pas vérifié. "
                    f"Dernière étape avant fermeture : jouer la colonne « Prod » de son protocole "
                    f"de test, puis fermer ({comment}).")


# ── résolution de la preuve ───────────────────────────────────────────────────

def _git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo)] + list(args),
                           capture_output=True, text=True, timeout=20)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _frontmatter(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    if not txt.startswith("---"):
        return {}
    try:
        return yaml.safe_load(txt.split("---", 2)[1]) or {}
    except Exception:  # noqa: BLE001 — une fiche illisible ne casse pas la veille
        return {}


def env_prod(project_dir):
    """L'environnement `prod` déclaré par le projet, ou {}."""
    f = Path(project_dir) / "project" / "environments.md"
    if not f.is_file():
        return {}
    envs = (_frontmatter(f).get("environments") or [])
    for e in envs:
        if isinstance(e, dict) and e.get("name") == "prod":
            return e
    return {}


def depots(workspace):
    """Dépôts git interrogeables d'un workspace : les bares de `repos/`, puis les worktrees."""
    ws = Path(workspace)
    trouves = [p for p in sorted((ws / "repos").glob("*.git"))] if (ws / "repos").is_dir() else []
    if (ws / ".git").exists():
        trouves.append(ws)
    trouves += [p for p in sorted((ws / "envs").glob("*")) if (p / ".git").exists()]
    return trouves


def workspace_de(project_dir):
    """Le workspace de code d'un projet PM, par le symlink canonique `workspace`."""
    wl = Path(project_dir) / "workspace"
    try:
        if wl.is_symlink() and wl.resolve().is_dir():
            return wl.resolve()
    except OSError:
        pass
    return None


def checkout_prod_pm(cfg):
    """Le checkout de PRODUCTION du code PM, ou None. Jamais de chemin codé en dur.

    Deux voies, dans cet ordre : `PM_CORE_DIR` (posé par le runtime), puis le dépôt qui
    CONTIENT le dossier des projets (`PROJECTS_PATH` vit dans le checkout de prod). On
    refuse un worktree de session (`envs/…`) : il disparaît à la livraison, et le prendre
    pour la prod ferait conclure « en prod » sur du code qui n'y est pas.
    """
    import os
    cands = [os.environ.get("PM_CORE_DIR")]
    racine = getattr(cfg, "projects_root", None)
    if racine:
        rc, top = _git(Path(racine).parent, "rev-parse", "--show-toplevel")
        if rc == 0 and top:
            cands.append(top)
    for c in cands:
        if not c:
            continue
        d = Path(c)
        if f"{os.sep}envs{os.sep}" in str(d):
            continue
        if (d / ".git").exists() and (d / "scripts").is_dir():
            return d
    return None


def preuve_prod(cfg, project_dir, branche):
    """(preuve, detail) — comment on sait que `branche` est en prod, ou (None, motif).

    Ordre voulu : le checkout LOCAL de prod d'abord (preuve directe), la branche de prod
    ensuite (preuve que le code y est, pas que le serveur l'a tirée).
    """
    if not branche:
        return None, "le ticket ne dit pas sur quelle branche il a été fait (git.branch vide)"
    ws = workspace_de(project_dir)
    repos = depots(ws) if ws else []
    sha = ""
    for r in repos:
        for ref in (branche, f"origin/{branche}"):
            rc, val = _git(r, "rev-parse", "--verify", "-q", ref)
            if rc == 0 and val:
                sha = val
                break
        if sha:
            break
    if not sha:
        return None, f"branche `{branche}` introuvable dans les dépôts locaux du workspace"

    # 1. checkout de prod local — cas du projet PM lui-même. La sélection se fait d'elle-même :
    # une branche d'un autre projet n'existe pas dans ce dépôt, donc `rev-parse` y échoue.
    prod_local = checkout_prod_pm(cfg)
    if prod_local:
        rc, sha_core = _git(prod_local, "rev-parse", "--verify", "-q", branche)
        if rc != 0 or not sha_core:
            rc, sha_core = _git(prod_local, "rev-parse", "--verify", "-q", f"origin/{branche}")
        rc2, head = _git(prod_local, "rev-parse", "HEAD")
        if sha_core and rc2 == 0 and head:
            rc3, _ = _git(prod_local, "merge-base", "--is-ancestor", sha_core, head)
            if rc3 == 0:
                return "checkout", f"{sha_core[:8]} ancêtre du HEAD de prod {head[:8]}"
            return None, (f"branche connue du checkout de prod mais pas encore dans son HEAD "
                          f"({head[:8]}) — core update en attente")
    # 2. branche que la prod suit, déclarée par le projet
    bp = (env_prod(project_dir).get("branch") or "").strip()
    if bp:
        for r in repos:
            for ref in (bp, f"origin/{bp}"):
                rc, tip = _git(r, "rev-parse", "--verify", "-q", ref)
                if rc != 0 or not tip:
                    continue
                rc2, _ = _git(r, "merge-base", "--is-ancestor", sha, tip)
                if rc2 == 0:
                    return f"branche {bp}", f"{sha[:8]} mergé dans {bp} ({tip[:8]})"
        return None, f"pas (encore) mergé dans la branche de prod `{bp}`"
    return None, "aucun checkout de prod local, et le projet ne déclare pas de branche de prod"


# ── balayage ──────────────────────────────────────────────────────────────────

def balayer(cfg, seuil):
    """[(rm_id, statut, jours, preuve, niveau, message|motif, projet)] pour toute la file."""
    lignes = []
    for ent, proj, _ in cfg.iter_projects():
        d = cfg.path("tasks_dir", entity=ent, project=proj)
        if not d.is_dir():
            continue
        project_dir = d.parent
        for f in sorted(d.glob("RM*.md")):
            if not is_task_sheet(f):
                continue
            fm = _frontmatter(f)
            if fm.get("status") not in SUIVIS:
                continue
            rm_id = fm.get("redmine_id")
            if not isinstance(rm_id, int):
                continue
            branche = ((fm.get("git") or {}).get("branch") or "")
            preuve, detail = preuve_prod(cfg, project_dir, branche)
            jours = jours_attente(fm)
            niveau, msg = verdict(fm.get("status"), preuve, jours, seuil)
            lignes.append({"rm": rm_id, "statut": fm.get("status"), "jours": jours,
                           "preuve": preuve, "detail": detail, "niveau": niveau,
                           "message": msg, "projet": f"{ent}/{proj}",
                           "titre": str(fm.get("title") or "")[:70]})
    return lignes


def appliquer(lignes):
    """Émet les notifications dues, résout celles qui ne le sont plus. (emises, resolues)."""
    dus = {}
    for l in lignes:
        if l["niveau"]:
            e = pm_notify.add("system", l["niveau"], f"RM{l['rm']} — {l['message']}",
                              job=JOB, rm=str(l["rm"]), jours=l["jours"], preuve=l["preuve"])
            if e:
                dus[e.get("id")] = l["rm"]
    encore = {str(l["rm"]) for l in lignes if l["niveau"]}
    resolues = [e["id"] for e in pm_notify.feed(etat="ouvert", origine="system", limit=1000)
                if e.get("job") == JOB and str(e.get("rm")) not in encore]
    n = pm_notify.mark(resolues, "traite") if resolues else 0
    return len(dus), n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=DEFAUT_JOURS,
                    help=f"seuil d'attente avant de notifier (défaut : {DEFAUT_JOURS})")
    ap.add_argument("--apply", action="store_true",
                    help="émet et résout les notifications (défaut : rapport seul)")
    ap.add_argument("--json", action="store_true", help="sortie machine (cockpit)")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    lignes = balayer(cfg, args.days)
    if args.json:
        print(json.dumps(lignes, ensure_ascii=False))
        return 0
    a_dire = [l for l in lignes if l["niveau"]]
    muets = [l for l in lignes if not l["niveau"]]
    print(f"file de MEP : {len(lignes)} ticket(s) · à signaler : {len(a_dire)} "
          f"· silencieux : {len(muets)} (seuil {args.days} j)")
    for l in sorted(a_dire, key=lambda x: -(x["jours"] or 0)):
        print(f"  {'⚠' if l['niveau'] == 'warn' else 'ⓘ'} RM{l['rm']:<5} {l['projet']:<24} "
              f"{l['statut']:<7} {l['jours']} j · {l['preuve']}")
        print(f"      {l['message'][:150]}")
    if muets:
        print("\n  silencieux (jamais notifiés — la preuve manque ou l'attente est courte) :")
        for l in sorted(muets, key=lambda x: x["projet"]):
            print(f"    RM{l['rm']:<5} {l['projet']:<24} {l['statut']:<7} {l['message']}"
                  + (f" · {l['detail']}" if l["detail"] else ""))
    if not args.apply:
        print(f"\n(rapport seul : {len(a_dire)} notification(s) seraient émises — --apply pour le faire)")
        return 0
    emises, resolues = appliquer(lignes)
    out.op("mep-watch", extra=f"{emises} notification(s) · {resolues} résolue(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
