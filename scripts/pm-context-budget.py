#!/usr/bin/env python3
"""pm-context-budget — Mesure le contexte « toujours chargé » d'une session PM par rôle (RM1943).

Compose, pour un rôle donné, l'ensemble des fichiers que l'onboarding NORMS
charge systématiquement, et en estime le coût en tokens :

  1. Pont workspace : /zfs/workspaces/AGENTS.md (lu par remontée d'arborescence)
  2. Instructions repo PM : CLAUDE.md
  3. KERNEL : norms/src/NORMS-KERNEL.md
  4. Modules préchargés par le rôle (en-têtes `Préchargé par :` des modules ;
     `tous` = tous les rôles) — les autres modules sont à la demande (non comptés)
  5. agents/worker-common.md + agents/<rôle>.md
  6. (option --entity/--project) cascade : client/*.md + memory + project/*.md + memory
  7. (option --with-host) ~/.claude/CLAUDE.md (instructions globales de la machine)

Estimation : tokens ≈ octets / 3.6 (texte FR + markdown, ordre de grandeur —
le tokenizer réel n'est pas accessible hors API ; biais < ±15 %).

Modes :
  --role <r>                 détail d'un rôle (défaut : worker-dev)
  --all-roles                tableau comparatif de tous les rôles
  --before                   substitue l'ancien NORMS.md monolithique au
                             KERNEL+modules (mesure avant RM1922)
  --entity E --project P     ajoute la cascade d'un projet réel
  --check                    compare au budget pm.config.yml :: context.budget_tokens
                             (exit 1 si dépassé) — utilisé par pm-norms-doctor
  --notify                   n'échoue JAMAIS : signale dans le fil de notifications que la
                             marge de sécurité est entamée (défaut : 90 % du plafond)

Deux capteurs, deux natures (RM2756) : le **plafond** est un invariant — le franchir casse
`--check`, et c'est bien le rôle d'un test. La **marge** est une TENDANCE : elle s'entame
lentement, sur des semaines, et un test qui reste rouge des semaines n'apprend plus rien —
il apprend à ignorer les échecs rouges. Une tendance se NOTIFIE ; un invariant casse.
"""
import argparse
import re
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

PM_DIR = Path(__file__).resolve().parent.parent
SRC = PM_DIR / "norms" / "src"
MODULES = SRC / "modules"
AGENTS = PM_DIR / "agents"
BYTES_PER_TOKEN = 3.6

ROLES = ["worker-dev", "worker-analyst", "worker-db", "worker-design",
         "worker-infra", "reviewer", "summarizer", "orchestrateur"]
PRELOAD_RE = re.compile(r"\*\*Préchargé par :\*\*\s*(.+?)\.?\s*$")


def tokens(path):
    try:
        return int(round(path.stat().st_size / BYTES_PER_TOKEN))
    except OSError:
        return 0


def preloaded_modules(role):
    """Modules dont l'en-tête déclare ce rôle (ou `tous`)."""
    short = role.replace("worker-", "") if role.startswith("worker-") else role
    out = []
    for f in sorted(MODULES.glob("*.md")):
        for line in f.read_text(encoding="utf-8").splitlines()[:4]:
            m = PRELOAD_RE.search(line)
            if not m:
                continue
            who = [w.strip().rstrip(".") for w in m.group(1).split(",")]
            if "tous" in who or role in who or short in who:
                out.append(f)
            break
    return out


def components(role, before=False, entity=None, project=None, with_host=False):
    """[(label, path, tokens)] du contexte toujours-chargé pour ce rôle."""
    comp = []

    def add(label, p):
        if p and p.is_file():
            comp.append((label, p, tokens(p)))

    add("pont /zfs/workspaces/AGENTS.md", Path("/zfs/workspaces/AGENTS.md"))
    add("CLAUDE.md (repo PM)", PM_DIR / "CLAUDE.md")
    if with_host:
        add("~/.claude/CLAUDE.md (host)", Path.home() / ".claude" / "CLAUDE.md")
    if before:
        add("NORMS.md monolithique (avant RM1922)", PM_DIR / "norms" / "NORMS.md")
    else:
        add("NORMS-KERNEL.md", SRC / "NORMS-KERNEL.md")
        for f in preloaded_modules(role):
            add(f"module préchargé {f.stem}", f)
    add("agents/worker-common.md", AGENTS / "worker-common.md")
    role_file = AGENTS / (f"{role}.md" if not (AGENTS / f"worker-{role}.md").is_file()
                          else f"worker-{role}.md")
    add(f"agents/{role_file.name}", role_file)

    if entity and project:
        cfg = PMConfig.load()
        for label, key, kw in (
                ("cascade client/*.md", "entity_client_dir", {"entity": entity}),
                ("cascade client memory/*.md", "entity_memory_dir", {"entity": entity}),
                ("cascade project/*.md", "project_dir", {"entity": entity, "project": project}),
                ("cascade docs/*.md", "docs_dir", {"entity": entity, "project": project}),
                ("cascade project memory/*.md", "project_memory_dir", {"entity": entity, "project": project})):
            d = cfg.path(key, **kw)
            if d.is_dir():
                t = sum(tokens(p) for p in d.glob("*.md"))
                if t:
                    comp.append((f"{label} ({d.relative_to(cfg.projects_root)})", d, t))
    return comp


def load_budget():
    cfg = yaml.safe_load((PM_DIR / "pm.config.yml").read_text(encoding="utf-8")) or {}
    return ((cfg.get("context") or {}).get("budget_tokens") or {})


