#!/usr/bin/env python3
"""pm-cf-mirror-backfill — reprise de l'existant des miroirs « frontmatter ↔ CF » (RM2563).

Trois champs de tâche sont désormais des miroirs d'un CF Redmine :

| frontmatter      | CF | poussé à l'écriture par     |
|------------------|----|-----------------------------|
| `test_protocol`  | 30 | `pm-task-protocol`          |
| `implementation` | 31 | `pm-task-implementation`    |
| `deploy_actions` | 8  | `pm-task-deploy`            |
| `acceptance`     | 33 | `pm-task-acceptance`        |

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

Cas des SECTIONS DU CORPS : si le frontmatter est vide mais que le corps du MD porte
la section d'avant le CF, `--adopt-sections` la reprend comme source du PUSH —
`## Implémentation` pour `implementation` (RM2563), `## Critères d'acceptation` pour
`acceptance` (RM2882). Le corps n'est **pas** modifié — rien n'est effacé ; la section
devient simplement redondante et pourra être retirée à la main, ticket par ticket, une
fois la reprise vérifiée.

Cas particulier `acceptance` (RM2882) : les deux côtés portent une LISTE d'items, pas
un bloc opaque. Quand ils diffèrent, on peut donc faire mieux qu'un conflit — mais
jamais un arbitrage :

    l'un est INCLUS dans l'autre     → UNION : on écrit le sur-ensemble des deux
    items exclusifs de chaque côté   → CONFLIT (divergence croisée)
    même item, coche différente      → CONFLIT (personne ne sait qui a raison)

L'audit a mesuré 18 % de tickets divergents sur les 56 porteurs de critères réels,
dans les deux sens : aucune source n'est systématiquement la bonne, d'où le refus de
trancher. S'y ajoute un verrou propre aux critères : un ticket dont des cases à cocher
traînent HORS de la section n'est pas migré automatiquement — les index de
`pm-task-description-update --check N` y désignent autre chose que le Nᵉ critère.

Avant la moindre écriture, `--go` dépose un **dump JSONL** de l'état des deux côtés
(leçon RM2409 : un script destructif par lot sauvegarde avant, pas après).

Usage :
    pm-cf-mirror-backfill.py                      # DRY-RUN sur tous les tickets (défaut)
    pm-cf-mirror-backfill.py --field deploy_actions
    pm-cf-mirror-backfill.py --rm-id 2560 --adopt-sections
    pm-cf-mirror-backfill.py --go                 # exécute
    pm-cf-mirror-backfill.py --go --pull-only     # ne remonte rien vers Redmine
    pm-cf-mirror-backfill.py --field acceptance --adopt-sections --go

Sans `--go`, **aucune écriture** : ni fichier, ni API, ni commit.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_think import is_task_sheet  # RM3053 : la fiche, jamais un frère (.log.md, .think.md)
from pm_paths import PMConfig
import pm_acceptance
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
    "acceptance":     (pm_acceptance.ENV_VAR,          pm_acceptance.CF_NAME,          False),
}

# Section du corps qui tenait lieu de champ avant le CF, par miroir (`--adopt-sections`).
SECTION_OF = {
    "implementation": pm_cf_mirror.extract_implementation_section,
    "acceptance":     pm_acceptance.adoptable_section,
}


def norm(value, is_list):
    """Valeur comparable : liste normalisée, ou texte strippé. Vide → None."""
    if is_list:
        items = list(value or []) if not isinstance(value, str) \
            else pm_cf_mirror.text_to_list(value)
        return items or None
    return pm_cf_mirror.normalize_text(value) or None


def cf_vide_vers_push(action, value, motifs, local, remote, source, remote_de_la_description):
    """RM3240 — le CF est VIDE et la valeur « Redmine » n'est que la section de la DESCRIPTION.

    `decide_acceptance` compare deux listes ; il ne sait pas que l'une est un repli. Deux sorties
    y deviennent fausses : « sync » (la section du corps = celle de la description) et « pull »
    (rien en local) concluaient que Redmine était à jour, et seul le miroir local était écrit —
    le CF 33 restait vide pour toujours (743 tickets au dry-run du 2026-09-19, dont RM1587).
    Dans ces deux cas on POUSSE vers le CF ; le miroir local suit (source ≠ frontmatter).
    Fonction PURE — (action, valeur, source, motifs)."""
    if not remote_de_la_description or action not in ("sync", "pull"):
        return action, value, source, motifs
    if local is not None:
        return "push", local, source, ["CF vide : critères repris de la section « " + source + " »"]
    return "push", remote, "description Redmine", [
        "CF vide : critères repris de la section de la description Redmine"]


def decide_acceptance(local, remote, body):
    """Que faire des critères d'un ticket ? Fonction PURE — (action, valeur, motifs).

    `action` ∈ {"sync", "push", "pull", "union", "conflit"} ; `motifs` explique un
    conflit, ou ce que l'union a ajouté. `body` sert au seul verrou des cases errantes.

    On n'écrit une union que lorsqu'une source est incluse dans l'autre : c'est alors
    un complément, pas un arbitrage. Dès qu'il y a de l'exclusif des deux côtés — ou
    la même ligne cochée d'un côté et pas de l'autre — personne ici ne sait qui a
    raison, et rien n'est touché.
    """
    errantes = pm_acceptance.stray_checkboxes(body or "")
    if local is None and remote is None:
        return "vide", None, []
    if errantes:
        # AVANT tout le reste, y compris avant « déjà synchrone » : même quand les deux
        # côtés portent exactement les mêmes critères, matérialiser le champ ferait
        # basculer la LECTURE dessus alors que `pm-task-description-update --check N`
        # continue d'écrire dans la description — où le Nᵉ item n'est pas le Nᵉ critère.
        # C'est tout le § 4.2 de l'étude : on ne bascule pas la lecture sans l'écriture.
        return "conflit", None, [
            "{} case(s) à cocher hors de la section de critères — `--check N` ne "
            "désignerait plus les mêmes lignes (§ 4.2) : migrer à la main".format(len(errantes))]

    md_items = pm_acceptance.parse_items(local or "")
    rm_items = pm_acceptance.parse_items(remote or "")
    # Comparaison sur la forme NORMALISÉE des libellés : l'outillage enveloppe à ~95
    # colonnes et Redmine ré-enveloppe à sa façon. Comparer le texte brut ferait passer
    # deux versions identiques pour divergentes — donc une réécriture à chaque passage.
    empreinte = lambda its: [(ok, pm_acceptance.norm_label(l)) for ok, l in its]  # noqa: E731
    if local is not None and remote is not None and empreinte(md_items) == empreinte(rm_items):
        return "sync", None, []

    if local is None:
        return "pull", remote, []
    if remote is None:
        return "push", local, []

    items, diffs = pm_acceptance.union(md_items, rm_items)
    croise = {d["type"] for d in diffs}
    if "check_differs" in croise:
        return "conflit", None, ["même item coché d'un côté seulement : " + ", ".join(
            d["label"].splitlines()[0] for d in diffs if d["type"] == "check_differs")]
    if croise == {"only_md", "only_redmine"}:
        return "conflit", None, ["divergence croisée : chaque côté porte des items que "
                                 "l'autre n'a pas"]
    motifs = ["+{} item(s) repris de Redmine".format(
        sum(1 for d in diffs if d["type"] == "only_redmine"))] if "only_redmine" in croise else \
        ["Redmine est un sous-ensemble du MD : on garde le MD"]
    return "union", pm_acceptance.render_items(items), motifs


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
    ap.add_argument("--backup", default=None,
                    help="chemin du dump JSONL d'avant écriture "
                         "(défaut : var/cf-mirror-backfill-<ts>.jsonl)")
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
                          if is_task_sheet(f)]

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

    stats = {"pull": 0, "push": 0, "union": 0, "conflit": 0, "sync": 0, "vide": 0,
             "adopt": 0}
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
            if local is None and args.adopt_sections and key in SECTION_OF:
                sect = SECTION_OF[key](m.group(4))
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
            remote_de_la_description = False
            if key == "acceptance" and remote is None:
                # Côté Redmine aussi la lecture est à DOUBLE SOURCE : le CF vient d'être
                # créé, il est donc vide partout, et la matière est encore dans la
                # description. L'audit a relevé 4 tickets dont le MD n'est qu'un stub
                # (fabriqué par `redmine-fetch-task.py`, qui range tout sous « Contexte »)
                # alors que la description porte les vrais critères : sans ceci, ils ne
                # seraient jamais migrés — et leur matière resterait hors du champ.
                remote = pm_acceptance.adoptable_section(issue.get("description") or "")
                remote_de_la_description = remote is not None

            if key == "acceptance":
                action, value, motifs = decide_acceptance(local, remote, m.group(4))
                action, value, source, motifs = cf_vide_vers_push(
                    action, value, motifs, local, remote, source, remote_de_la_description)
                if action == "sync" and source != "frontmatter":
                    # Le CF porte déjà les bons critères, mais la valeur comparée venait
                    # de la SECTION du corps : le miroir local, lui, est toujours vide.
                    # Sans cette écriture le ticket resterait « non migré » pour tout ce
                    # qui lit en local — le cockpit le premier.
                    action, value, motifs = "pull", local, [
                        "CF déjà conforme : on matérialise seulement le miroir local"]
                if action == "conflit":
                    stats["conflit"] += 1
                    conflicts.append((rm_id, key, motifs[0] if motifs else "", remote))
                elif action in ("push", "pull", "union"):
                    stats["union" if action == "union" else action] += 1
                    actions.append((action, rm_id, key, path, value, source,
                                    local, remote, motifs))
                else:
                    stats[action] += 1
                continue

            if local is None and remote is None:
                stats["vide"] += 1
            elif local == remote:
                stats["sync"] += 1
            elif local is None:                        # ← Redmine seul : PULL
                stats["pull"] += 1
                actions.append(("pull", rm_id, key, path, remote, source,
                                local, remote, []))
            elif remote is None:                       # ← PM seul : PUSH
                stats["push"] += 1
                actions.append(("push", rm_id, key, path, local, source,
                                local, remote, []))
            else:                                      # ← les deux, différents
                stats["conflit"] += 1
                conflicts.append((rm_id, key, local, remote))  # les deux versions

    # ── Rapport ──────────────────────────────────────────────────────────────
    print(f"{len(paths)} fiche(s) · champs : {', '.join(fields)}")
    print(f"  déjà synchrones : {stats['sync']}   · vides des deux côtés : {stats['vide']}")
    print(f"  à REMONTER (PM → Redmine) : {stats['push']}"
          f"   · à RAPATRIER (Redmine → PM) : {stats['pull']}")
    if stats["union"]:
        print(f"  à UNIR (une source incluse dans l'autre) : {stats['union']}")
    if args.adopt_sections:
        print(f"  sections du corps adoptées comme source : {stats['adopt']}")
    if conflicts:
        print(f"\n⚠ {len(conflicts)} CONFLIT(S) — les deux côtés portent du contenu "
              f"DIFFÉRENT. Rien n'est touché ; à trancher à la main :")
        for rm_id, key, local, remote in conflicts:
            print(f"  RM{rm_id} · {key}")
            print(f"      local  : {str(local)[:160]}")
            print(f"      Redmine: {str(remote)[:160]}")

    todo = [a for a in actions
            if not (args.pull_only and a[0] in ("push", "union"))
            and not (args.push_only and a[0] == "pull")]
    if not todo:
        print("\n(rien à faire)")
        return
    print()
    for kind, rm_id, key, path, value, source, local, remote, motifs in todo:
        arrow = "→ frontmatter" if kind == "pull" else "→ Redmine"
        preview = " ⏎ ".join(str(value).splitlines() if not isinstance(value, list)
                             else value)[:110]
        print(f"  {kind.upper():5s} RM{rm_id:<5} {key:<15} {arrow:<14} "
              f"[{source}] {preview}")
        for motif in motifs:
            print(f"        · {motif}")

    if not args.go:
        print(f"\n(dry-run : {len(todo)} opération(s) — relancer avec --go pour exécuter)")
        return

    # ── Dump AVANT écriture (leçon RM2409) ───────────────────────────────────
    # Le journal Redmine garde l'ancienne valeur d'un CF, mais pas le corps du MD ni
    # ce que le script a LU pour décider. Sans ce dump, un rollback demanderait de
    # reconstituer l'entrée à partir de la sortie.
    dump = Path(args.backup) if args.backup else (
        cfg.state_dir / f"cf-mirror-backfill-{datetime.now():%Y%m%d-%H%M%S}.jsonl")
    dump.parent.mkdir(parents=True, exist_ok=True)
    with dump.open("a", encoding="utf-8") as fh:
        for kind, rm_id, key, path, value, source, local, remote, motifs in todo:
            fh.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "rm_id": rm_id, "field": key, "action": kind, "source": source,
                "path": str(path), "avant_local": local, "avant_redmine": remote,
                "apres": value, "motifs": motifs,
            }, ensure_ascii=False) + "\n")
    print(f"  ↳ dump avant écriture : {dump} ({len(todo)} entrée(s))")

    # ── Exécution ────────────────────────────────────────────────────────────
    touched = []
    for kind, rm_id, key, path, value, source, local, remote, motifs in todo:
        env_var, cf_name, is_list = MIRRORS[key]
        if kind in ("push", "union"):
            text = pm_cf_mirror.list_to_text(value) if is_list else value
            ok = pm_cf_mirror.push_text_cf(rm_id, text, env_var=env_var, cf_name=cf_name)
            print(f"  {'✓' if ok else '✗'} {kind} RM{rm_id} {key}")
            # Une union, comme une section adoptée, n'existe pas encore dans le
            # frontmatter : sans cette écriture, le miroir local resterait vide et un
            # pull futur croirait le champ absent.
            if ok and (source != "frontmatter" or kind == "union"):
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
                f"pm(cf-mirror): reprise de {len(files)} miroir(s) frontmatter↔CF "
                f"(RM2563, RM2882)")
            print(f"  ✓ commit {root} ({len(files)} fiche(s)){' ' + sha if sha else ''}")


if __name__ == "__main__":
    main()
