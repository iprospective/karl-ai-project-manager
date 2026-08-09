#!/usr/bin/env python3
"""pm-pricing-backfill — recalcule `cost_total_usd` des tickets dont le coût a été
compté à 0 (ou à un tarif périmé) — RM2342.

POURQUOI. `compute_cost_usd()` retourne **0 silencieusement** quand le modèle
n'est pas dans `pm.pricing.yml`. Chaque fois qu'Anthropic sort un modèle, tous
les tickets travaillés avec lui accumulent des tokens à coût nul jusqu'à ce que
quelqu'un ajoute la ligne (incidents : RM2163 pour `claude-fable-5`, RM2342 pour
`claude-opus-5`). Ce script rejoue l'historique avec la table de prix à jour.

SOURCE DE VÉRITÉ. Le frontmatter n'agrège les tokens que globalement — il ne dit
pas quel modèle a produit quoi. Le `.log.md`, lui, porte une entrée par tick avec
son modèle ET sa ventilation :

    ## 2026-07-30T22:08 — Tick IA (claude-opus-5)
    Tokens : 1297533 | Coût : $0.0000 | IA : 1.4 min

    Détail : input=11, output=2721, cache_read=1285681, cache_creation=9120

C'est donc le journal qui est rejoué, tick par tick, au tarif courant.

GARDE-FOUS.
  - **Journal append-only** (KERNEL) : le script n'édite JAMAIS une entrée de log
    existante. Il corrige `cost_total_usd` dans le frontmatter et **appende** une
    entrée de rattrapage traçant l'ancien et le nouveau montant.
  - **Couverture** : les ticks < 1000 tokens ne sont pas journalisés (seuil du
    hook), donc la somme des ticks est un minorant de `tokens_total`. Si les
    ticks parsés couvrent moins de `--min-coverage` (défaut 90 %) des tokens du
    ticket, le ticket est **signalé et non écrit** — sauf `--force`.
  - **Backup** : chaque ticket touché est dumpé en JSONL avant écriture.
  - **Dry-run par défaut** ; `--apply` pour écrire.

Usage :
    pm-pricing-backfill.py                    # dry-run sur tous les projets
    pm-pricing-backfill.py --entity iprospective --apply
    pm-pricing-backfill.py --rm-id 2457 --apply --verbose
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("ERREUR : PyYAML requis.")

# ── Format des entrées de tick dans le .log.md ──────────────────────────────
RE_TICK_HEADER = re.compile(r"^##\s+(\S+)\s+—\s+Tick IA\s+\((?P<model>[^)]+)\)\s*$")
RE_DETAIL = re.compile(
    r"^Détail\s*:\s*input=(?P<input>\d+),\s*output=(?P<output>\d+),\s*"
    r"cache_read=(?P<cache_read>\d+),\s*cache_creation=(?P<cache_creation>\d+)"
)
RE_TOKENS_LINE = re.compile(r"^Tokens\s*:\s*(?P<tokens>\d+)\s*\|")

FIELDS = ("input", "output", "cache_read", "cache_creation")
PRICE_KEY = {
    "input": "input_per_mtok_usd",
    "output": "output_per_mtok_usd",
    "cache_read": "cache_read_per_mtok_usd",
    "cache_creation": "cache_creation_per_mtok_usd",
}


def load_pricing():
    """Table de prix résolue relativement à CE script (comme pm-task-tick)."""
    p = Path(__file__).resolve().parent.parent / "pm.pricing.yml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return cfg.get("models") or {}


def cost_of(model, counts, pricing):
    """USD d'un tick. Retourne None si le modèle est inconnu (≠ 0, qui est un
    montant valide) — l'appelant doit distinguer « gratuit » de « non tarifé »."""
    m = pricing.get(model)
    if not m:
        return None
    return sum(counts[f] * m.get(PRICE_KEY[f], 0) / 1_000_000 for f in FIELDS)


def parse_ticks(log_path):
    """(ticks, unparsable) — un tick = {model, counts, tokens}."""
    if not log_path.is_file():
        return [], 0
    ticks, unparsable, cur = [], 0, None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        h = RE_TICK_HEADER.match(line)
        if h:
            if cur is not None and cur.get("counts") is None:
                unparsable += 1  # tick sans ligne Détail
            cur = {"model": h.group("model").strip(), "counts": None, "tokens": 0}
            ticks.append(cur)
            continue
        if cur is None:
            continue
        t = RE_TOKENS_LINE.match(line)
        if t and cur["tokens"] == 0:
            cur["tokens"] = int(t.group("tokens"))
            continue
        d = RE_DETAIL.match(line)
        if d and cur["counts"] is None:
            cur["counts"] = {f: int(d.group(f)) for f in FIELDS}
    if cur is not None and cur.get("counts") is None:
        unparsable += 1
    return [t for t in ticks if t["counts"] is not None], unparsable


def split_frontmatter(raw):
    if not raw.startswith("---\n"):
        return None, None
    parts = raw.split("---\n", 2)
    return (parts[1], parts[2]) if len(parts) >= 3 else (None, None)


