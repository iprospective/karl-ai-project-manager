#!/usr/bin/env python3
"""pm-snapshot — point de restauration ZFS pré-MEP, pris sur le bon hyperviseur, depuis le ticket (RM2989).

Le tripwire #10 impose, avant toute MEP sur une cible opensvc / LXC / ZFS, un snapshot
pris depuis l'hyperviseur qui porte le conteneur (`om <svc> sync update --rid
sync#root_hour`), et son nom journalisé avec la commande de rollback. Jusqu'ici l'agent
devait deviner le service, interroger srv3/4/5, réécrire la commande et relever le nom
à la main (RM2988).

Trois partis pris :

  1. **PM ne touche aucun hôte.** Tout passe par atlas, seul détenteur de l'accès
     hyperviseur (frontière D3, RM2421) : canal orchestrateur SSH forced-command
     (RM2516) → ops `svc-status` (P0) et `svc-snapshot` (P1) du catalogue (RM3254).
  2. **Cible déclarée, jamais devinée.** Le service opensvc vient d'un champ
     `snapshot: {svc: <nom>, rid: <rid>}` posé sur l'env de `environments.md`
     (`target_env` du ticket, sinon `prod`) ou, pour un projet dont la prod EST le
     conteneur, dans `meta.yml`. Absent ⇒ erreur qui dit quoi poser — pas de
     rapprochement par nom de client.
  3. **Nœud constaté, jamais supposé.** Chaque nœud candidat est interrogé ; il faut
     exactement UNE instance `up`. Zéro ou plusieurs ⇒ refus, rien n'est exécuté.

Usage :
    pm-snapshot 2988 --dry-run      # nœud constaté + commande exacte, rien d'exécuté
    pm-snapshot 2988                # snapshot + entrée journal + note Redmine (rollback)
    pm-snapshot --svc calyclay --dry-run
    pm-snapshot 2988 --porcelain    # « <nœud> <snapshot> » par ligne, pour capture

Config (`pm.config.yml :: snapshot`) : `nodes` (candidats), `rid` (défaut),
`atlas_orch_host`, `atlas_orch_key` ; surcharges ATLAS_ORCH_HOST / ATLAS_ORCH_KEY.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402

RIDS = ("sync#root_hour", "sync#root_day", "sync#root_week")
DEFAULT_RID = "sync#root_hour"
DEFAULT_NODES = ("srv3", "srv4", "srv5")
RE_SVC = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")    # = RE_CONTAINER côté atlas


class SnapError(Exception):
    """Refus explicite : rien n'a été exécuté."""


# ── Résolution de la cible (pur) ─────────────────────────────────────────

def frontmatter(text):
    """Frontmatter YAML d'un fichier MD (`---` … `---`), {} si absent."""
    if not text.startswith("---"):
        return {}
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return {}
    try:
        return yaml.safe_load(parts[0][3:]) or {}
    except yaml.YAMLError:
        return {}


def pick_env(envs, target_env):
    """Env visé : `target_env` du ticket s'il est posé, sinon `prod`. None si introuvable.

    Un `target_env` posé mais absent de la liste est une incohérence : on ne retombe
    PAS sur prod (on prendrait le snapshot du mauvais environnement)."""
    by_name = {e.get("name"): e for e in envs or [] if isinstance(e, dict)}
    if target_env:
        return by_name.get(target_env)
    return by_name.get("prod")


def snapshot_target(env, meta, rid_default=DEFAULT_RID):
    """(svc, rid, source) depuis `env.snapshot` puis `meta.snapshot` ; None sinon."""
    for source, holder in (("environments.md", env or {}), ("meta.yml", meta or {})):
        snap = holder.get("snapshot") if isinstance(holder, dict) else None
        if isinstance(snap, dict) and snap.get("svc"):
            return str(snap["svc"]), str(snap.get("rid") or rid_default), source
    return None


def validate(svc, rid):
    if not RE_SVC.match(svc or ""):
        raise SnapError(f"nom de service opensvc invalide : {svc!r}")
    if rid not in RIDS:
        raise SnapError(f"rid {rid!r} hors liste ({', '.join(RIDS)})")


