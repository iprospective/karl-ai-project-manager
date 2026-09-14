#!/usr/bin/env python3
"""pm_bus — le journal des événements MÉTIER de PM (RM3145, lot 2).

⚠ À ne pas confondre avec `pm_events`, qui porte déjà un autre sens : PRÉVENIR LE COCKPIT qu'une
donnée a changé (RM3006), pour qu'il rafraîchisse sans attendre son tick. Ce module-ci ne prévient
personne dans l'instant : il retient des FAITS auxquels des modules réagiront. Deux noms proches pour
deux natures différentes, et c'est justement pourquoi celui-ci ne s'appelle pas `pm_events`.

Un bus existe déjà, et il ne fait pas ce travail. `_EventBus` (RM3006, dans karl-agent) est un bus
d'**affichage** : il publie des sujets sans charge utile pour réveiller les connexions SSE, en
mémoire du serveur, et personne ne peut s'y abonner. Ce qu'un module attend est autre chose : un
événement **nommé et porteur** — « le statut de RM3145 est passé de a_faire à en_cours » — auquel il
réagit en faisant quelque chose. Confondre les deux serait une erreur : l'un doit être immédiat et
volatile, l'autre durable et rejouable.

**Pourquoi un journal, et pas des appels directs.** Les émetteurs de PM sont des processus COURTS :
`pm-task-status-update` s'exécute et meurt. Un bus en mémoire ne verrait jamais les abonnés. Restait
à choisir qui exécute :

  * l'émetteur lui-même — simple, mais le geste le plus fréquent de PM ralentirait à proportion des
    modules installés, et se coupleraient à eux ceux qui n'ont rien demandé ;
  * l'émetteur DÉPOSE, un drain exécute — c'est retenu. `pm-scheduler` tourne déjà : pas de minuterie
    de plus (RM3013), l'émetteur ne sait même pas qui écoute, et un événement non traité n'est pas
    perdu. Prix assumé : la réaction attend un tour d'ordonnanceur. Ce qui doit être instantané
    (rafraîchir un écran) passe par le bus SSE, qui fait déjà exactement cela.

**Le nom d'un événement est un contrat** : un module s'y abonne, le renommer casse des modules. Les
noms se déclarent donc ici, comme les natures de `provides` se déclarent dans `pm_modules`.

Fichier : `<state_dir>/events.jsonl`, une ligne par événement. Jamais d'exception vers l'appelant —
un journal qui casse ce qu'il observe n'aide personne (même règle que `pm_notify`).
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

FICHIER = "bus.jsonl"
#: au-delà, les plus anciens DRAINÉS sont oubliés — jamais un qui attend encore.
GARDE = 2000

#: Les événements que le noyau émet. Un nom absent d'ici est refusé : mieux vaut un émetteur qui
#: échoue à la première exécution qu'un abonné qui attend en silence un nom mal orthographié.
EVENEMENTS = {
    "task.status.changed": "le statut d'un ticket a changé (rm_id, from, to)",
    "task.created": "un ticket a été créé (rm_id, title)",
    "task.closed": "un ticket a été fermé (rm_id, close_reason)",
    "mr.created": "une merge request a été ouverte (url, source, target)",
    "mr.merged": "une merge request a été fusionnée (url, target)",
    "session.idle": "une session a fini son tour et attend une suite (sid)",
    "notification.added": "une notification est entrée dans le fil (id, level)",
    "provider.changed": "un fournisseur a été déclaré, modifié ou retiré (axis, type)",
    "module.enabled": "un module a été activé (name)",
    "module.disabled": "un module a été désactivé (name)",
}

_LOCK = threading.Lock()


def _state_dir() -> Path:
    d = os.environ.get("PM_BUS_DIR")
    if d:
        return Path(os.path.expanduser(d))
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pm_stores
        root = pm_stores.state_root()
        if root:
            return root
    except Exception:      # noqa: BLE001
        pass
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "karl-agent"


def path() -> Path:
    return _state_dir() / FICHIER


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
    """Comme le fil : on n'oublie que ce qui est DRAINÉ, quitte à dépasser. Jeter un événement qui
    attend, c'est faire disparaître une réaction que quelqu'un attend."""
    if len(entrees) <= GARDE:
        return entrees
    drainés = [e for e in entrees if e.get("drained")]
    a_jeter = {id(e) for e in drainés[: len(entrees) - GARDE]}
    return [e for e in entrees if id(e) not in a_jeter]


def publish(name: str, source: str | None = None, **payload) -> dict | None:
    """Dépose un événement. Rend l'entrée, ou None si le nom est inconnu ou le journal non écrivable.

    L'émetteur ne sait pas qui écoute, et n'attend personne : c'est ce qui fait qu'ajouter un module
    ne ralentit pas les gestes de PM."""
    if name not in EVENEMENTS:
        return None
    maintenant = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    entree = {"id": uuid.uuid4().hex[:12], "name": name, "ts": maintenant,
              "source": str(source or "")[:80], "drained": False, "payload": {}}
    for k, v in payload.items():
        if v is None:
            continue
        try:
            json.dumps(v)
            entree["payload"][k] = v
        except TypeError:
            entree["payload"][k] = str(v)
    with _LOCK:
        entrees = _lire()
        entrees.append(entree)
        return entree if _ecrire(_taille(entrees)) else None


def pending(limit: int = 200, name: str | None = None) -> list:
    """Ce qui attend d'être drainé, du plus ancien au plus récent — l'ordre des faits."""
    out = [e for e in _lire() if not e.get("drained")]
    if name:
        out = [e for e in out if e.get("name") == name]
    out.sort(key=lambda e: e.get("ts") or "")
    return out[: max(1, min(int(limit or 200), 2000))]


def mark_drained(ids, erreur: str | None = None) -> int:
    """Marque des événements traités. `erreur` retient CE QUI a échoué sans rejouer indéfiniment :
    un abonné cassé rejouerait en boucle, et son échec finirait par noyer le journal."""
    voulus = {ids} if isinstance(ids, str) else set(ids or [])
    if not voulus:
        return 0
    maintenant = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with _LOCK:
        entrees = _lire()
        n = 0
        for e in entrees:
            if e.get("id") in voulus and not e.get("drained"):
                e["drained"] = maintenant
                if erreur:
                    e["error"] = str(erreur)[:300]
                n += 1
        if n:
            _ecrire(_taille(entrees))
        return n


def counts() -> dict:
    entrees = _lire()
    attente = [e for e in entrees if not e.get("drained")]
    return {"total": len(entrees), "pending": len(attente),
            "errors": sum(1 for e in entrees if e.get("error")),
            "by_name": {n: sum(1 for e in attente if e.get("name") == n)
                        for n in sorted({e.get("name") for e in attente if e.get("name")})}}
