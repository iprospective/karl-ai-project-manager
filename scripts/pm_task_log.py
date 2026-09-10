"""pm_task_log — écrire dans le `.log.md` d'un ticket. Une seule fois. RM3085 (lot L5 de RM3015).

Le journal d'un ticket a UN format, que `pm-task-log.py` parse avec UNE expression :

    ## <horodatage> — <sujet>
    Tokens : N | Durée : N min

    <corps>

Il avait pourtant **sept** fonctions `append_log` distinctes (plus une écriture en ligne dans
`pm-task-status-update`), chacune reconstruisant l'en-tête à sa façon — et l'une d'elles,
`pm-env-expose`, écrivait sans la ligne `Tokens :`, donc une entrée que le parseur et la feuille de
temps ne comptaient pas. Rien ne le signalait : un journal mal formé se lit très bien à l'œil.

D'où ce module : le format est écrit ici, et les appelants disent seulement QUI écrit et QUOI.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def log_path(path) -> Path:
    """Le `.log.md` d'un ticket, à partir de sa fiche (ou du log lui-même — idempotent)."""
    p = Path(path)
    if p.name.endswith(".log.md"):
        return p
    return p.with_name(p.name[:-3] + ".log.md") if p.name.endswith(".md") else p


def entry(source: str, message: str, *, tokens: int = 0, minutes: int = 0, when=None) -> str:
    """Le bloc, tel que `pm-task-log.py` le parse. Pure — c'est elle qui porte le format."""
    ts = when or datetime.now().strftime("%Y-%m-%dT%H:%M")
    body = str(message or "").rstrip("\n")
    return f"\n## {ts} — {source}\nTokens : {int(tokens)} | Durée : {int(minutes)} min\n\n{body}\n"


def append(path, source: str, message: str, *, tokens: int = 0, minutes: int = 0, when=None) -> Path:
    """Ajoute une entrée au journal du ticket. Retourne le chemin écrit (pratique pour
    `pm_git.autocommit`, que l'appelant reste libre d'appeler ou non)."""
    target = log_path(path)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(entry(source, message, tokens=tokens, minutes=minutes, when=when))
    return target
