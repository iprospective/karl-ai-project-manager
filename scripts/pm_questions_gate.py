#!/usr/bin/env python3
"""pm_questions_gate — pas de mise en prod avec une question en suspens (RM3238).

Une question ouverte dans le `.think.md` d'un ticket refusait déjà sa CLÔTURE (RM3053). Mais la clôture
arrive après la mise en prod : le ticket partait en production — statut et code — avec la question
pendante, et ne butait qu'au moment où la réponse ne pouvait plus rien changer. D'où cette garde, posée
là où la prod se décide :

- **statut** : entrer en `a_mep_prod` ou `en_mep` est refusé ; `a_mep` (préprod) avertit seulement ;
- **merge** vers une branche de prod (`main` / `master`) par `pm-mr merge` et `pm-promote`.

Les dépôts de DONNÉES PM (`*-core`) ne sont jamais concernés : leurs commits `pm(think): RM…` citent des
tickets sans rien mettre en production.

Le contournement existe (`--ignore-think` pour un statut, `--ignore-questions` pour un merge) et se
trace : une garde qu'on ne peut pas lever devient une garde qu'on contourne à la main, sans trace.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: branches de production — une MR qui y arrive met du code en prod
PROD_BRANCHES = ("main", "master")
#: statuts de MEP prod : refusés tant qu'une question est ouverte
GATED_STATUSES = ("a_mep_prod", "en_mep")
#: statut de MEP préprod : avertissement seulement — la préprod sert justement à trancher
WARN_STATUSES = ("a_mep",)
#: une question est close quand elle est tranchée (validée) ou écartée (invalidée)
_CLOSES = ("valide", "invalide")

# Deux façons dont un lot de commits nomme ses tickets (RM2809) :
#   « RM2857 : … »                       → commit direct
#   « Merge branch '2777-slug' into … »  → commit de merge, sans RM<id> dans le sujet
_RM_IN_TEXT = re.compile(r"\bRM(\d{3,6})\b")
_MERGE_BRANCH = re.compile(r"(?:Merge (?:branch|remote-tracking branch) '(?:[^']*/)?)(\d{3,6})-")
_BRANCH_ID = re.compile(r"^(?:[^/]+/)?(\d{3,6})-")


def ids_in_text(text: str) -> list:
    """RM<id> CITÉS dans des messages de commit, sans doublon, dans l'ordre d'apparition — lecture
    large, pour ANNOTER un lot (RM2809). Pour bloquer, `carried_ids` (RM3239)."""
    ids, seen = [], set()
    for rx in (_RM_IN_TEXT, _MERGE_BRANCH):
        for m in rx.finditer(text or ""):
            i = int(m.group(1))
            if i not in seen:
                seen.add(i)
                ids.append(i)
    return ids


# RM3239 — ce qu'un lot PORTE, par opposition à ce qu'il CITE. `ids_in_text` lit tout « RM<id> » du
# sujet ET du corps : juste pour annoter (RM2809), faux pour bloquer — « résorption RM3035 » dans un
# corps de commit bloquait une promotion où RM3035 n'était pour rien. On ne lit que les SUJETS, et
# seulement les formes qui désignent le ticket du commit :
_SUBJECT_RM = re.compile(r"^\W*RM(\d{3,6})\b")                                   # « RM3226 : … »
_SUBJECT_MERGE = re.compile(r"^Merge (?:branch|remote-tracking branch) '(?:[^']*/)?(\d{3,6})-")
_SUBJECT_INTO = re.compile(r"\binto '?(?:[^' ]*/)?(\d{3,6})-")                   # « … into 3227-slug »


def carried_ids(messages) -> list:
    """Tickets PORTÉS par des commits — lus dans la 1re ligne (sujet) de chaque message :
    sujet qui commence par `RM<id>`, merge de `<id>-…`, merge `into <id>-…`. Sans doublon."""
    ids, seen = [], set()
    for msg in messages or []:
        sujet = (msg or "").strip().split("\n", 1)[0]
        for rx in (_SUBJECT_RM, _SUBJECT_MERGE, _SUBJECT_INTO):
            m = rx.search(sujet)
            if m and int(m.group(1)) not in seen:
                seen.add(int(m.group(1)))
                ids.append(int(m.group(1)))
    return ids


def id_from_branch(name: str):
    """Le ticket d'une branche `<id>-slug` (tripwire #3), ou None."""
    m = _BRANCH_ID.match(name or "")
    return int(m.group(1)) if m else None