def locate(statuses):
    """Nœud portant l'instance `up`, parmi {nœud: avail|erreur}. Exactement un, sinon refus."""
    up = sorted(n for n, a in statuses.items() if a == "up")
    if len(up) == 1:
        return up[0]
    vu = ", ".join(f"{n}={a}" for n, a in sorted(statuses.items()))
    if not up and statuses and all(str(a).startswith("erreur") for a in statuses.values()):
        raise SnapError(f"atlas n'a pu interroger aucun nœud ({vu}) — rien exécuté. "
                        "Ops svc-status/svc-snapshot déployées côté atlas (RM3254) ?")
    if not up:
        raise SnapError(f"aucune instance up ({vu}) — rien exécuté")
    raise SnapError(f"plusieurs instances up ({vu}) — cible ambiguë, rien exécuté")


def om_command(svc, rid):
    return f"om {svc} sync update --rid {rid}"


def rollback_command(node, svc, snap):
    return (f"ssh root@{node} 'om {svc} stop && zfs rollback -r {snap} && om {svc} start'"
            "   # -r détruit les snapshots plus récents que celui-ci")


def journal_note(node, svc, rid, snaps):
    lignes = [f"Point de restauration pré-MEP pris par pm-snapshot (via atlas) sur {node} :"]
    lignes += [f"- `{s}`" for s in snaps]
    lignes += ["", f"Commande exécutée : `{om_command(svc, rid)}` (op atlas svc-snapshot).",
               "Rollback du conteneur complet :"]
    lignes += [f"    {rollback_command(node, svc, s)}" for s in snaps]
    if rid == "sync#root_hour":
        lignes += ["", "Rétention courte (ressource horaire, ~8 h) : filet pour la fenêtre "
                       "d'intervention, pas une sauvegarde."]
    return "\n".join(lignes)


# ── Canal atlas ──────────────────────────────────────────────────────────

def atlas_payload(argv):
    return base64.b64encode(json.dumps(argv).encode()).decode()


def parse_atlas(raw):
    """Réponse JSON du cœur → (ok, charge utile de l'op | message d'erreur)."""
    try:
        resp = json.loads(raw)
    except (ValueError, TypeError):
        return False, f"réponse atlas illisible : {str(raw)[:200]!r}"
    if not isinstance(resp, dict):
        return False, "réponse atlas inattendue"
    if not resp.get("ok"):
        err = resp.get("error") or (resp.get("stderr") or "").strip() or f"exit {resp.get('exit')}"
        return False, err
    lignes = [ln for ln in (resp.get("stdout") or "").splitlines() if ln.strip()]
    try:
        return True, json.loads(lignes[-1]) if lignes else {}
    except ValueError:
        return False, f"sortie d'op illisible : {lignes[-1][:200]!r}"


