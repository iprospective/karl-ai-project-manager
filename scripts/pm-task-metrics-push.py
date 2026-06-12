#!/usr/bin/env python3
"""pm-task-metrics-push — Pousse l'ESTIMATION d'une tâche vers Redmine.

Pont MD → Redmine pour le volet *prévisionnel* du ROI (NORMS § « ROI assisté
par IA »). Les IDs de CF viennent de la source unique `redmine.reference.yml`
(via redmine_utils).

Mode unique :

  --estimate         Pousse l'estimation (frontmatter `estimate`) vers les champs :
                       estimate.tokens            → CF « Tokens prévus » (21)
                       estimate.ai_time_minutes/60 → CF « Temps estimé IA (h) » (22)
                       estimate.estimated_model   → CF « LLM prévu » (25, via llm_tiers)
                       estimate.human_time_minutes/60 → estimated_hours (natif)
                     À faire à la création, à la prise de ticket si manquante, et
                     à la maj de description si l'estimation a changé.

⚠ Périmètre réduit par RM1825 (réconciliation du doublon RM1806/RM1819) : le
report de la CONSOMMATION (time_entries CF16 + cumul CF17 « Tokens passés »)
est porté exclusivement par `pm-task-report.py` (ancrage sur les entrées
datées du `.log.md`, dédup par ledger `reporting.time_entries[]`). Les anciens
modes `--commit`/`--cumul` de ce script sont retirés ; les marqueurs
`metrics.reported_*` du frontmatter sont obsolètes (laissés en place, plus
jamais écrits).
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import redmine_utils

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def read_task(rm_id):
    """Retourne (md_path, fm_dict, m_match). Sys.exit si introuvable."""
    cfg = PMConfig.load()
    md_path = cfg.find_task(rm_id)
    if not md_path:
        sys.exit(f"ERREUR : RM{rm_id} introuvable")
    content = md_path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {md_path}")
    return md_path, (yaml.safe_load(m.group(2)) or {}), m


def write_task_fm(md_path, fm, m):
    """Réécrit le MD avec le frontmatter modifié (corps préservé)."""
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")


def get_metrics(fm):
    """Bloc `metrics` du frontmatter, préservé tel quel (créé si absent).

    Les clés legacy (`reported_*`, `last_time_entry_id`) des anciens modes
    --commit/--cumul (retirés, RM1825) sont conservées sans être réécrites.
    """
    return dict(fm.get("metrics") or {})


# ── Mode ─────────────────────────────────────────────────────────────────────

def _verify_pushed(rm_id, cfs, est_hours):
    """Re-GET et avertit si un CF/estimated_hours poussé n'a pas pris (silent drop)."""
    iss = redmine_utils.fetch_issue(rm_id)
    live = {c["id"]: (c.get("value") or "") for c in iss.get("custom_fields", [])}
    present = set(live)
    for c in (cfs or []):
        cid = c["id"]
        if cid not in present:
            print(f"  ⚠ CF{cid} non présent sur le ticket (champ non associé au tracker "
                  f"'{(iss.get('tracker') or {}).get('name')}' ?) — valeur ignorée par Redmine.",
                  file=sys.stderr)
        elif str(live[cid]) != str(c["value"]):
            print(f"  ⚠ CF{cid} = {live[cid]!r} après push (attendu {c['value']!r}) — drop probable.",
                  file=sys.stderr)
    if est_hours is not None:
        got = iss.get("estimated_hours")
        if got is None or abs(float(got) - float(est_hours)) > 0.001:
            print(f"  ⚠ estimated_hours = {got!r} après push (attendu {est_hours}).", file=sys.stderr)


def resolve_llm_tier(estimated_model):
    """Mappe un nom de modèle → value id du CF « LLM prévu » via llm_tiers.model_match.

    Retourne (value_id_str, label) ou (None, None) si pas de modèle / pas de match.
    """
    if not estimated_model:
        return None, None
    tiers = redmine_utils.load_reference().get("llm_tiers") or {}
    matches = tiers.get("model_match") or {}
    low = str(estimated_model).lower()
    for substr, vid in matches.items():
        if str(substr).lower() in low:
            label = (tiers.get("values") or {}).get(vid)
            return str(vid), label
    return None, None


