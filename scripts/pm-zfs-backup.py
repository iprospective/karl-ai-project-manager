#!/usr/bin/env python3
"""pm-zfs-backup — snapshots ZFS de la machine, au fil de l'eau (RM3023).

Le 2026-09-06, `/home` n'avait **aucun** snapshot depuis avril 2025 et aucune
sauvegarde externe. Résultat : 42 transcripts de session effacés par la
rétention par défaut de Claude Code étaient définitivement irrécupérables
(RM2997) — il n'existait aucun recours au niveau du système de fichiers.

Trois partis pris :

  1. **Pas de timer dédié.** Le tick se greffe sur un processus qui tourne déjà
     (`pm-task-report`, cron de l'hôte toutes les 30 min). Sur un portable, un
     horaire fixe manquerait la moitié de ses créneaux ; la question utile est
     « le dernier snapshot a-t-il plus d'une heure ? », pas « est-il minuit ? ».
  2. **Aucun droit nouveau.** Tout passe par `pm-zfs-snap.sh`, guichet sudo
     NOPASSWD déjà en place, root-owned, qui refuse un dataset hors périmètre et
     ne peut détruire qu'un `dataset@snapshot`, jamais un dataset nu.
  3. **Une empreinte lisible d'ailleurs.** Le tick tourne sur l'hôte (seul
     endroit où `zfs` existe) ; le contrôle qui le surveille tourne dans le
     conteneur. Ils ne se voient que par le fichier d'empreinte, posé sur le
     montage partagé.

Usage :
    pm-zfs-backup.py --tick        # greffé sur un process existant ; ne dit rien s'il n'y a rien à dire
    pm-zfs-backup.py --status      # ce qui existe, par dataset et par seau
    pm-zfs-backup.py --check       # sort 1 si la sauvegarde a décroché
    pm-zfs-backup.py --run         # force une prise dans tous les seaux dus
    pm-zfs-backup.py --dry-run --verbose
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig                              # noqa: E402

PREFIX = "pm-auto"
# `pm-auto-<seau>-<AAAAMMJJTHHMM>` — un préfixe à nous, pour que la purge ne
# puisse pas mordre sur un snapshot posé à la main (pré-MEP, migration…).
SNAP_RE = re.compile(rf"^{PREFIX}-(?P<bucket>[a-z]+)-(?P<stamp>\d{{8}}T\d{{4}})$")
# Le guichet sudo n'est autorisé QUE sur son chemin de runtime : la règle
# sudoers vise un chemin absolu. Exécuté depuis un worktree de session, ce
# script doit donc viser le runtime, pas son voisin de branche — sinon sudo
# refuse, et on croit à un problème de droits (leçon RM2997, même piège).
WRAPPER = Path(os.environ.get("PM_ZFS_SNAP")
               or "/zfs/workspaces/.mmi-pm-core/scripts/pm-zfs-snap.sh")


# >>> due_buckets — pure (testée par test_pm_zfs_backup.py)
def due_buckets(existants, buckets, now):
    """Seaux à prendre maintenant : {seau: True} si le plus récent a vieilli.

    `existants` : {seau: epoch du plus récent} (absent = jamais pris).
    Un seau jamais pris est TOUJOURS dû — sur une machine qui démarre, la
    première prise ne doit pas attendre un tour de cadran."""
    dus = []
    for nom, conf in (buckets or {}).items():
        periode = float(conf.get("every_minutes") or 0) * 60
        dernier = existants.get(nom)
        if dernier is None or (now - dernier) >= periode:
            dus.append(nom)
    return dus
# <<< due_buckets


# >>> to_prune — pure (testée par test_pm_zfs_backup.py)
def to_prune(noms, buckets):
    """Snapshots à détruire : au-delà du nombre gardé, les plus anciens.

    Deux gardes tiennent la purge :
      * seuls les noms qui portent NOTRE préfixe sont candidats — un snapshot
        posé à la main (pré-MEP, migration) n'est jamais un déchet à ramasser ;
      * un seau inconnu de la politique n'est pas purgé. Retirer un seau de la
        config ne doit pas déclencher, au tick suivant, la destruction
        silencieuse de tout son historique."""
    par_seau = {}
    for n in noms or []:
        m = SNAP_RE.match(n)
        if not m:
            continue
        par_seau.setdefault(m.group("bucket"), []).append(n)
    sortie = []
    for seau, liste in par_seau.items():
        conf = (buckets or {}).get(seau)
        if not conf:
            continue
        keep = int(conf.get("keep") or 0)
        if keep <= 0:
            continue
        liste.sort()                      # l'horodatage trie chronologiquement
        sortie.extend(liste[:-keep] if len(liste) > keep else [])
    return sorted(sortie)
# <<< to_prune


# >>> stale — pure (testée par test_pm_zfs_backup.py)
def stale(stamp, now, stale_hours):
    """(en_retard, message) d'après l'empreinte du dernier passage.

    Distingue trois situations, qui n'appellent pas la même réaction : jamais
    passé (rien n'est installé), passé il y a trop longtemps (ça a décroché),
    passé récemment mais en erreur (ça tourne et ça échoue)."""
    if not stamp:
        return True, "aucune sauvegarde ZFS n'a jamais tourné"
    at = stamp.get("at") or 0
    age_h = (now - at) / 3600.0
    if age_h > stale_hours:
        return True, f"dernière sauvegarde il y a {age_h:.0f} h (seuil {stale_hours} h)"
    erreurs = stamp.get("errors") or []
    if erreurs:
        return True, f"dernier passage il y a {age_h:.0f} h, mais {len(erreurs)} erreur(s) : " \
                     + "; ".join(str(e)[:80] for e in erreurs[:2])
    n = sum(len(v) for v in (stamp.get("datasets") or {}).values())
    return False, f"sauvegardé il y a {age_h:.0f} h · {n} seau(x) à jour"
# <<< stale


def zfs_dispo():
    """`zfs` n'existe que sur l'hôte. Dans le conteneur, le tick est un no-op
    silencieux : le greffer sur un process partagé ne doit pas le faire crier
    là où il n'a rien à faire."""
    return shutil.which("zfs") is not None or Path("/usr/sbin/zfs").exists()


def _run(cmd, timeout=120):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def snapshots(dataset):
    """[(nom_court, epoch)] des snapshots pm-auto d'un dataset (récursif)."""
    p = _run(["zfs", "list", "-t", "snapshot", "-o", "name,creation", "-p",
              "-H", "-r", dataset])
    out = []
    for ligne in (p.stdout or "").splitlines():
        bouts = ligne.split("\t")
        if len(bouts) < 2 or "@" not in bouts[0]:
            continue
        ds, _, nom = bouts[0].partition("@")
        if ds != dataset or not SNAP_RE.match(nom):
            continue
        try:
            out.append((nom, int(bouts[1])))
        except ValueError:
            continue
    return out


def creer(dataset, nom, dry, verbose):
    if dry:
        print(f"  (dry-run) créerait {dataset}@{nom}")
        return True, None
    p = _run(["sudo", "-n", str(WRAPPER), "create", dataset, nom])
    if p.returncode != 0:
        return False, (p.stderr or p.stdout or "échec").strip()[:200]
    if verbose:
        print(f"  ✓ {dataset}@{nom}")
    return True, None


def detruire(dataset, nom, dry, verbose):
    if not SNAP_RE.match(nom):        # ceinture : la purge ne sort jamais du nôtre
        return False, f"refus de détruire un nom hors politique : {nom}"
    if dry:
        print(f"  (dry-run) détruirait {dataset}@{nom}")
        return True, None
    p = _run(["sudo", "-n", str(WRAPPER), "destroy", dataset, nom])
    if p.returncode != 0:
        return False, (p.stderr or p.stdout or "échec").strip()[:200]
    if verbose:
        print(f"  ⌫ {dataset}@{nom}")
    return True, None


def politique(cfg, only=None):
    """(datasets, seaux, seuil d'alerte) depuis `zfs_backup:` de pm.config.yml.

    Config et non constantes : le périmètre d'une machine n'est pas celui d'une
    autre, et retirer un dataset doit se faire en une ligne, pas dans le code."""
    z = getattr(cfg, "zfs_backup", None) or {}
    datasets = z.get("datasets") or []
    if only:
        datasets = [d for d in datasets if d in only] or list(only)
    return (datasets, z.get("buckets") or {}, float(z.get("stale_hours") or 26))


def lire_stamp(cfg):
    try:
        return json.loads(cfg.path("zfs_backup_stamp").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def ecrire_stamp(cfg, data):
    try:
        p = cfg.path("zfs_backup_stamp")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except (OSError, KeyError) as e:
        print(f"⚠ empreinte non écrite : {e}", file=sys.stderr)


def passer(cfg, args):
    datasets, buckets, _ = politique(cfg, args.only)
    now = time.time()
    resume, erreurs = {}, []
    for ds in datasets:
        snaps = snapshots(ds)
        recents = {}
        for nom, epoch in snaps:
            m = SNAP_RE.match(nom)
            b = m.group("bucket")
            recents[b] = max(recents.get(b, 0), epoch)
        for seau in due_buckets(recents, buckets, now):
            nom = f"{PREFIX}-{seau}-{datetime.fromtimestamp(now):%Y%m%dT%H%M}"
            ok, err = creer(ds, nom, args.dry_run, args.verbose)
            if not ok:
                erreurs.append(f"{ds}@{nom} : {err}")
        # purge APRÈS la prise : le nouveau snapshot compte dans le quota, sinon
        # on garderait toujours un cran de plus que demandé.
        noms = [n for n, _ in snapshots(ds)] if not args.dry_run else [n for n, _ in snaps]
        for nom in to_prune(noms, buckets):
            ok, err = detruire(ds, nom, args.dry_run, args.verbose)
            if not ok:
                erreurs.append(f"{ds}@{nom} : {err}")
        finaux = {}
        for nom, epoch in (snapshots(ds) if not args.dry_run else snaps):
            b = SNAP_RE.match(nom).group("bucket")
            finaux.setdefault(b, []).append(epoch)
        resume[ds] = {b: {"n": len(v), "last": max(v)} for b, v in finaux.items()}
    # Une passe restreinte (`--only`, pour un essai ou une reprise ciblée) ne
    # doit PAS faire croire que tout le périmètre est à jour : elle n'écrit pas
    # l'empreinte, donc le contrôle continue de dire la vérité.
    if not args.dry_run and not args.only:
        ecrire_stamp(cfg, {"at": int(now), "datasets": resume, "errors": erreurs})
    return resume, erreurs


def cmd_status(cfg, args):
    datasets, buckets, stale_h = politique(cfg, args.only)
    st = lire_stamp(cfg)
    retard, msg = stale(st, time.time(), stale_h)
    print(("✗ " if retard else "✓ ") + msg)
    if not zfs_dispo():
        print("  (zfs absent ici — état lu depuis l'empreinte ; le tick tourne sur l'hôte)")
        for ds, seaux in ((st or {}).get("datasets") or {}).items():
            print(f"  {ds:18} " + "  ".join(
                f"{b}:{v['n']}" for b, v in sorted(seaux.items())))
        return 1 if retard else 0
    for ds in datasets:
        snaps = snapshots(ds)
        par = {}
        for nom, epoch in snaps:
            par.setdefault(SNAP_RE.match(nom).group("bucket"), []).append(epoch)
        detail = "  ".join(
            f"{b}:{len(par.get(b, []))}/{buckets[b].get('keep')}" for b in buckets)
        dernier = max((e for v in par.values() for e in v), default=None)
        quand = datetime.fromtimestamp(dernier).strftime("%Y-%m-%d %H:%M") if dernier else "jamais"
        print(f"  {ds:18} {detail}   dernier : {quand}")
    return 1 if retard else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--tick", action="store_true",
                   help="Greffé sur un process existant : prend ce qui est dû, "
                        "purge, et se tait s'il n'y a rien à dire.")
    g.add_argument("--run", action="store_true", help="Comme --tick, mais bavard.")
    g.add_argument("--status", action="store_true")
    g.add_argument("--check", action="store_true",
                   help="Sort 1 si la sauvegarde a décroché (pour un contrôle "
                        "d'environnement).")
    ap.add_argument("--only", action="append", metavar="DATASET",
                    help="Restreindre à ce(s) dataset(s) — essai ou reprise ciblée. "
                         "N'écrit pas l'empreinte : une passe partielle ne doit pas "
                         "faire croire que tout est à jour.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    cfg = PMConfig.load()

    if args.check:
        _, _, stale_h = politique(cfg, None)
        retard, msg = stale(lire_stamp(cfg), time.time(), stale_h)
        print(("✗ " if retard else "") + msg)
        return 1 if retard else 0
    if args.status:
        return cmd_status(cfg, args)
    if not (args.tick or args.run):
        return cmd_status(cfg, args)
    if not zfs_dispo():
        if args.run or args.verbose:
            print("zfs absent : rien à faire ici (le tick tourne sur l'hôte)")
        return 0
    args.verbose = args.verbose or args.run
    resume, erreurs = passer(cfg, args)
    if args.run or args.verbose:
        for ds, seaux in resume.items():
            print(f"  {ds:18} " + "  ".join(f"{b}:{v['n']}" for b, v in sorted(seaux.items())))
    for e in erreurs:
        print(f"✗ {e}", file=sys.stderr)
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
