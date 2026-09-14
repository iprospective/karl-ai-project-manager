"""Contrôleur du module release-watch : l'état des veilles de publication (RM3145, lot 4).

Le registre `releases.watch.yml` n'était visible que depuis la ligne de commande : on déclarait une
veille sans jamais pouvoir vérifier, depuis le cockpit, qu'elle était bien là et ce qu'elle attendait.

Ce contrôleur LIT le registre. Il n'interroge aucun dépôt : la veille elle-même est un travail de
l'ordonnanceur, et une route d'affichage qui partirait sur le réseau ferait attendre celui qui
regarde — et échouerait quand GitHub tousse, pour une information qui n'en dépend pas.
"""
from pathlib import Path

try:
    import yaml
except ImportError:                     # pragma: no cover
    yaml = None

REGISTRE = "releases.watch.yml"


def _racine() -> Path:
    """La racine du repo PM : ce fichier vit dans modules/<nom>/controllers/."""
    return Path(__file__).resolve().parent.parent.parent.parent


def etat(qs=None, payload=None, auth_ctx=None) -> dict:
    """{watches: [...], count} — ce qui est déclaré, et ce que chaque veille attend."""
    f = _racine() / REGISTRE
    if not f.is_file() or yaml is None:
        return {"watches": [], "count": 0, "registry": str(f),
                "error": "registre absent" if not f.is_file() else "PyYAML absent"}
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return {"watches": [], "count": 0, "registry": str(f), "error": f"registre illisible — {e}"}
    out = []
    for nom, v in (data.get("watches") or {}).items():
        v = v or {}
        out.append({
            "name": str(nom),
            "repo": str(v.get("repo") or ""),
            "min_version": str(v.get("min_version") or ""),
            "rm": str(v.get("rm") or "") or None,
            # Le « pourquoi » est ce qui manque le plus quand une alerte tombe des mois plus tard.
            "why": " ".join(str(v.get("why") or "").split()),
            "enabled": bool(v.get("enabled", True)),
        })
    out.sort(key=lambda x: x["name"])
    return {"watches": out, "count": len(out), "registry": str(f)}
