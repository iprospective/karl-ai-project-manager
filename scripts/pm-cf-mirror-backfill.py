#!/usr/bin/env python3
"""pm-cf-mirror-backfill — reprise de l'existant des miroirs « frontmatter ↔ CF » (RM2563).

Trois champs de tâche sont désormais des miroirs d'un CF Redmine :

| frontmatter      | CF | poussé à l'écriture par     |
|------------------|----|-----------------------------|
| `test_protocol`  | 30 | `pm-task-protocol`          |
| `implementation` | 31 | `pm-task-implementation`    |
| `deploy_actions` | 8  | `pm-task-deploy`            |

Le câblage est neuf : avant lui, `deploy_actions` n'était **jamais** poussé (le champ
existait, le CF existait, rien ne les reliait) et l'esquisse d'implémentation vivait en
section `## Implémentation` du corps. Il reste donc de l'existant des deux côtés, qu'il
faut réconcilier **sans rien perdre**.

RÈGLE CARDINALE — on ne remplace **jamais** du contenu par du vide, dans aucun des deux
sens, et on ne tranche **jamais** un désaccord tout seul :

    local vide   & distant plein  → PULL   (Redmine → frontmatter)
    local plein  & distant vide   → PUSH   (frontmatter → Redmine)
    les deux vides                → rien
    les deux pleins & identiques  → rien (déjà synchrone)
    les deux pleins & DIFFÉRENTS  → CONFLIT : signalé, rien n'est touché

Les conflits sont listés avec les deux versions ; c'est un humain qui tranche, puis
rejoue le sens choisi avec l'outil dédié (`pm-task-deploy --set` / `--pull`, etc.).

Cas particulier `implementation` : si le frontmatter est vide mais que le CORPS du MD
porte une section `## Implémentation` (forme d'avant le CF 31), `--adopt-sections` la
reprend comme source du PUSH. Le corps n'est **pas** modifié — rien n'est effacé ; la
section devient simplement redondante et pourra être retirée à la main, ticket par
ticket, une fois la reprise vérifiée.

Usage :
    pm-cf-mirror-backfill.py                      # DRY-RUN sur tous les tickets (défaut)
    pm-cf-mirror-backfill.py --field deploy_actions
    pm-cf-mirror-backfill.py --rm-id 2560 --adopt-sections
    pm-cf-mirror-backfill.py --go                 # exécute
    pm-cf-mirror-backfill.py --go --pull-only     # ne remonte rien vers Redmine

Sans `--go`, **aucune écriture** : ni fichier, ni API, ni commit.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_cf_mirror
import pm_git

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)

# (clé frontmatter, variable .env, nom du CF, liste ?)
MIRRORS = {
    "implementation": ("REDMINE_CF_IMPLEMENTATION_ID", "Proposition d'implémentation", False),
    "test_protocol":  ("REDMINE_CF_TEST_PROTOCOL_ID",  "Protocole de test",            False),
    "deploy_actions": ("REDMINE_CF_DEPLOY_ACTIONS_ID", "Actions au déploiement",       True),
}


def norm(value, is_list):
    """Valeur comparable : liste normalisée, ou texte strippé. Vide → None."""
    if is_list:
        items = list(value or []) if not isinstance(value, str) \
            else pm_cf_mirror.text_to_list(value)
        return items or None
    return pm_cf_mirror.normalize_text(value) or None


section_of = pm_cf_mirror.extract_implementation_section


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rm-id", type=int, help="Limiter à un ticket")
    ap.add_argument("--field", choices=sorted(MIRRORS), action="append",
                    help="Limiter à ce(s) champ(s) (défaut : les trois)")
    ap.add_argument("--adopt-sections", action="store_true",
                    help="Pour `implementation` : adopter la section `## Implémentation` "
                         "du corps quand le frontmatter est vide (le corps est conservé)")
    ap.add_argument("--pull-only", action="store_true", help="N'effectuer que les PULL")
    ap.add_argument("--push-only", action="store_true", help="N'effectuer que les PUSH")
    ap.add_argument("--go", action="store_true", help="Exécute (défaut : dry-run)")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git")
    args = ap.parse_args()
    if args.pull_only and args.push_only:
        sys.exit("ERREUR : --pull-only et --push-only sont exclusifs")
    fields = args.field or sorted(MIRRORS)

    cfg = PMConfig.load()
    if args.rm_id:
        p = cfg.find_task(args.rm_id)
        if not p:
            sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
        paths = [p]
    else:
        paths = []
        for ent, proj, _ in cfg.iter_projects():
            d = cfg.path("tasks_dir", entity=ent, project=proj)
            if d.is_dir():
                paths += [f for f in sorted(d.glob("RM*.md"))
                          if not f.name.endswith(".log.md")]

    # Pré-chargement en masse : un GET par ticket ferait ~1200 appels pour un
    # balayage complet. La liste paginée renvoie déjà les custom_fields.
    import redmine_utils
    issues = {}
    if args.rm_id:
        try:
            issues[args.rm_id] = redmine_utils.fetch_issue(args.rm_id) or {}
        except Exception:  # noqa: BLE001
            issues[args.rm_id] = {}
    else:
        creds = redmine_utils.redmine_creds()
        base, key = creds[0].rstrip("/"), creds[1]
        off, total = 0, None
        while total is None or off < total:
            # ~30 pages : un hoquet réseau sur une seule ne doit pas perdre le balayage.
            for attempt in range(3):
                try:
                    st, d = redmine_utils.http_json(
                        "GET", f"{base}/issues.json?status_id=*&limit=100&offset={off}",
                        key, basic=creds.basic)
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        sys.exit(f"ERREUR : lecture Redmine impossible à l'offset {off} "
                                 f"après 3 essais ({e}). Rien n'a été écrit.")
                    print(f"  ⚠ offset {off} : {e} — nouvel essai", file=sys.stderr)
            total = d.get("total_count", 0)
            for i in d.get("issues", []):
                issues[i["id"]] = i
            off += 100
        print(f"({len(issues)} ticket(s) Redmine chargés)")

    stats = {"pull": 0, "push": 0, "conflit": 0, "sync": 0, "vide": 0, "adopt": 0}
    conflicts, actions = [], []

    for path in paths:
        try:
            m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            fm = yaml.safe_load(m.group(2)) or {}
        except Exception:  # noqa: BLE001 — fiche illisible : on la saute, on ne casse rien
            continue
        rm_id = fm.get("redmine_id")
        if not isinstance(rm_id, int):
            continue
        issue = None
        for key in fields:
            env_var, cf_name, is_list = MIRRORS[key]
            local = norm(fm.get(key), is_list)
            source = "frontmatter"
            if key == "implementation" and local is None and args.adopt_sections:
                sect = section_of(m.group(4))
                if sect:
                    local, source = norm(sect, is_list), "section du corps"
                    stats["adopt"] += 1
            if issue is None:
                issue = issues.get(rm_id) or {}
            cid = pm_cf_mirror.resolve_cf_id(env_var, cf_name)
            if cid is None:
                continue
            raw = next((c.get("value") for c in issue.get("custom_fields", [])
                        if c.get("id") == cid), None)
            remote = norm(raw, is_list)

            if local is None and remote is None:
                stats["vide"] += 1
            elif local == remote:
                stats["sync"] += 1
            elif local is None:                        # ← Redmine seul : PULL
                stats["pull"] += 1
                actions.append(("pull", rm_id, key, path, remote, source))
            elif remote is None:                       # ← PM seul : PUSH
                stats["push"] += 1
                actions.append(("push", rm_id, key, path, local, source))
            else:                                      # ← les deux, différents
                stats["conflit"] += 1
                conflicts.append((rm_id, key, local, remote))

    # ── Rapport ──────────────────────────────────────────────────────────────
    print(f"{len(paths)} fiche(s) · champs : {', '.join(fields)}")
    print(f"  déjà synchrones : {stats['sync']}   · vides des deux côtés : {stats['vide']}")
    print(f"  à REMONTER (PM → Redmine) : {stats['push']}"
          f"   · à RAPATRIER (Redmine → PM) : {stats['pull']}")
    if args.adopt_sections:
        print(f"  sections `## Implémentation` adoptées comme source : {stats['adopt']}")
    if conflicts:
        print(f"\n⚠ {len(conflicts)} CONFLIT(S) — les deux côtés portent du contenu "
              f"DIFFÉRENT. Rien n'est touché ; à trancher à la main :")
        for rm_id, key, local, remote in conflicts:
            print(f"  RM{rm_id} · {key}")
            print(f"      local  : {str(local)[:160]}")
            print(f"      Redmine: {str(remote)[:160]}")

    todo = [a for a in actions
            if not (args.pull_only and a[0] == "push")
            and not (args.push_only and a[0] == "pull")]
    if not todo:
        print("\n(rien à faire)")
        return
    print()
    for kind, rm_id, key, path, value, source in todo:
        arrow = "→ Redmine" if kind == "push" else "→ frontmatter"
        preview = " ⏎ ".join(str(value).splitlines() if not isinstance(value, list)
                             else value)[:110]
        print(f"  {kind.upper():5s} RM{rm_id:<5} {key:<15} {arrow:<14} "
              f"[{source}] {preview}")

    if not args.go:
        print(f"\n(dry-run : {len(todo)} opération(s) — relancer avec --go pour exécuter)")
        return

    # ── Exécution ────────────────────────────────────────────────────────────
    touched = []
    for kind, rm_id, key, path, value, source in todo:
        env_var, cf_name, is_list = MIRRORS[key]
        if kind == "push":
            text = pm_cf_mirror.list_to_text(value) if is_list else value
            ok = pm_cf_mirror.push_text_cf(rm_id, text, env_var=env_var, cf_name=cf_name)
            print(f"  {'✓' if ok else '✗'} push RM{rm_id} {key}")
            if ok and source != "frontmatter":
                # La section du corps devient la valeur du champ : on l'y inscrit aussi,
                # sinon le miroir local resterait vide et un pull futur le croirait absent.
                m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
                fm = yaml.safe_load(m.group(2)) or {}
                fm[key] = value
                fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
                new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                                        default_flow_style=False)
                path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}",
                                encoding="utf-8")
                touched.append(path)
        else:
            m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            fm = yaml.safe_load(m.group(2)) or {}
            fm[key] = value
            fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
            new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                                    default_flow_style=False)
            path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}",
                            encoding="utf-8")
            touched.append(path)
            print(f"  ✓ pull RM{rm_id} {key}")

    # Commit PAR DÉPÔT : un backfill global touche des fiches réparties sur plusieurs
    # dépôts de données (un par workspace projet). `pm_git.autocommit` déduit le dépôt
    # du PREMIER chemin et ignore tout ce qui tombe ailleurs — les autres fiches
    # resteraient non committées, en silence. On regroupe donc avant d'appeler.
    if touched and not args.no_commit:
        import subprocess
        by_repo = {}
        for f in sorted(set(touched)):
            r = subprocess.run(["git", "-C", str(Path(f).parent),
                                "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True)
            root = r.stdout.strip()
            if not root:
                print(f"  ⚠ {f} hors dépôt git — à committer à la main", file=sys.stderr)
                continue
            by_repo.setdefault(root, []).append(f)
        for root, files in by_repo.items():
            sha = pm_git.autocommit(
                files,
                f"pm(cf-mirror): reprise de {len(files)} miroir(s) frontmatter↔CF (RM2563)")
            print(f"  ✓ commit {root} ({len(files)} fiche(s)){' ' + sha if sha else ''}")


if __name__ == "__main__":
    main()
