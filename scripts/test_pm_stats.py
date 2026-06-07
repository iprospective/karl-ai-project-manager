#!/usr/bin/env python3
"""Tests de collect_stats (pm-stats.py) — RM1865.

Lancer : python3 scripts/test_pm_stats.py

Construit une arborescence projets synthétique en tempdir, instancie un
PMConfig pointant dessus (patterns réels lus dans pm.config.yml), puis vérifie
les compteurs renvoyés par collect_stats : entités par type, projets actifs
(≥1 ticket non `ferme`), tickets total / ouverts / en_cours.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from pm_paths import PMConfig

_spec = importlib.util.spec_from_file_location("pm_stats", str(_HERE / "pm-stats.py"))
stats_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stats_mod)

# Patterns de chemins réels (mêmes que ceux utilisés en prod).
_PATTERNS = yaml.safe_load((_HERE.parent / "pm.config.yml").read_text(encoding="utf-8"))["paths"]


# ── Helpers de construction d'arbo synthétique ──────────────────────────────
def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def mk_entity(root: Path, slug: str, etype: str | None):
    """Crée clients/<slug>/client/overview.md (avec ou sans `type`)."""
    fm = f"---\nslug: {slug}\n"
    if etype is not None:
        fm += f"type: {etype}\n"
    fm += "---\n\n# " + slug + "\n"
    _write(root / "clients" / slug / "client" / "overview.md", fm)


def mk_task(root: Path, entity: str, project: str, rm_id: int, status: str):
    fm = f"---\nredmine_id: {rm_id}\ntitle: t{rm_id}\nstatus: {status}\n---\n\n# t{rm_id}\n"
    _write(
        root / "clients" / entity / "projects" / project / "tasks"
        / f"RM{rm_id}_some-slug.md",
        fm,
    )


def build_tree(root: Path):
    # 3 entités : client, product, et une sans `type` (défaut → client)
    mk_entity(root, "acme", "client")
    mk_entity(root, "redmine", "product")
    mk_entity(root, "legacy", None)  # défaut client

    # acme : 2 projets, 1 actif (a_faire) + 1 inactif (tout fermé)
    mk_task(root, "acme", "alpha", 1, "a_faire")
    mk_task(root, "acme", "alpha", 2, "en_cours")
    mk_task(root, "acme", "beta", 3, "ferme")  # projet inactif

    # redmine : 1 projet actif (en_cours)
    mk_task(root, "redmine", "core", 4, "en_cours")
    mk_task(root, "redmine", "core", 5, "ferme")

    # legacy : 1 projet sans aucune tâche (inactif) + parasites ignorés
    (root / "clients" / "legacy" / "projects" / "empty" / "tasks").mkdir(parents=True)
    # .log.md et fichier non conforme : doivent être ignorés (pas comptés)
    _write(
        root / "clients" / "acme" / "projects" / "alpha" / "tasks"
        / "RM1_some-slug.log.md",
        "# log\n",
    )
    _write(
        root / "clients" / "acme" / "projects" / "alpha" / "tasks" / "README.md",
        "pas une tâche\n",
    )


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        build_tree(root)
        cfg = PMConfig(_HERE.parent, root, _PATTERNS)
        s = stats_mod.collect_stats(cfg)

        # Entités : 3 au total, 2 client (acme + legacy-défaut) + 1 product
        assert s["entities"]["total"] == 3, s["entities"]
        assert s["entities"]["by_type"] == {"client": 2, "product": 1}, s["entities"]["by_type"]

        # Projets : alpha, beta, core, empty = 4 ; actifs = alpha + core = 2
        assert s["projects"]["total"] == 4, s["projects"]
        assert s["projects"]["active"] == 2, s["projects"]

        # Tickets : 5 au total (le .log.md et README.md ignorés)
        assert s["tickets"]["total"] == 5, s["tickets"]
        # Ouverts (non ferme) : RM1(a_faire), RM2(en_cours), RM4(en_cours) = 3
        assert s["tickets"]["open"] == 3, s["tickets"]
        # en_cours : RM2, RM4 = 2
        assert s["tickets"]["en_cours"] == 2, s["tickets"]

    print("OK — test_pm_stats : tous les cas passent")


if __name__ == "__main__":
    run()