def do_estimate(rm_id, fm, md_path, m, dry_run):
    est = fm.get("estimate") or {}
    cf21 = redmine_utils.cf_id_by_name("Tokens prévus")
    cf22 = redmine_utils.cf_id_by_name("Temps estimé IA (h)")
    cf25 = redmine_utils.cf_id_by_name("LLM prévu")
    cfs = []
    if est.get("tokens") is not None and cf21:
        cfs.append({"id": cf21, "value": str(int(est["tokens"]))})
    est_hours = None
    if est.get("human_time_minutes") is not None:
        est_hours = round(est["human_time_minutes"] / 60.0, 2)
    if est.get("ai_time_minutes") is not None and cf22:
        cfs.append({"id": cf22, "value": str(round(est["ai_time_minutes"] / 60.0, 2))})
    if cf25:
        tier_id, tier_label = resolve_llm_tier(est.get("estimated_model"))
        if tier_id:
            cfs.append({"id": cf25, "value": tier_id})
        elif est.get("estimated_model"):
            print(f"  ⚠ LLM prévu : modèle {est['estimated_model']!r} non mappé "
                  f"(llm_tiers.model_match) → CF{cf25} non poussé.", file=sys.stderr)

    if not cfs and est_hours is None:
        print("  · estimation : rien à pousser (estimate vide)")
        return False
    desc = [f"CF{c['id']}={c['value']}" for c in cfs]
    if est_hours is not None:
        desc.append(f"estimated_hours={est_hours}")
    if dry_run:
        print(f"--dry-run : estimation → {', '.join(desc)}")
        return False
    ok, err = redmine_utils.update_issue_fields(rm_id, custom_fields=cfs or None,
                                                estimated_hours=est_hours)
    if not ok:
        sys.exit(f"ERREUR push estimation : {err}")
    print(f"✓ estimation poussée : {', '.join(desc)}")
    # Vérification : Redmine renvoie 204 même quand il *drop* un CF non associé au
    # tracker ou interdit par permissions (cf. knowledge/redmine/api.md). On re-GET
    # pour confirmer que chaque valeur a bien pris.
    _verify_pushed(rm_id, cfs, est_hours)
    mt = get_metrics(fm)
    mt["estimate_pushed_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    fm["metrics"] = mt
    return True


REMOVED_MODES_MSG = (
    "ERREUR : le mode {mode} a été RETIRÉ de pm-task-metrics-push (RM1825 — "
    "réconciliation du doublon RM1806/RM1819).\n"
    "Le report de la consommation (time_entries CF16 + cumul CF17) est porté par :\n"
    "  scripts/pm-task-report.py --rm-id <id> --apply      # un ticket\n"
    "  scripts/pm-task-report.py --all --apply             # batch\n"
    "Ce script ne pousse plus que l'ESTIMATION (--estimate)."
)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rm-id", type=int, required=True)
    ap.add_argument("--estimate", action="store_true", help="Pousse l'estimation (CF21/22/25 + estimated_hours)")
    # Stubs de dépréciation (RM1825) : modes retirés, message d'orientation.
    ap.add_argument("--commit", metavar="HASH", help=argparse.SUPPRESS)
    ap.add_argument("--cumul", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.commit:
        sys.exit(REMOVED_MODES_MSG.format(mode="--commit"))
    if args.cumul:
        sys.exit(REMOVED_MODES_MSG.format(mode="--cumul"))
    if not args.estimate:
        sys.exit("ERREUR : préciser --estimate (seul mode ; le report conso vit dans pm-task-report.py).")

    md_path, fm, m = read_task(args.rm_id)
    dirty = do_estimate(args.rm_id, fm, md_path, m, args.dry_run)

    if dirty and not args.dry_run:
        write_task_fm(md_path, fm, m)
        print(f"✓ frontmatter métriques mis à jour : {md_path.name}")


if __name__ == "__main__":
    main()