def notifie(ratio: float = 0.9) -> int:
    """Dit dans le FIL que la marge est entamée — et ne casse jamais rien.

    Le message est volontairement STABLE : les chiffres partent en champs, pas dans le texte.
    C'est ce qui fait qu'une dérive qui dure produit UNE entrée qui remonte, et non une par
    passage — la mesure bouge de quelques tokens à chaque commit de NORMS."""
    budgets = load_budget()
    defaut = budgets.get("default")
    if not defaut:
        print("aucun budget par défaut déclaré (pm.config.yml :: context.budget_tokens)")
        return 0
    mesures = {r: sum(t for _, _, t in components(r)) for r in ROLES}
    pire_role = max(mesures, key=lambda r: mesures[r])
    pire = mesures[pire_role]
    seuil = int(defaut * ratio)
    part = pire / defaut * 100
    if pire <= seuil:
        print(f"marge saine : {pire:,} / {defaut:,} ({part:.0f} %), pire rôle {pire_role}")
        return 0

    depasse = pire > defaut
    msg = ("la précharge NORMS DÉPASSE le plafond de contexte" if depasse
           else "la précharge NORMS a entamé sa marge de sécurité")
    print(f"{msg} — {pire:,} / {defaut:,} ({part:.0f} %), pire rôle {pire_role}")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pm_notify
        pm_notify.add("system", "critical" if depasse else "warn", msg,
                      job="norms-budget", role=pire_role, tokens=pire, budget=defaut,
                      pct=round(part))
    except Exception:      # noqa: BLE001 — un fil indisponible ne casse pas une mesure
        pass
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", default="worker-dev", choices=ROLES)
    ap.add_argument("--all-roles", action="store_true")
    ap.add_argument("--before", action="store_true",
                    help="NORMS.md monolithique au lieu du KERNEL+modules (avant RM1922)")
    ap.add_argument("--entity")
    ap.add_argument("--project")
    ap.add_argument("--with-host", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="Compare chaque rôle à context.budget_tokens (exit 1 si dépassé)")
    ap.add_argument("--notify", action="store_true",
                    help="signale une marge entamée dans le fil de notifications (n'échoue jamais)")
    ap.add_argument("--warn-ratio", type=float, default=0.9,
                    help="part du plafond à partir de laquelle la marge est dite entamée (défaut 0.9)")
    ap.add_argument("--json", action="store_true",
                    help="sortie machine : ce que lit la santé du poste (cockpit, famille PM)")
    args = ap.parse_args()

    if args.notify:
        return notifie(args.warn_ratio)

    if args.json:
        budgets = load_budget()
        defaut = budgets.get("default")
        roles = {}
        for role in ROLES:
            total = sum(t for _, _, t in components(role))
            b = budgets.get(role, defaut)
            roles[role] = {"tokens": total, "budget": b, "ok": (b is None or total <= b)}
        depasses = sorted([r for r, v in roles.items() if not v["ok"]])
        print(json.dumps({"ok": not depasses, "budget": defaut, "roles": roles,
                          "depassements": depasses,
                          "mesure_le": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False))
        return

    if args.check or args.all_roles:
        budgets = load_budget() if args.check else {}
        default_budget = budgets.get("default")
        over = []
        print(f"{'rôle':<16} {'tokens':>8}  {'vs avant':>9}  {'budget':>8}")
        before_total = sum(t for _, _, t in components("worker-dev", before=True))
        for role in ROLES:
            total = sum(t for _, _, t in components(role))
            budget = budgets.get(role, default_budget)
            ratio = f"-{(1 - total / before_total) * 100:.0f}%" if before_total else "?"
            mark = ""
            if budget:
                if total > budget:
                    over.append(role)
                    mark = "  ✗ DÉPASSÉ"
                else:
                    mark = "  ✓"
            print(f"{role:<16} {total:>8,}  {ratio:>9}  {budget or '—':>8}{mark}")
        print(f"\n(référence avant RM1922, NORMS monolithique : {before_total:,} tokens ; "
              f"estimation octets/{BYTES_PER_TOKEN})")
        if args.check and over:
            sys.exit(1)
        return

    comp = components(args.role, before=args.before, entity=args.entity,
                      project=args.project, with_host=args.with_host)
    total = sum(t for _, _, t in comp)
    print(f"== contexte toujours-chargé — rôle {args.role}"
          f"{' (AVANT RM1922)' if args.before else ''} ==")
    for label, _, t in comp:
        print(f"  {t:>7,}  {label}")
    print(f"  {total:>7,}  TOTAL (≈ tokens, octets/{BYTES_PER_TOKEN})")

    # Garde-fou cascade docs (RM2368, CDC RM2316 § S7) : le dossier docs/ d'un
    # projet ne doit pas dépasser context.budget_tokens.project_docs (les docs
    # se lisent à la demande via docs/INDEX.md — pas en lecture intégrale).
    if args.entity and args.project:
        docs_budget = load_budget().get("project_docs")
        docs_total = sum(t for label, _, t in comp if label.startswith("cascade docs/"))
        if docs_budget and docs_total > docs_budget:
            print(f"✗ cascade docs : {docs_total:,} tokens > budget project_docs "
                  f"{docs_budget:,} — découper/archiver, et lecture via docs/INDEX.md")
            sys.exit(1)


if __name__ == "__main__":
    main()