class Atlas:
    def __init__(self, host, key, runner=subprocess.run):
        self.host, self.key, self.runner = host, key, runner

    def run(self, node, op, *args, timeout=90):
        argv = ["run", "--node", node, op, *args]
        cmd = ["ssh", "-i", self.key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               "-o", "StrictHostKeyChecking=accept-new", self.host, f"atlas {atlas_payload(argv)}"]
        try:
            p = self.runner(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"atlas : délai dépassé ({timeout} s)"
        if p.returncode != 0 and not p.stdout.strip():
            return False, (p.stderr or "").strip() or f"ssh exit {p.returncode}"
        return parse_atlas(p.stdout)


def statuses_of(atlas, nodes, svc):
    out = {}
    for n in nodes:
        ok, res = atlas.run(n, "svc-status", svc, timeout=40)
        out[n] = res.get("avail", "n/a") if ok else f"erreur({res})"
    return out


# ── Orchestration ────────────────────────────────────────────────────────

def resolve_from_ticket(cfg, rm_id, rid_default):
    task = cfg.find_task(rm_id)
    if not task:
        raise SnapError(f"RM{rm_id} introuvable dans les projets PM")
    proj = task.parent.parent
    fm = frontmatter(task.read_text(encoding="utf-8"))
    env_file = proj / "project" / "environments.md"
    envs = frontmatter(env_file.read_text(encoding="utf-8")).get("environments") if env_file.exists() else []
    target_env = fm.get("target_env")
    env = pick_env(envs, target_env)
    if target_env and env is None:
        raise SnapError(f"RM{rm_id} : target_env={target_env!r} absent de {env_file} — "
                        "rien exécuté (pas de repli sur prod)")
    meta_file = proj / "meta.yml"
    meta = yaml.safe_load(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    tgt = snapshot_target(env, meta, rid_default)
    if not tgt:
        rel = proj.relative_to(cfg.projects_root) if proj.is_relative_to(cfg.projects_root) else proj
        raise SnapError(
            f"RM{rm_id} : aucune cible de snapshot déclarée pour {rel} "
            f"(env {(env or {}).get('name') or target_env or 'prod'}). Poser, sur l'env de "
            "project/environments.md ou dans meta.yml :\n"
            "    snapshot: {svc: <service opensvc>, rid: sync#root_hour}")
    return tgt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", nargs="?", type=int, help="ticket dont on protège la cible")
    ap.add_argument("--svc", help="service opensvc explicite (sans ticket, ou pour forcer)")
    ap.add_argument("--rid", help=f"ressource de snapshot ({', '.join(RIDS)})")
    ap.add_argument("--node", action="append",
                    help="nœud candidat (répétable) ; défaut : pm.config.yml :: snapshot.nodes")
    ap.add_argument("--dry-run", action="store_true",
                    help="constate le nœud et affiche la commande, n'exécute rien")
    ap.add_argument("--porcelain", action="store_true", help="« <nœud> <snapshot> » par ligne")
    ap.add_argument("--no-journal", action="store_true", help="pas d'entrée journal/Redmine")
    args = ap.parse_args(argv)

    cfg = PMConfig.load()
    conf = getattr(cfg, "snapshot", {}) or {}
    rid_default = args.rid or conf.get("rid") or DEFAULT_RID
    nodes = args.node or conf.get("nodes") or list(DEFAULT_NODES)
    atlas = Atlas(os.environ.get("ATLAS_ORCH_HOST") or conf.get("atlas_orch_host")
                  or "atlas-orch@atlas.iprospective.net",
                  os.path.expanduser(os.environ.get("ATLAS_ORCH_KEY") or conf.get("atlas_orch_key")
                                     or "~/.ssh/id_ed25519_karl"))
    try:
        if args.svc:
            svc, rid, source = args.svc, rid_default, "--svc"
        elif args.rm_id:
            svc, rid, source = resolve_from_ticket(cfg, args.rm_id, rid_default)
            if args.rid:
                rid = args.rid
        else:
            ap.error("un ticket ou --svc est requis")
        validate(svc, rid)
        log = (lambda *a: None) if args.porcelain else (lambda *a: print(*a, file=sys.stderr))
        log(f"cible : service opensvc {svc} ({source}), ressource {rid}")
        st = statuses_of(atlas, nodes, svc)
        node = locate(st)
        log(f"nœud  : {node}  (constaté : {', '.join(f'{n}={a}' for n, a in sorted(st.items()))})")
        if args.dry_run:
            print(f"{node}\t{om_command(svc, rid)}" if args.porcelain
                  else f"[dry-run] sur {node} : {om_command(svc, rid)}  — rien exécuté")
            return 0
        ok, res = atlas.run(node, "svc-snapshot", svc, rid, timeout=120)
        if not ok:
            raise SnapError(f"svc-snapshot refusé ou en échec sur {node} : {res}")
        snaps = res.get("snapshots") or []
        if not snaps:
            raise SnapError(f"atlas n'a rendu aucun nom de snapshot sur {node} — à vérifier à la main")
    except SnapError as e:
        print(f"✗ pm-snapshot : {e}", file=sys.stderr)
        return 2

    if args.porcelain:
        print("\n".join(f"{node} {s}" for s in snaps))
    else:
        print(f"✓ point de restauration sur {node} :")
        for s in snaps:
            print(f"    {s}")
            print(f"    rollback : {rollback_command(node, svc, s)}")
    if args.rm_id and not args.no_journal:
        note = journal_note(node, svc, rid, snaps)
        p = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "pm-task-comment.py"),
                            str(args.rm_id), "--note", note], capture_output=True, text=True)
        if p.returncode != 0:
            # Le snapshot EXISTE : on ne le cache pas derrière un échec de journal.
            print(f"⚠ snapshot pris mais journal/Redmine en échec : {(p.stderr or p.stdout).strip()[:300]}",
                  file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
