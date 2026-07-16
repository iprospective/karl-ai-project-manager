"""pm_scope — garde de PÉRIMÈTRE des outils PM mutants (RM2274).

Incident déclencheur (2026-07-14) : un agent a prédit un RM-id (tripwire #13,
RM2170) et les outils mutants ont écrit — lien, statut, notes — sur le ticket
d'un AUTRE projet. Les gardes existantes protègent le chemin du code
(RM2224/RM2240) ; celle-ci protège les écritures Redmine/MD.

Deux couches, appelées AVANT toute mutation :

  1. **Périmètre projet** (déterministe) : le projet du ticket ciblé (déduit du
     chemin de son MD `clients/<entité>/projects/<projet>/tasks/…`) doit être
     celui du workspace courant (`.mmi-pm` le plus proche du cwd). Mismatch →
     REFUS, sauf `--cross-project` explicite.
  2. **Registre de session** (filet, quand il n'y a PAS de contexte workspace) :
     l'id doit avoir été vu dans le worklog de la session Claude courante
     (créé / transitionné / commenté — auto-alimenté RM2068). Jamais vu →
     REFUS, sauf `--cross-project`. Hors session Claude (cron, humain) : pas
     de garde (aucun contexte à défendre).

Un refus n'est JAMAIS silencieux : message explicite avec les deux projets et
le geste pour passer outre en conscience.
"""
import json
import os
import re
import sys
from pathlib import Path

_RM_RE = re.compile(r"(?i)^rm?(\d+)$")


def _meta_project(mmi_pm: Path):
    """(client, slug) depuis le meta.yml d'un `.mmi-pm` — lecture minimale."""
    meta = mmi_pm / "meta.yml"
    if not meta.is_file():
        return None
    client = slug = None
    try:
        for line in meta.read_text(encoding="utf-8").splitlines():
            if line.startswith("client:"):
                client = line.split(":", 1)[1].strip()
            elif line.startswith("slug:"):
                slug = line.split(":", 1)[1].strip()
    except OSError:
        return None
    return (client, slug) if client and slug else None


def _clients_pattern(parts):
    try:
        i = parts.index("clients")
        if parts[i + 2] == "projects":
            return parts[i + 1], parts[i + 3]
    except (ValueError, IndexError):
        pass
    return None


def task_project(md_path: Path):
    """(entité, projet) du fichier tâche. Deux layouts (RM1949) :
    - arbo centrale `…/clients/<entité>/projects/<projet>/tasks/RM…` — motif
      cherché sur le chemin BRUT d'abord : la version centrale peut être un
      symlink vers le co-localisé, resolve() détruirait le motif ;
    - co-localisé `<workspace>/.mmi-pm/tasks/RM…` → meta.yml (client + slug)."""
    raw = Path(md_path)
    for candidate in (list(raw.parts), list(raw.resolve().parts)):
        hit = _clients_pattern(candidate)
        if hit:
            return hit
    for path in (raw, raw.resolve()):
        parts = list(path.parts)
        if ".mmi-pm" in parts:
            mm = Path(*parts[: parts.index(".mmi-pm") + 1])
            hit = _meta_project(mm)
            if hit:
                return hit
    return None


def workspace_project(start: Path | None = None):
    """(entité, projet) du workspace PM-tracké contenant `start` (défaut cwd),
    via le `.mmi-pm` le plus proche — symlink historique ou dossier co-localisé
    (RM1949). None hors workspace PM."""
    d = Path(start or Path.cwd()).resolve()
    for p in [d, *d.parents]:
        mm = p / ".mmi-pm"
        if not mm.exists():
            continue
        hit = _meta_project(mm)
        if hit:
            return hit
        # symlink vers l'arbo centrale : déduire du chemin résolu
        return _clients_pattern(list(mm.resolve().parts))
    return None


def _seen_in_session(rm_id) -> bool:
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        return True  # hors session Claude : pas de registre → pas de garde
    wl = Path.home() / ".claude" / "session-worklogs" / f"{sid}.json"
    try:
        data = json.loads(wl.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True  # registre illisible : ne jamais bloquer un humain pour ça
    items = data.get("items", data)
    refs = items.keys() if isinstance(items, dict) else \
        [it.get("ref", "") for it in items]
    for ref in refs:
        m = _RM_RE.match(str(ref))
        if m and int(m.group(1)) == int(rm_id):
            return True
    return False


def assert_task_scope(rm_id, md_path, cross_project: bool, tool: str) -> None:
    """À appeler AVANT toute mutation. Sort du process (exit 2) hors périmètre."""
    if cross_project:
        return
    ws = workspace_project()
    tp = task_project(md_path) if md_path is not None else None

    if ws and tp:
        # Mismatch TOLÉRÉ si le ticket a déjà été manipulé consciemment dans
        # cette session (créé avec --project explicite, transitionné…) — le
        # worklog RM2068 en fait foi. C'est la PREMIÈRE écriture sur un id
        # hors-projet jamais vu qui est l'empreinte de l'incident.
        if ws != tp and not _seen_in_session(rm_id):
            sys.exit(
                f"{tool}: REFUS (garde de périmètre RM2274) — RM{rm_id} appartient au "
                f"projet {tp[0]}/{tp[1]}, mais le workspace courant est {ws[0]}/{ws[1]}.\n"
                f"  → Mauvais id ? (tripwire #13 : ne jamais prédire un RM-id — "
                f"re-résous-le : ID=$(pm-task-add … --porcelain) / pm-task-list)\n"
                f"  → Écriture cross-projet voulue ? relance avec --cross-project."
            )
        return

    # Pas de contexte workspace (ou MD introuvable) : filet registre de session.
    if not _seen_in_session(rm_id):
        sys.exit(
            f"{tool}: REFUS (garde de périmètre RM2274) — RM{rm_id} n'a jamais été "
            f"vu dans cette session (ni créé, ni transitionné, ni listé) et le cwd "
            f"n'est pas un workspace PM-tracké.\n"
            f"  → Vérifie l'id (tripwire #13), ou relance avec --cross-project."
        )
