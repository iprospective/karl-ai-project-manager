#!/usr/bin/env python3
"""pm_notify — le fil de notifications de l'instance (RM2792, lot 2).

Trois canaux disaient déjà des choses, chacun dans son coin : le **journal** (`pm_log`) trace tout ce qui
se passe, le **worklog de session** (`pm-session-status notify`) retient ce qui est notable dans UNE
session, et l'**ordonnanceur** (`pm-scheduler`) garde l'historique de ses travaux. Aucun ne répond à la
question qu'on se pose vraiment en arrivant le matin : **qu'est-ce qui demande mon attention, là,
maintenant, toutes sources confondues ?**

Ce fil est cette réponse. Il ne remplace aucun des trois : il **agrège** et retient l'état.

  - Un journal est une TRACE : on y cherche après coup, il ne se lit pas en entier.
  - Un fil est une FILE : chaque entrée attend d'être lue, puis traitée, puis disparaît de la vue.

D'où ce que porte une entrée, et rien de plus : son **origine** (qui l'a émise), son **niveau**, son
horodatage, un message, et son **état** — `neuf` → `lu` → `traite`. L'identifiant est une **empreinte du
contenu** : ré-émettre la même notification ne la duplique pas, elle remonte. C'est l'anti-répétition
demandée, obtenue sans table de déduplication séparée.

Fichier : `<state_dir>/notifications.jsonl`, une ligne par entrée, réécrit à la marque (le volume se
compte en centaines, pas en millions). Jamais d'exception vers l'appelant : un fil qui casse ce qu'il
observe n'aide personne.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

NIVEAUX = ("info", "warn", "critical")
ETATS = ("neuf", "lu", "traite")
#: qui a le droit d'émettre — nommer les sources évite que chacune invente son vocabulaire
ORIGINES = ("scheduler", "session", "agent", "forge", "mail", "system")
FICHIER = "notifications.jsonl"
GARDE = 500                      # au-delà, les plus anciennes traitées sont oubliées

_LOCK = threading.Lock()


def _state_dir() -> Path:
    d = os.environ.get("PM_NOTIFY_DIR") or os.environ.get("KARL_AGENT_STATE_DIR")
    if d:
        return Path(d)
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pm_paths import PMConfig
        return Path(PMConfig.load().state_dir)
    except Exception:
        base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
        return Path(base) / "karl-agent"


def path() -> Path:
    return _state_dir() / FICHIER


def cle(origine: str, message: str, **champs) -> str:
    """L'empreinte d'une notification : même origine, même message, mêmes références → même entrée.
    C'est ce qui fait qu'un travail qui échoue toutes les heures ne produit pas 24 lignes par jour."""
    refs = "|".join(f"{k}={champs[k]}" for k in sorted(champs) if k in ("job", "rm", "sid", "ref"))
    return hashlib.sha256(f"{origine}\x1f{message}\x1f{refs}".encode("utf-8")).hexdigest()[:12]


def _lire() -> list:
    p = path()
    if not p.is_file():
        return []
    out = []
    try:
        for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                out.append(json.loads(ligne))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _ecrire(entrees: list) -> bool:
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entrees), encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        return False


def _taille(entrees: list) -> list:
    """Au-delà de la garde, on oublie les plus anciennes TRAITÉES — jamais une qui attend."""
    if len(entrees) <= GARDE:
        return entrees
    traitees = [e for e in entrees if e.get("etat") == "traite"]
    a_jeter = {id(e) for e in traitees[: len(entrees) - GARDE]}
    return [e for e in entrees if id(e) not in a_jeter]


def add(origine: str, niveau: str, message: str, **champs) -> dict | None:
    """Ajoute une notification, ou fait REMONTER celle qui dit déjà la même chose.

    Rend l'entrée (avec `repeats` incrémenté si elle existait), ou None si le fil n'a pas pu être écrit."""
    o = origine if origine in ORIGINES else "system"
    n = niveau if niveau in NIVEAUX else "info"
    maintenant = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    k = cle(o, str(message), **champs)
    with _LOCK:
        entrees = _lire()
        for e in entrees:
            if e.get("id") == k and e.get("etat") != "traite":
                # déjà dans la file et pas encore traitée : on ne la duplique pas, on la rafraîchit
                e["repeats"] = int(e.get("repeats", 1)) + 1
                e["last"] = maintenant
                e["level"] = n if NIVEAUX.index(n) > NIVEAUX.index(e.get("level", "info")) else e.get("level")
                _ecrire(_taille(entrees))
                return e
        entree = {"id": k, "ts": maintenant, "last": maintenant, "origin": o, "level": n,
                  "msg": str(message), "etat": "neuf", "repeats": 1}
        for cl, v in champs.items():
            if v is not None:
                try:
                    json.dumps(v); entree[cl] = v
                except TypeError:
                    entree[cl] = str(v)
        entrees.append(entree)
        return entree if _ecrire(_taille(entrees)) else None


def feed(etat=None, origine=None, niveau=None, limit: int = 100) -> list:
    """Le fil, du plus récent au plus ancien. `etat` accepte « ouvert » = tout sauf traité."""
    entrees = _lire()
    if etat == "ouvert":
        entrees = [e for e in entrees if e.get("etat") != "traite"]
    elif etat:
        entrees = [e for e in entrees if e.get("etat") == etat]
    if origine:
        voulues = {o.strip() for o in str(origine).split(",") if o.strip()}
        entrees = [e for e in entrees if e.get("origin") in voulues]
    if niveau:
        seuil = NIVEAUX.index(niveau) if niveau in NIVEAUX else 0
        entrees = [e for e in entrees if NIVEAUX.index(e.get("level", "info")) >= seuil]
    entrees.sort(key=lambda e: e.get("last") or e.get("ts") or "", reverse=True)
    return entrees[: max(1, min(int(limit or 100), 1000))]


def mark(ids, etat: str = "lu") -> int:
    """Marque des entrées. Rend le nombre réellement changé."""
    if etat not in ETATS:
        return 0
    voulus = {ids} if isinstance(ids, str) else set(ids or [])
    if not voulus:
        return 0
    with _LOCK:
        entrees = _lire()
        n = 0
        for e in entrees:
            if e.get("id") in voulus and e.get("etat") != etat:
                e["etat"] = etat
                e["marked"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
                n += 1
        if n:
            _ecrire(_taille(entrees))
        return n


def counts() -> dict:
    """Ce qu'on affiche en pastille : combien attendent, et au pire niveau."""
    ouverts = [e for e in _lire() if e.get("etat") != "traite"]
    par_niveau = {n: sum(1 for e in ouverts if e.get("level") == n) for n in NIVEAUX}
    pire = next((n for n in reversed(NIVEAUX) if par_niveau.get(n)), None)
    return {"open": len(ouverts), "neuf": sum(1 for e in ouverts if e.get("etat") == "neuf"),
            "by_level": par_niveau, "worst": pire}
