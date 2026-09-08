#!/usr/bin/env python3
"""cockpit-view-cost — ce que coûte, en tokens, ouvrir un domaine du cockpit (RM3008).

Objectif de la refonte (RM2889) : un agent qui doit modifier une vue ne charge que les
fichiers de son domaine — modèle, dépôt, service, ViewModel, vue, contrôleur, style, test —
et non le monolithe (~120 k tokens). Ce script mesure ce coût domaine par domaine
(approximation : 4 caractères ≈ 1 token) et ventile par couche, pour savoir quoi découper.

Usage :
    cockpit-view-cost.py                 # tableau texte, trié par coût décroissant
    cockpit-view-cost.py --md            # tableau markdown (à coller dans cockpit/README.md)
    cockpit-view-cost.py --json          # brut, pour un outil
    cockpit-view-cost.py --check 15000   # sortie 1 si la VUE d'un domaine coûte plus (garde de test)
    cockpit-view-cost.py --domain sets   # un seul domaine, fichier par fichier
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COCKPIT = ROOT / "deploy" / "karl-agent" / "cockpit"
CHARS_PER_TOKEN = 4
LAYERS = ("model", "repository", "service", "viewmodel", "view", "controller", "style", "test")
# ce qu'un agent lit pour modifier UNE VUE : la vue, son ViewModel, le contrôleur qui la monte — et les tests de ces couches.
# RM3017+ : un test scindé par couche (`test_cockpit_<d>.model.js`) reste dans le total du domaine mais SORT du coût « vue ».
VIEW_SET = ("viewmodel", "view", "controller", "test")
TEST_MODEL_SUFFIX = ".model.js"


def layer_of(name: str) -> str:
    """Couche d'un fichier de module, par son SUFFIXE (même règle que test_cockpit_core.js § 12)."""
    if name.endswith(".scss"):
        return "style"
    if name.endswith(".controller.js"):
        return "controller"
    if name.endswith(".service.js"):
        return "service"
    if name.endswith(".view.js"):
        return "view"
    if name.endswith("Repository.js"):
        return "repository"
    if "ViewModel" in name:
        return "viewmodel"
    return "model"


def tokens(n_chars: int) -> int:
    return (n_chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def measure_domain(d: Path, cockpit: Path = COCKPIT) -> dict:
    files = []
    for f in sorted(d.iterdir()):
        if f.is_file() and (f.suffix in (".js", ".scss")):
            files.append({"file": f.name, "layer": layer_of(f.name), "chars": f.stat().st_size})
    for t in sorted(cockpit.glob(f"test_cockpit_{d.name}.js")) + sorted(cockpit.glob(f"test_cockpit_{d.name}.*.js")):
        files.append({"file": t.name, "layer": "test", "chars": t.stat().st_size, "model_only": t.name.endswith(TEST_MODEL_SUFFIX)})
    by = {k: 0 for k in LAYERS}
    for f in files:
        by[f["layer"]] += f["chars"]
    total = sum(by.values())
    view = sum(by[k] for k in VIEW_SET if k != "test") + sum(f["chars"] for f in files if f["layer"] == "test" and not f.get("model_only"))
    return {"domain": d.name, "files": files, "chars": total, "tokens": tokens(total),
            "view_tokens": tokens(view), "layers": {k: tokens(v) for k, v in by.items()}}


def measure_all(cockpit: Path = COCKPIT) -> list[dict]:
    mods = cockpit / "src" / "modules"
    out = [measure_domain(d, cockpit) for d in sorted(mods.iterdir()) if d.is_dir()]
    core = cockpit / "src" / "core"
    if core.is_dir():
        c = measure_domain(core, cockpit)
        c["domain"] = "core"
        out.append(c)
    return sorted(out, key=lambda x: -x["tokens"])


def table(rows: list[dict], md: bool, limit: int | None) -> str:
    head = ["domaine", "total", "vue", *LAYERS]
    lines = []
    if md:
        lines.append("| " + " | ".join(head) + " |")
        lines.append("|" + "|".join("---:" if i else "---" for i in range(len(head))) + "|")
    else:
        lines.append(f"{'domaine':<11}" + "".join(f"{h:>7}" for h in head[1:]))
    for r in rows:
        mark = " ⚠" if limit and r["view_tokens"] > limit and r["domain"] != "core" else ""
        cells = [r["domain"] + mark, r["tokens"], r["view_tokens"], *(r["layers"][k] for k in LAYERS)]
        if md:
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
        else:
            lines.append(f"{cells[0]:<11}" + "".join(f"{c:>7}" for c in cells[1:]))
    tot = sum(r["tokens"] for r in rows)
    lines.append(("" if md else "") + f"\n{len(rows)} domaine(s), {tot} tokens au total (≈ {CHARS_PER_TOKEN} car./token) ; "
                 "« vue » = ViewModel + vue + contrôleur + leurs tests (les tests de modèle scindés, `*.model.js`, n'y comptent pas) — ce qu'un agent lit pour modifier une vue ; c'est ce que --check borne.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--md", action="store_true", help="tableau markdown")
    ap.add_argument("--json", action="store_true", help="sortie JSON")
    ap.add_argument("--check", type=int, metavar="TOKENS", help="échoue (1) si un domaine (core exclu) dépasse ce coût total")
    ap.add_argument("--domain", help="détail d'un seul domaine, fichier par fichier")
    a = ap.parse_args()
    rows = measure_all()
    if a.domain:
        r = next((x for x in rows if x["domain"] == a.domain), None)
        if not r:
            sys.exit(f"domaine inconnu : {a.domain}")
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=1)); return 0
        for f in sorted(r["files"], key=lambda x: -x["chars"]):
            print(f"{tokens(f['chars']):>7}  {f['layer']:<10} {f['file']}")
        print(f"{r['tokens']:>7}  total ({r['view_tokens']} pour la vue)")
        return 0
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1)); return 0
    print(table(rows, a.md, a.check))
    if a.check:
        # La garde porte sur le coût « vue » (ce qu'un agent lit pour modifier une vue : ViewModel + vue + contrôleur + leurs tests),
        # c'est l'objectif de RM2889. `core` est le socle, pas un domaine : il figure dans le tableau, pas dans la garde.
        over = [r for r in rows if r["view_tokens"] > a.check and r["domain"] != "core"]
        if over:
            print(f"\n✗ {len(over)} domaine(s) dont la vue coûte plus de {a.check} tokens : " + ", ".join(f"{r['domain']} (vue {r['view_tokens']}, total {r['tokens']})" for r in over), file=sys.stderr)
            return 1
        print(f"\n✓ aucune vue au-dessus de {a.check} tokens (coût ViewModel + vue + contrôleur + leurs tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
