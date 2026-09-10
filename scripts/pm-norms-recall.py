#!/usr/bin/env python3
"""pm-norms-recall — remet le KERNEL NORMS dans le contexte quand celui-ci vient d'être perdu (RM3071).

Une compaction remplace la conversation par un résumé : la tâche en cours y survit, les normes non. L'agent
continue alors avec le souvenir qu'il croit avoir des garde-fous, et les re-viole un par un — le garde-fou 15
le dit déjà de lui-même, mais il ne fait relire que lui, et seulement si on l'a lu.

Ce script imprime le KERNEL sur la sortie standard. Câblé en hook `SessionStart` de matcher `compact` (et
`resume`, qui perd le contexte de la même façon), sa sortie est versée au contexte de la session qui reprend :
la relecture n'est plus une consigne qu'on espère, c'est un fait.

  pm-norms-recall                 imprime le KERNEL à réinjecter, précédé de pourquoi il revient
  pm-norms-recall --path          n'imprime que le chemin retenu
  pm-norms-recall --plain         le KERNEL nu, sans l'en-tête de rappel
  pm-norms-recall --check         exit 1 si aucun KERNEL n'est trouvable (pour pm-doctor)
  pm-norms-recall --reason resume adapte la phrase d'en-tête à l'événement

Le KERNEL **runtime** (`norms/runtime/KERNEL.md`, réécriture dense pour LLM — RM3037) est préféré à la source
humaine (`norms/src/NORMS-KERNEL.md`) : même obligation, trois fois moins de tokens. Sans runtime, la source
fait l'affaire.
"""
import argparse
import sys
from pathlib import Path

PM_ROOT = Path(__file__).resolve().parents[1]
#: par ordre de préférence — le runtime dense d'abord, la source humaine ensuite
CANDIDATS = ("norms/runtime/KERNEL.md", "norms/src/NORMS-KERNEL.md")

RAISONS = {
    "compact": "La conversation vient d'être compactée : les normes ne sont plus dans le contexte, "
               "seul le résumé de la tâche l'est.",
    "resume":  "Cette session reprend une conversation antérieure : les normes ne sont pas dans le contexte.",
    "startup": "Début de session.",
}


def kernel_path(root: Path = PM_ROOT) -> Path:
    """Le KERNEL à relire, ou None si le dépôt n'en porte aucun."""
    for rel in CANDIDATS:
        p = root / rel
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def rappel(raison: str = "compact", plain: bool = False, root: Path = PM_ROOT) -> str:
    p = kernel_path(root)
    if not p:
        return ""
    corps = p.read_text(encoding="utf-8")
    if plain:
        return corps
    pourquoi = RAISONS.get(raison, RAISONS["compact"])
    return (f"# NORMS — relecture obligatoire ({raison})\n"
            f"{pourquoi} Le KERNEL est donc redonné ci-dessous EN ENTIER : il t'engage à nouveau, "
            f"immédiatement, sans que tu aies à le rouvrir. Source : `{p.relative_to(root)}`.\n\n"
            f"{corps}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", action="store_true", help="n'imprime que le chemin du KERNEL retenu")
    ap.add_argument("--plain", action="store_true", help="le KERNEL nu, sans l'en-tête de rappel")
    ap.add_argument("--check", action="store_true", help="exit 1 si aucun KERNEL n'est trouvable")
    ap.add_argument("--reason", default="compact", help="événement à l'origine du rappel (compact, resume…)")
    ap.add_argument("--root", type=Path, default=PM_ROOT, help="racine du dépôt PM (défaut : celui-ci)")
    a = ap.parse_args()

    p = kernel_path(a.root)
    if a.check:
        if not p:
            print("✗ aucun KERNEL trouvable : " + ", ".join(CANDIDATS), file=sys.stderr)
            return 1
        print(f"✓ KERNEL à réinjecter : {p.relative_to(a.root)}")
        return 0
    if not p:
        # un hook ne doit jamais casser la session qui reprend : muet et sans erreur
        return 0
    print(str(p) if a.path else rappel(a.reason, a.plain, a.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
