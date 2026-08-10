#!/usr/bin/env python3
"""pm-env-gc — GC des worktrees & branches locales des tickets fermés (RM2566).

Le teardown par ticket (à la clôture) est événementiel et parfois raté ; rien ne
nettoie périodiquement. Les worktrees `envs/<repo>-rm<id>[-s<seq>]` s'accumulent
(90+ constatés). Cet outil fait le ménage, en SÉLECTIF et en SÛR.

Retire un worktree si, ET SEULEMENT SI, les trois gardes passent :
  1. son ticket est `ferme` (statut du frontmatter) ;
  2. il est PROPRE (aucune modif non commitée) ;
  3. il est INTÉGRÉ : HEAD est ancêtre de `origin/main` ou `origin/dev` (donc
     aucun commit local non mergé / non poussé à perdre).
Puis supprime sa branche locale en **merge-safe** (`git branch -d`, jamais `-D`).
Un worktree sale ou non intégré est SAUTÉ (garde de non-perte). Les worktrees
d'intégration (branche `dev`/`main`/… = pas d'id de ticket) et le bare sont
ignorés.

Dry-run par DÉFAUT (liste ce qui serait retiré) ; `--apply` exécute.

Usage :
    pm-env-gc.py                       # dry-run depuis le workspace courant
    pm-env-gc.py --fetch               # rafraîchit origin/* d'abord
    pm-env-gc.py --apply               # exécute le nettoyage
    mmi-pm env gc [--apply]            # via la façade CLI
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

TICKET_RE = re.compile(r"^(\d+)-")
FM_STATUS_RE = re.compile(r"^status:\s*(\S+)", re.MULTILINE)


def git(args, cwd=None, check=False):
    r = subprocess.run(["git", *(["-C", str(cwd)] if cwd else []), *args],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} a échoué : {r.stderr.strip()}")
    return r


def find_workspace(start: Path) -> Path:
    """Racine du workspace = 1er ancêtre avec `.mmi-pm/` ET `repos/` (layout RM1993)."""
    for d in [start, *start.parents]:
        if (d / ".mmi-pm").exists() and (d / "repos").is_dir():
            return d
    sys.exit(f"aucun workspace (repos/ + .mmi-pm) en remontant depuis {start}")


def ticket_status(cfg: PMConfig, rm_id: int):
    tf = cfg.find_task(rm_id)
    if not tf:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---", tf.read_text(encoding="utf-8"), re.DOTALL)
    if not m:
        return None
    sm = FM_STATUS_RE.search(m.group(1))
    return sm.group(1) if sm else None


def integrated(bare: Path, head: str):
    """(True, ref) si `head` est ancêtre d'une branche d'intégration connue."""
    for ref in ("origin/main", "origin/dev", "main", "dev", "origin/master", "master"):
        if git(["rev-parse", "--verify", "-q", ref + "^{commit}"], cwd=bare).returncode != 0:
            continue
        if git(["merge-base", "--is-ancestor", head, ref], cwd=bare).returncode == 0:
            return True, ref
    return False, None


def worktree_entries(bare: Path):
    """Parse `git worktree list --porcelain` → [{path, branch?, bare?, detached?}]."""
    out = git(["worktree", "list", "--porcelain"], cwd=bare).stdout
    entries, cur = [], {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                entries.append(cur)
            cur = {"path": line.split(" ", 1)[1]}
        elif line == "bare":
            cur["bare"] = True
        elif line == "detached":
            cur["detached"] = True
        elif line.startswith("branch "):
            cur["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
    if cur:
        entries.append(cur)
    return entries


def gc_worktrees(cfg, bare: Path, apply: bool, verbose: bool):
    removed, kept, skipped, freed_branches = 0, 0, 0, []
    for e in worktree_entries(bare):
        p = Path(e["path"])
        if e.get("bare") or p.resolve() == bare.resolve():
            continue
        branch = e.get("branch", "")
        m = TICKET_RE.match(branch)
        if not m:
            if verbose:
                lbl = branch or ("(HEAD détachée)" if e.get("detached") else "(?)")
                print(f"  · {p.name} — {lbl} : pas un worktree de ticket → gardé")
            kept += 1
            continue
        rm_id = int(m.group(1))
        if git(["status", "--porcelain"], cwd=p).stdout.strip():
            print(f"  ⚠ {p.name} (RM{rm_id}) — modifs non commitées → SAUTÉ")
            skipped += 1
            continue
        status = ticket_status(cfg, rm_id)
        if status != "ferme":
            if verbose:
                print(f"  · {p.name} (RM{rm_id}) — statut « {status} » → gardé")
            kept += 1
            continue
        head = git(["rev-parse", "HEAD"], cwd=p).stdout.strip()
        ok, ref = integrated(bare, head)
        if not ok:
            print(f"  ⚠ {p.name} (RM{rm_id}) — commits non intégrés (non mergés) → SAUTÉ")
            skipped += 1
            continue
        print(f"  {'✓ retiré ' if apply else '→ à retirer'} : {p.name} "
              f"(RM{rm_id} ferme, intégré dans {ref})")
        removed += 1
        if apply:
            r = git(["worktree", "remove", str(p)], cwd=bare)
            if r.returncode != 0:
                print(f"      ✗ échec worktree remove : {r.stderr.strip()}")
                removed -= 1
                skipped += 1
                continue
        freed_branches.append(branch)
    return removed, kept, skipped, freed_branches


def gc_branches(cfg, bare: Path, apply: bool, skip: set, verbose: bool):
    """Supprime les branches locales des tickets fermés, en merge-safe (`-d`).
    `skip` = branches encore rattachées à un worktree (traitées ailleurs)."""
    out = git(["for-each-ref", "--format=%(refname:short)", "refs/heads/"], cwd=bare).stdout
    pruned = 0
    for br in out.split():
        if br in skip:
            continue
        m = TICKET_RE.match(br)
        if not m:
            continue
        if ticket_status(cfg, int(m.group(1))) != "ferme":
            continue
        if apply:
            r = git(["branch", "-d", br], cwd=bare)  # -d : refuse si non mergée
            if r.returncode != 0:
                if verbose:
                    print(f"  · branche {br} non supprimée (non mergée ?) — gardée")
                continue
            print(f"  ✓ branche locale supprimée : {br}")
        else:
            # dry-run : ne supprime pas, mais teste la même sûreté que `-d` (mergée ?)
            base_ok = any(git(["merge-base", "--is-ancestor", br, ref], cwd=bare).returncode == 0
                          for ref in ("origin/main", "main", "origin/dev", "dev")
                          if git(["rev-parse", "--verify", "-q", ref + "^{commit}"], cwd=bare).returncode == 0)
            if base_ok:
                print(f"  → branche locale à supprimer : {br}")
            elif verbose:
                print(f"  · branche {br} (RM{m.group(1)} ferme) mais non mergée → gardée")
                continue
            else:
                continue
        pruned += 1
    return pruned


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="exécute le nettoyage (défaut : dry-run)")
    ap.add_argument("--workspace", help="racine du workspace (défaut : remontée depuis cwd)")
    ap.add_argument("--fetch", action="store_true",
                    help="git fetch --all avant (rafraîchit origin/* pour le test d'intégration)")
    ap.add_argument("--verbose", action="store_true", help="détaille aussi ce qui est gardé")
    args = ap.parse_args()

    ws = find_workspace(Path(args.workspace).resolve() if args.workspace else Path.cwd())
    cfg = PMConfig.load()
    bares = sorted((ws / "repos").glob("*.git"))
    if not bares:
        sys.exit(f"aucun bare repos/*.git sous {ws}")

    print(f"workspace : {ws}\nmode      : {'APPLY' if args.apply else 'dry-run (aucune suppression)'}\n")
    tot_r = tot_k = tot_s = tot_b = 0
    for bare in bares:
        print(f"── {bare.name} ──")
        if args.fetch:
            git(["fetch", "--all", "-q"], cwd=bare)
        r, k, s, freed = gc_worktrees(cfg, bare, args.apply, args.verbose)
        b = gc_branches(cfg, bare, args.apply, set(freed), args.verbose)
        tot_r, tot_k, tot_s, tot_b = tot_r + r, tot_k + k, tot_s + s, tot_b + b

    verb = "retirés" if args.apply else "à retirer"
    print(f"\n{tot_r} worktree(s) {verb} · {tot_b} branche(s) locale(s) {'supprimée(s)' if args.apply else 'à supprimer'} "
          f"· {tot_k} gardé(s) · {tot_s} sauté(s) (sale/non intégré)")
    if not args.apply and (tot_r or tot_b):
        print("→ relancer avec --apply pour exécuter.")


if __name__ == "__main__":
    main()