def set_scalar(fm, key, value):
    """Remplace `key: ...` au niveau racine du frontmatter (texte, pas de re-dump
    YAML : on ne veut réécrire ni l'ordre ni les commentaires du reste)."""
    out, done = [], False
    for line in fm.splitlines(keepends=True):
        if not done and line.startswith(f"{key}:"):
            out.append(f"{key}: {value}\n")
            done = True
        else:
            out.append(line)
    return "".join(out), done


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entity", help="limiter à un client/entité")
    ap.add_argument("--rm-id", type=int, help="limiter à un ticket")
    ap.add_argument("--apply", action="store_true", help="écrire (défaut : dry-run)")
    ap.add_argument("--force", action="store_true",
                    help="écrire même si la couverture est sous le seuil")
    ap.add_argument("--min-coverage", type=float, default=0.90,
                    help="couverture minimale tokens ticks/total (défaut 0.90)")
    ap.add_argument("--backup", default=None,
                    help="chemin du dump JSONL (défaut : var/pricing-backfill-<ts>.jsonl)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = PMConfig.load()
    pricing = load_pricing()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    backup_path = Path(args.backup) if args.backup else (
        cfg.state_dir / f"pricing-backfill-{datetime.now():%Y%m%d-%H%M%S}.jsonl")
    if args.apply:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_fh = backup_path.open("a", encoding="utf-8")
    else:
        backup_fh = None

    stats = {"scanned": 0, "changed": 0, "skipped_coverage": 0,
             "unknown_model": 0, "no_ticks": 0}
    delta_total = 0.0
    unknown_models = {}

    for ent, proj, _ in cfg.iter_projects(entity=args.entity):
        tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
        if not tasks_dir.is_dir():
            continue
        pattern = f"RM{args.rm_id}_*.md" if args.rm_id else "RM*.md"
        for md in sorted(tasks_dir.glob(pattern)):
            if md.name.endswith(".log.md"):
                continue
            raw = md.read_text(encoding="utf-8")
            fm, body = split_frontmatter(raw)
            if fm is None:
                continue
            try:
                meta = yaml.safe_load(fm) or {}
            except yaml.YAMLError:
                continue
            tokens_total = int(meta.get("tokens_total") or 0)
            if tokens_total <= 0:
                continue
            stats["scanned"] += 1
            old_cost = float(meta.get("cost_total_usd") or 0.0)

            log_path = md.with_suffix("").with_suffix(".log.md") \
                if md.name.endswith(".md") else None
            log_path = md.parent / (md.name[:-3] + ".log.md")
            ticks, unparsable = parse_ticks(log_path)
            if not ticks:
                stats["no_ticks"] += 1
                if args.verbose:
                    print(f"  · {md.name} : aucun tick ventilé dans le journal — ignoré")
                continue

            new_cost, covered, unknown = 0.0, 0, False
            for t in ticks:
                c = cost_of(t["model"], t["counts"], pricing)
                if c is None:
                    unknown = True
                    unknown_models[t["model"]] = unknown_models.get(t["model"], 0) + 1
                    continue
                new_cost += c
                covered += sum(t["counts"].values())

            if unknown:
                stats["unknown_model"] += 1

            coverage = covered / tokens_total if tokens_total else 0.0
            if coverage < args.min_coverage and not args.force:
                stats["skipped_coverage"] += 1
                print(f"  ⚠ {md.name} : couverture {coverage:.0%} < "
                      f"{args.min_coverage:.0%} ({covered}/{tokens_total} tokens) — non écrit")
                continue

            if abs(new_cost - old_cost) < 0.005:
                continue

            stats["changed"] += 1
            delta_total += new_cost - old_cost
            print(f"  {'✓' if args.apply else '→'} {md.name} : "
                  f"${old_cost:.4f} → ${new_cost:.4f} "
                  f"({len(ticks)} tick(s), couverture {coverage:.0%})")

            if not args.apply:
                continue

            backup_fh.write(json.dumps({
                "path": str(md), "at": now, "tokens_total": tokens_total,
                "cost_total_usd_before": old_cost, "cost_total_usd_after": round(new_cost, 6),
                "ticks": len(ticks), "unparsable_ticks": unparsable,
                "coverage": round(coverage, 4),
            }, ensure_ascii=False) + "\n")
            backup_fh.flush()

            fm2, ok = set_scalar(fm, "cost_total_usd", f"{new_cost:.6f}")
            if not ok:
                print(f"    ✗ champ cost_total_usd introuvable — ignoré", file=sys.stderr)
                continue
            fm2, _ = set_scalar(fm2, "updated", now)
            md.write_text("---\n" + fm2 + "---\n" + body, encoding="utf-8")

            # Journal : append-only — on ne réécrit pas les « Coût : $0.0000 »
            # déjà inscrits, on trace la correction en fin de fichier.
            with log_path.open("a", encoding="utf-8") as lf:
                lf.write(
                    f"\n## {now} — Backfill tarifaire (RM2342)\n"
                    f"Tokens : 0 | Coût : $0.0000\n\n"
                    f"Recalcul de `cost_total_usd` sur {len(ticks)} tick(s) journalisé(s) "
                    f"avec `pm.pricing.yml` à jour : ${old_cost:.4f} → ${new_cost:.4f} "
                    f"(couverture {coverage:.0%} des {tokens_total} tokens du ticket).\n"
                    f"Les montants inscrits dans les entrées de tick ci-dessus sont "
                    f"conservés tels quels (journal append-only).\n"
                )

    if backup_fh:
        backup_fh.close()

    print(f"\n── Backfill {'appliqué' if args.apply else '(dry-run)'} ──")
    print(f"  tickets avec tokens   : {stats['scanned']}")
    print(f"  corrigés              : {stats['changed']}  (Δ ${delta_total:+.2f})")
    print(f"  sans tick ventilé     : {stats['no_ticks']}")
    print(f"  couverture < seuil    : {stats['skipped_coverage']}")
    if unknown_models:
        print(f"  ⚠ modèles ABSENTS de pm.pricing.yml (coût compté 0) :")
        for m, n in sorted(unknown_models.items(), key=lambda kv: -kv[1]):
            print(f"      {m} — {n} tick(s)")
    if args.apply:
        print(f"  backup                : {backup_path}")
    else:
        print("  (dry-run : --apply pour écrire)")


if __name__ == "__main__":
    main()
