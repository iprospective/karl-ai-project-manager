#!/usr/bin/env python3
"""pm-pricing-check — Vérifie pm.pricing.yml contre la doc officielle Anthropic.

Conçu pour un cron quotidien (RM2165). Ne modifie JAMAIS pm.pricing.yml :
en cas d'écart, crée un ticket Redmine (tag `pricing-watch`) avec le diff,
et l'humain valide/corrige. Dédup : pas de nouveau ticket tant qu'un ticket
`pricing-watch` est encore ouvert.

Pipeline :
  1. fetch des pages doc (endpoints .md, parsables) — urllib, pas de dépendance ;
  2. comparaison déléguée à `claude -p` en headless SANS outils (le contenu est
     fourni sur stdin ; modèle sonnet = suffisant et peu coûteux) → JSON strict ;
  3. si drift → ticket via pm-task-add.py (CF IA posé par l'outil).

Usage :
    pm-pricing-check.py [--dry-run] [--model M] [-v]

Cron (cf. cron.example.sh) :
    30 8 * * * python3 $PM_DIR/scripts/pm-pricing-check.py >> $HOME/.local/log/pm-pricing-check.log 2>&1
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

PRICING_FILE = Path(__file__).resolve().parent.parent / "pm.pricing.yml"
DOC_URLS = [
    # endpoints .md (markdown brut) ; pricing.md renvoie 404 (testé 2026-07-08),
    # la table tarifaire de l'overview suffit
    "https://platform.claude.com/docs/en/about-claude/models/overview.md",
]
DEFAULT_MODEL = "claude-sonnet-4-6"   # extraction/diff simple : sonnet suffit
TICKET_PROJECT = "iprospective/pm-ai-agents"
TICKET_TAG = "pricing-watch"

PROMPT = """Tu compares la grille tarifaire interne (YAML ci-dessous) avec la \
documentation officielle Anthropic (markdown ci-dessous). Unité : USD par MTok.

Règles :
- Compare, pour chaque modèle présent dans le YAML, les 4 champs : input, output, \
cache read (~0.1x input), cache creation (~1.25x input). Si la doc ne donne que \
input/output, déduis cache read = input x 0.1 et cache creation = input x 1.25 et \
ne signale un écart cache QUE s'il dépasse 10 %.
- Signale aussi tout modèle ACTIF côté doc (tier courant : Fable/Mythos, Opus, \
Sonnet, Haiku) absent du YAML. Ignore les modèles legacy/dépréciés/retirés absents \
du YAML.
- IGNORE les tarifs promotionnels/introductifs datés (ex. « intro through ... ») : \
la référence est le tarif normal.
- Si la doc est illisible ou ne contient pas de tarifs, status = "error".

Réponds UNIQUEMENT avec un objet JSON, sans markdown autour :
{"status": "ok" | "drift" | "error",
 "diffs": [{"model": "...", "field": "input|output|cache_read|cache_creation",
            "yaml_usd": 0.0, "official_usd": 0.0}],
 "missing_models": [{"model": "...", "input_usd": 0.0, "output_usd": 0.0}],
 "notes": "une phrase max"}
"""


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "pm-pricing-check/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def run_claude(model, payload):
    exe = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    proc = subprocess.run(
        [exe, "-p", PROMPT, "--model", model],
        input=payload, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p rc={proc.returncode}: {proc.stderr[:500]}")
    m = re.search(r"\{.*\}", proc.stdout, re.DOTALL)
    if not m:
        raise RuntimeError(f"pas de JSON dans la sortie: {proc.stdout[:500]}")
    return json.loads(m.group(0))


def open_watch_ticket_exists(cfg):
    """True si un ticket tagué pricing-watch est encore ouvert (dédup cron)."""
    entity, project = TICKET_PROJECT.split("/")
    tasks_dir = cfg.path("tasks_dir", entity=entity, project=project)
    fm_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    for md in tasks_dir.glob("RM*_*.md"):
        if md.name.endswith(".log.md"):
            continue
        m = fm_re.match(md.read_text(encoding="utf-8"))
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if TICKET_TAG in (fm.get("tags") or []) and fm.get("status") != "ferme":
            return fm.get("redmine_id")
    return None


def create_ticket(verdict, dry_run):
    lines = ["Écart(s) détecté(s) par pm-pricing-check (cron quotidien RM2165) "
             f"le {datetime.now():%Y-%m-%d %H:%M} :", ""]
    for d in verdict.get("diffs") or []:
        lines.append(f"- {d['model']} / {d['field']} : YAML {d['yaml_usd']} USD/MTok "
                     f"vs officiel {d['official_usd']} USD/MTok")
    for miss in verdict.get("missing_models") or []:
        lines.append(f"- modèle actif ABSENT du YAML : {miss['model']} "
                     f"(input {miss.get('input_usd')}, output {miss.get('output_usd')})")
    if verdict.get("notes"):
        lines += ["", f"Note : {verdict['notes']}"]
    lines += ["", "À faire : vérifier sur la doc officielle puis corriger pm.pricing.yml "
              "(branche + MR, cf. RM2163). Ne pas appliquer le diff aveuglément : "
              "il provient d'une extraction LLM."]
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "pm-task-add.py"),
           "--project", TICKET_PROJECT,
           "--title", "Tarifs Anthropic : écart détecté avec pm.pricing.yml",
           "--type", "maintenance", "--priority", "high",
           "--tags", f"pricing,{TICKET_TAG}",
           "--description", "\n".join(lines)]
    if dry_run:
        print("[dry-run] ticket non créé ; description :\n" + "\n".join(lines))
        return
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="pas de ticket, affiche le verdict")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    docs = []
    for url in DOC_URLS:
        try:
            docs.append(f"<!-- {url} -->\n" + fetch(url))
        except Exception as e:  # une page KO n'invalide pas l'autre
            print(f"{ts} ⚠ fetch {url}: {e}", file=sys.stderr)
    if not docs:
        sys.exit(f"{ts} ✗ aucune page doc récupérée — check impossible")

    payload = ("=== GRILLE INTERNE (pm.pricing.yml) ===\n"
               + PRICING_FILE.read_text(encoding="utf-8")
               + "\n\n=== DOC OFFICIELLE ===\n" + "\n\n".join(docs))
    verdict = run_claude(args.model, payload)
    if args.verbose:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))

    status = verdict.get("status")
    if status == "ok":
        print(f"{ts} ✓ tarifs alignés")
        return
    if status == "error":
        sys.exit(f"{ts} ✗ comparaison impossible : {verdict.get('notes')}")

    if args.dry_run:  # pas de dédup en dry-run (PMConfig exige le .env canonique)
        create_ticket(verdict, dry_run=True)
        return
    rm = open_watch_ticket_exists(PMConfig.load())
    if rm:
        print(f"{ts} ⚠ drift détecté mais RM{rm} ({TICKET_TAG}) déjà ouvert — pas de doublon")
        return
    create_ticket(verdict, dry_run=False)
    print(f"{ts} ⚠ drift détecté → ticket créé")


if __name__ == "__main__":
    main()
