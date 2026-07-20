#!/usr/bin/env python3
"""pm-task-take — prise d'un ticket en UN appel (RM2364, CDC RM2316 § S3).

Compose la séquence canonique « je prends un ticket » (aujourd'hui 3–4 appels
et leurs sorties) :

  1. statut → en_cours + auto-assignation (pm-task-status-update ; hook
     env-session inclus : worktree + runtime selon le layout du workspace) ;
  2. branche <id>-<slug> + CF3 GIT Branche (pm-branch-start sur le worktree
     de session s'il existe, sinon --repo) ;
  3. brief final (pm-task-brief) — le contexte de travail en ≤ 30 lignes.

Idempotent : chaque étape est re-jouable (statut déjà en_cours → skip,
branche existante → checkout). Une seule note Redmine (celle du statut).
Gardes NORMS inchangées (auto-assignation, CF, optimistic locking — portées
par les scripts unitaires appelés, qui restent disponibles).

Usage :
    pm-task-take.py <RM-id>                 # flux complet
    pm-task-take.py <RM-id> --no-branch     # ticket sans code (pas de branche)
    pm-task-take.py <RM-id> --repo PATH     # repo cible explicite pour la branche
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def run_step(label, cmd, ok_required=True):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    detail = "\n".join(s.rstrip() for s in (r.stdout, r.stderr) if s and s.strip())
    out.info(detail)
    if r.returncode != 0:
        if ok_required:
            out.fail(f"{label} (exit {r.returncode}) :\n{detail}",
                     remede="reprendre l'étape avec le script unitaire (--verbose pour le détail)")
        out.warn(f"{label} en échec non bloquant (exit {r.returncode}) — reprendre à la main")
    return r


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--no-branch", action="store_true",
                    help="Pas de branche de ticket (tâche sans code — flux court § S8)")
    ap.add_argument("--repo", help="Repo cible pour la branche (défaut : worktree de session, sinon cwd)")
    ap.add_argument("--from", dest="base", help="Branche de base (défaut : branche d'intégration)")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    md = cfg.find_task(args.rm_id)
    if not md:
        out.fail(f"fichier RM{args.rm_id}_*.md introuvable")
    fm = yaml.safe_load(FM_RE.match(md.read_text(encoding="utf-8")).group(1)) or {}

    # 1. statut en_cours (+ auto-assign + hook env-session) — idempotent
    if fm.get("status") == "en_cours":
        out.op("statut", rm=args.rm_id, extra="déjà en_cours (skip)")
    else:
        run_step("pm-task-status-update", [str(here / "pm-task-status-update.py"),
                                           str(args.rm_id), "en_cours"])
        out.op("statut", rm=args.rm_id, extra="en_cours (auto-assign, env-session au layout)")

    # 2. branche + CF3 — idempotent (pm-branch-start re-checkout si existante)
    if not args.no_branch:
        repo = args.repo
        if not repo:
            # worktree de session envs/<repo>-rm<id> si le layout RM1993 l'a créé
            cand = None
            try:
                import pm_session
                rec = pm_session.current_record() or {}
                for w in rec.get("worktrees") or []:
                    if w.endswith(f"rm{args.rm_id}"):
                        cand = w
                        break
            except Exception:
                pass
            if not cand:
                for envs_dir in Path.cwd().glob("envs"):
                    for d in envs_dir.glob(f"*rm{args.rm_id}"):
                        cand = str(d)
            repo = cand or "."
        cmd = [str(here / "pm-branch-start.py"), str(args.rm_id), "--repo", str(repo)]
        if args.base:
            cmd += ["--from", args.base]
        run_step("pm-branch-start", cmd, ok_required=False)

    # 3. brief final — le contexte de travail
    r = subprocess.run([sys.executable, str(here / "pm-task-brief.py"), str(args.rm_id)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(r.stdout.rstrip())
    else:
        out.warn("brief indisponible : " + (r.stderr or "").strip()[:120])


if __name__ == "__main__":
    main()