def is_prod_branch(name: str) -> bool:
    return (name or "").strip() in PROD_BRANCHES


def is_data_repo(project_path: str = None, local_repo=None) -> bool:
    """Dépôt de données PM ? Le dépôt local fait foi (`.mmi-pm/` réel à la racine, pm_git) ;
    sans lui (merge depuis une URL), la convention de nommage `*-core`."""
    if local_repo is not None:
        try:
            import pm_git
            return bool(pm_git.is_core_repo(Path(local_repo)))
        except Exception:  # noqa: BLE001 — on retombe sur le nom
            pass
    return bool(project_path) and str(project_path).rstrip("/").endswith("-core")


def open_questions_of_sheet(sheet) -> list:
    """[(Qnnn, texte)] des questions ouvertes d'une fiche — vide si pas de think."""
    import pm_think
    tp = pm_think.think_path(Path(sheet))
    if not tp.is_file():
        return []
    rows = ((pm_think.load(tp) or {}).get("question", {}) or {}).get("rows", [])
    out = []
    for r in rows:
        if r.get("closed") or r.get("state") in _CLOSES:
            continue
        cells = r.get("cells", [])
        out.append((r["id"], " ".join(str(cells[1] if len(cells) > 1 else "").split())))
    return out


def open_questions(rm_id, cfg=None) -> list:
    """Questions ouvertes d'un ticket, par son id. Ticket introuvable ⇒ vide (pas de faux blocage)."""
    if cfg is None:
        from pm_paths import PMConfig
        cfg = PMConfig.load()
    sheet = cfg.find_task(int(rm_id))
    return open_questions_of_sheet(sheet) if sheet else []


def blocked(ids, cfg=None) -> dict:
    """{rm_id: [(Qnnn, texte)]} pour les tickets du lot qui ont une question ouverte.

    Config PM illisible (pas de `.env`…) : on le DIT et on n'agit pas — une garde qui ferait planter
    l'outil qu'elle protège bloquerait aussi ce qui n'a aucune question."""
    ids = list(ids or [])
    if not ids:
        return {}
    if cfg is None:
        try:
            from pm_paths import PMConfig
            cfg = PMConfig.load()
        except (Exception, SystemExit) as e:  # noqa: BLE001 — PMConfig sort en sys.exit sans .env
            print(f"⚠ garde des questions (RM3238) non appliquée : config PM illisible ({e})", file=sys.stderr)
            return {}
    out = {}
    for i in ids:
        qs = open_questions(i, cfg)
        if qs:
            out[int(i)] = qs
    return out


def describe(blocked_map: dict, limit: int = 3) -> str:
    """Les tickets bloquants et leurs questions, une ligne par ticket."""
    lines = []
    for rm, qs in blocked_map.items():
        shown = " · ".join(f"{q} « {t[:80]} »" for q, t in qs[:limit])
        more = f" (+{len(qs) - limit})" if len(qs) > limit else ""
        lines.append(f"  RM{rm} : {shown}{more}")
    return "\n".join(lines)


def refusal(blocked_map: dict, action: str, override: str) -> str:
    return (f"ERREUR : {action} refusé — question(s) non tranchée(s) (RM3238) :\n"
            f"{describe(blocked_map)}\n"
            f"  → tranche-les (`mmi-pm task-think <id> --decide \"Qnnn : …\" --state valide` puis "
            f"`--set Qnnn --state valide|invalide`, ou ✅/❌ sur la fiche du cockpit),\n"
            f"    ou passe outre en connaissance de cause : {override}")
