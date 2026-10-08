#!/usr/bin/env python3
"""Source unique de l'énumération NORMS `priority` (RM3275).

Avant ce module, la table des priorités était recopiée en dur dans neuf
endroits — `pm_task_md.py`, `pm-task-sync.py`, `pm-project-bootstrap.py`,
`validate-task.py`, `priority.py`, `pm-dashboard.py`, `pm-task-list.py`,
`karl-mail-draft.py`, `karl-agent.py` — chacun avec sa propre forme : table
label→id, table id→label, ordre de tri, poids de scoring, regex de validation.
Ajouter une priorité demandait de trouver les neuf, et d'en oublier une les
faisait diverger en silence : un ticket créé avec la nouvelle valeur passait la
création puis disparaissait des tris, ou pesait zéro au classement.

Ici, une seule table, lue de `redmine.reference.yml :: priorities`, et tout le
reste s'en déduit :

- **l'ordre de force** suit l'**id Redmine croissant** (1 « Bas » → 5
  « Immédiat ») — pas une liste parallèle à tenir à jour ;
- **le poids** de scoring double à chaque cran (`0.5 · 2^rang`), ce qui
  reproduit exactement les poids historiques 0.5 / 1 / 2 / 4 et donne 8 à
  `immediat` sans décider de rien à la main.

Ajouter une priorité = une ligne dans `redmine.reference.yml`. Rien d'autre.

⚠ L'instance Redmine porte aussi « A définir » (id 24). Ce n'est pas un degré
d'urgence mais une absence de choix : elle reste hors de cette énumération, et
un ticket qui la porte côté Redmine est traité comme sans priorité connue.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Repli si `redmine.reference.yml` est absent ou illisible (PyYAML manquant,
# fichier tronqué) : l'outillage doit continuer à fonctionner en dégradé plutôt
# que de refuser toute priorité. Tenu identique au bloc du fichier.
_FALLBACK_IDS = {"low": 1, "normal": 2, "high": 3, "urgent": 4, "immediat": 5}

# Poids du cran le plus bas ; chaque cran suivant double.
_BASE_WEIGHT = 0.5

DEFAULT = "normal"

_CACHE = None


def _ids_raw():
    """{label: id} depuis la référence, repli en dur. Résultat mémoïsé."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    table = {}
    try:
        from redmine_utils import load_reference
        raw = (load_reference() or {}).get("priorities") or {}
        for label, pid in raw.items():
            label = str(label).strip().lower()
            try:
                table[label] = int(pid)
            except (TypeError, ValueError):
                continue  # entrée illisible : ignorée, le repli comblera
    except Exception:  # ImportError, yaml absent, fichier illisible
        table = {}
    _CACHE = table or dict(_FALLBACK_IDS)
    return _CACHE


def reset_cache():
    """Oublie la table mémoïsée — pour les tests, qui changent la référence."""
    global _CACHE
    _CACHE = None


def ids():
    """{label: id Redmine}, du plus faible au plus fort."""
    return dict(sorted(_ids_raw().items(), key=lambda kv: kv[1]))


def labels():
    """Labels du plus FAIBLE au plus FORT (`low` … `immediat`)."""
    return list(ids().keys())


def labels_by_force():
    """Labels du plus FORT au plus faible — l'ordre d'affichage d'une file."""
    return list(reversed(labels()))


def is_valid(label):
    return str(label or "").strip().lower() in _ids_raw()


def normalize(label, default=DEFAULT):
    """Label propre, ou `default` si la valeur est vide/inconnue."""
    s = str(label or "").strip().lower()
    return s if s in _ids_raw() else default


def to_id(label, default=None):
    """Label NORMS → id Redmine. `default` (ou l'id de `normal`) si inconnu."""
    table = _ids_raw()
    s = str(label or "").strip().lower()
    if s in table:
        return table[s]
    return default if default is not None else table.get(DEFAULT, 2)


def from_id(pid, default=DEFAULT):
    """Id Redmine → label NORMS. `default` si l'id n'est pas de l'énumération.

    Vaut notamment pour « A définir » (24), volontairement hors table.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return default
    for label, known in _ids_raw().items():
        if known == pid:
            return label
    return default


def rank(label):
    """Rang de force, 0 = le plus faible. -1 si la priorité est inconnue."""
    try:
        return labels().index(normalize(label, default=""))
    except ValueError:
        return -1


def sort_key(label):
    """Clé de tri d'une file de travail : le plus PRIORITAIRE en premier.

    Une priorité inconnue (ou absente) part en fin de liste plutôt que de
    s'intercaler au milieu — elle n'a pas été arbitrée, elle ne double personne.
    """
    r = rank(label)
    return len(labels()) - r if r >= 0 else 99


def weight(label):
    """Poids de scoring ROI — double à chaque cran, 0.5 au plus bas.

    Reproduit les poids historiques (low 0.5 · normal 1 · high 2 · urgent 4) et
    prolonge la série sans arbitrage manuel (immediat 8).
    """
    r = rank(label)
    if r < 0:
        r = rank(DEFAULT)
    return _BASE_WEIGHT * (2 ** r)


def weights():
    """{label: poids} — pour les scripts qui veulent la table entière."""
    return {label: weight(label) for label in labels()}


def choices_re():
    """Alternance pour une regex de validation d'argument (`low|normal|…`)."""
    return "|".join(labels())


if __name__ == "__main__":
    print("priorités NORMS (de la plus faible à la plus forte) :")
    for label in labels():
        print(f"  {label:<10} id={to_id(label):<3} rang={rank(label)} poids={weight(label)}")
