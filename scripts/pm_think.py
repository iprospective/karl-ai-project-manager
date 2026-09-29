"""pm_think — le fichier de réflexion d'un ticket (`RM<id>_<slug>.think.md`) et sa fusion
vers les fichiers du projet (RM3015 D003–D009, lot RM3053).

Trois journaux par ticket, une seule maille durable — le ticket :
  - `RM<id>_<slug>.md`        la FICHE : le contrat (quoi, critères, état) ;
  - `RM<id>_<slug>.log.md`    le JOURNAL : les événements (statuts, livraisons, ticks) ;
  - `RM<id>_<slug>.think.md`  la RÉFLEXION : notes verbatim (N), questions (Q), décisions et
                              conseils (D/C), fonctionnalités à implémenter (F).

Le `.think.md` est un registre en TABLES markdown, à la grammaire fixe — la même que les
fichiers projet `docs/cdc-questions.md`, `cdc-decisions.md`, `cdc-notes.md`, `cdc-features.md`
que `pm-think-merge` régénère depuis tous les tickets (ids préfixés `RM<id>-`). Le YAML pour
l'état (compteurs dans le frontmatter de la fiche), le markdown pour la pensée ; le script fait
le pont (RM3015-C004).

Stdlib seulement : `karl-agent.py` l'importe (serveur sans dépendances).

Piège levé ici (RM3015-C001, leçon RM2362) : les scripts retrouvaient la fiche par
`glob("RM<id>_*.md")` en n'excluant que `.log.md`. Un `.think.md` matche ce glob, et l'ordre
d'un glob n'est pas trié. `is_task_sheet()` est le seul test légitime — tout site qui
énumère des fiches passe par lui.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

THINK_SUFFIX = ".think.md"
LOG_SUFFIX = ".log.md"
#: La fiche, et rien d'autre : `RM<id>_<slug>.md` avec UN SEUL point. Exclut `.log.md`,
#: `.think.md`, `.reporting.yml` et tout suffixe frère à venir.
SHEET_RE = re.compile(r"^RM(\d+)_[^./]+\.md$")
THINK_RE = re.compile(r"^RM(\d+)_[^./]+\.think\.md$")

STATES = {"✅": "valide", "❌": "invalide", "🟡": "propose", "🕐": "attente", "⏸": "reserve"}
STATE_ICON = {v: k for k, v in STATES.items()}
#: RM3062 : ce que chaque rubrique est — et n'est pas (NORMS `session-tooling` § « Les quatre rubriques »)
LEGEND = {
    "note":     "N note — une information utile plus tard, verbatim (constat, idée, réserve, contrainte ; proposition pertinente de l'IA) ; jamais une demande immédiate, un accord, un accusé.",
    "question": "Q question — ce qui n'est pas tranché, ce que ça bloque, l'urgence, l'avis.",
    "decision": "D décision — ce que le demandeur demande de faire, pose ou tranche (réponse à une question ou non, ticketé ou non) ; C conseil — l'avis de l'agent, 🟡 jusqu'à l'arbitrage.",
    "feature":  "F fonctionnalité — une feature atomique qui donne lieu à un ticket, le complète, ou reste à faire.",
}
#: kind → (préfixe d'id, titre de section, en-tête de table)
#: RM3262 — chaque rubrique porte « Date · auteur » comme les notes : une question sans date ni
#: signataire ne se relit pas, et une décision portait les siennes COLLÉES dans son libellé.
#: La colonne TEXTE change de nom selon la rubrique (c'est elle qu'on lit partout) : `TEXTE_COL`.
#: RM3290 — « Origine » est généralisée aux quatre rubriques (elle n'existait que sur les
#: fonctionnalités). Elle porte d'où vient l'entrée : `ex-Q004` après une REQUALIFICATION, ou
#: `RM2881-Q004` après un déplacement (RM3258). Sans elle, requalifier revenait à supprimer puis
#: réécrire — on perdait l'id, la date et l'auteur, et la piste de ce qui avait été requalifié.
KINDS = {
    "note":     ("N", "Notes — vrac verbatim, jamais reformulé",
                 ["#", "Date · auteur", "Verbatim", "État", "Traitée par", "Origine"]),
    "question": ("Q", "Questions ouvertes",
                 ["#", "Date · auteur", "Question", "Bloque", "Urgence", "État", "Tranchée par", "Origine"]),
    "decision": ("D", "Décisions",
                 ["#", "Date · auteur", "Objet", "État", "Origine"]),
    "feature":  ("F", "Fonctionnalités à implémenter",
                 ["#", "Date · auteur", "Fonctionnalité", "Domaine", "Version", "Origine", "État", "Lot"]),
}
#: le nom de la colonne qui porte le texte de l'entrée, par rubrique
TEXTE_COL = {"note": "Verbatim", "question": "Question", "decision": "Objet", "feature": "Fonctionnalité"}
SIGNATURE_COL = "Date · auteur"
#: Un conseil de l'agent est une ligne de la section Décisions, préfixée C.
PREFIX_KIND = {"N": "note", "Q": "question", "D": "decision", "C": "decision", "F": "feature"}
SECTION_RE = {
    "note": re.compile(r"^##\s+(Notes|Vrac)\b", re.I),
    "question": re.compile(r"^##\s+Questions?\b", re.I),
    "decision": re.compile(r"^##\s+D[ée]cisions?\b", re.I),
    "feature": re.compile(r"^##\s+(Fonctionnalit[ée]s|Id[ée]es)\b", re.I),
}
MERGE_BEGIN = "<!-- think-merge:begin — bloc RÉGÉNÉRÉ par pm-think-merge, ne pas éditer entre les marqueurs -->"
MERGE_END = "<!-- think-merge:end -->"
#: fichiers projet régénérés (D004/D009) ; roadmap, help et cdc restent manuels
MERGED_FILES = {"question": "cdc-questions.md", "decision": "cdc-decisions.md",
                "note": "cdc-notes.md", "feature": "cdc-features.md"}
PROJECT_FILES = ("cdc.md", "cdc-questions.md", "cdc-decisions.md", "cdc-features.md",
                 "cdc-notes.md", "cdc-roadmap.md", "cdc-help.md")


# ── Reconnaissance des fichiers frères ───────────────────────────────────────

def is_task_sheet(path) -> bool:
    """La fiche d'un ticket — jamais un frère (`.log.md`, `.think.md`, …)."""
    return SHEET_RE.match(Path(path).name) is not None


def is_think(path) -> bool:
    return THINK_RE.match(Path(path).name) is not None


def sheet_of(path) -> Path:
    """La fiche à partir de n'importe quel frère (`RM12_x.think.md` → `RM12_x.md`)."""
    p = Path(path)
    stem = p.name
    for suf in (THINK_SUFFIX, LOG_SUFFIX, ".reporting.yml"):
        if stem.endswith(suf):
            return p.with_name(stem[: -len(suf)] + ".md")
    return p


def think_path(sheet) -> Path:
    p = Path(sheet)
    return p.with_name(p.name[:-3] + THINK_SUFFIX)


def rm_id_of(path):
    m = re.match(r"^RM(\d+)_", Path(path).name)
    return int(m.group(1)) if m else None


def siblings(sheet) -> list:
    """(fiche, log, think, reporting) — les frères d'une fiche, existants ou non."""
    p = Path(sheet); stem = p.name[:-3]
    return [p, p.with_name(stem + LOG_SUFFIX), p.with_name(stem + THINK_SUFFIX),
            p.with_name(stem + ".reporting.yml")]


def iter_sheets(tasks_dir):
    """Les fiches d'un dossier `tasks/`, triées — la SEULE façon de les énumérer."""
    d = Path(tasks_dir)
    if not d.is_dir():
        return []
    return sorted(f for f in d.glob("RM*.md") if is_task_sheet(f))


def find_sheet(tasks_dir, rm_id):
    for f in Path(tasks_dir).glob(f"RM{int(rm_id)}_*.md"):
        if is_task_sheet(f):
            return f
    return None


# ── Parseur ──────────────────────────────────────────────────────────────────

def _cells(line: str) -> list:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_sep(line: str) -> bool:
    return re.match(r"^\s*\|?\s*:?-{3,}", line) is not None


def state_of(text: str):
    for icon, name in STATES.items():
        if icon in (text or ""):
            return name
    return None


def parse(text: str) -> dict:
    """{kind: {"header": [...], "rows": [row…], "line_start": i, "line_end": j}} —
    `line_end` = index (exclusif) de la dernière ligne de la table, pour y insérer.
    row = {id, prefix, closed, state, cells, line}. Pure."""
    lines = text.splitlines()
    out = {}
    cur = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("## "):
            cur = next((k for k, rx in SECTION_RE.items() if rx.match(ln)), None)
            if cur and cur not in out:
                out[cur] = {"header": None, "rows": [], "line_start": i, "line_end": None, "heading": i}
            i += 1
            continue
        sec = out.get(cur) if cur else None
        if sec is not None and sec["header"] is None and ln.strip().startswith("|") \
                and i + 1 < len(lines) and _is_sep(lines[i + 1]):
            sec["header"] = _cells(ln)
            sec["line_start"] = i
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _cells(lines[i])
                raw = cells[0] if cells else ""
                closed = raw.startswith("~~")
                rid = raw.strip("~").strip().strip("*").strip()
                prefix = rid[:1].upper() if rid else ""
                st_col = None
                for j, h in enumerate(sec["header"]):
                    if re.search(r"[ée]tat", h, re.I):
                        st_col = j
                st_text = cells[st_col] if st_col is not None and st_col < len(cells) else " ".join(cells)
                sec["rows"].append({"id": rid, "prefix": prefix, "closed": closed,
                                    "state": state_of(st_text), "cells": cells, "line": i})
                i += 1
            sec["line_end"] = i
            continue
        i += 1
    return out


def load(path) -> dict:
    p = Path(path)
    return parse(p.read_text(encoding="utf-8")) if p.is_file() else {}


def counters(parsed: dict) -> dict:
    """Ce que le frontmatter de la fiche porte (D007) : l'état, jamais la pensée."""
    q = parsed.get("question", {}).get("rows", [])
    n = parsed.get("note", {}).get("rows", [])
    d = parsed.get("decision", {}).get("rows", [])
    f = parsed.get("feature", {}).get("rows", [])
    return {
        "questions_open": sum(1 for r in q if not r["closed"] and r["state"] not in ("valide", "invalide")),
        "notes_pending": sum(1 for r in n if not r["closed"] and r["state"] not in ("valide", "invalide")),
        "decisions": sum(1 for r in d if r["prefix"] == "D" and r["state"] == "valide"),
        "features": sum(1 for r in f if not r["closed"]),
    }


# ── signatures nominatives (RM3062, lot 3) ───────────────────────────────────
# Chaque N/Q/D/F est signée par son auteur NOMMÉ — une personne (Mathieu, Paul…) ou un modèle (Claude Opus 5,
# Qwen 3.8 27b…) — jamais un code. « M » / « A » restent acceptés en entrée et sont résolus à l'écriture.
_MODEL_NAMES = [(r"^claude-fable-(\d+)-(\d+)", "Claude Fable {0}.{1}"), (r"^claude-opus-(\d+)(?:-(\d+))?", "Claude Opus {0}.{1}"),
                (r"^claude-sonnet-(\d+)(?:-(\d+))?", "Claude Sonnet {0}.{1}"), (r"^claude-haiku-(\d+)-(\d+)", "Claude Haiku {0}.{1}")]


def model_label(model_id: str) -> str:
    """`claude-opus-5` → « Claude Opus 5 », `claude-fable-5-1` → « Claude Fable 5.1 », `qwen3.8:27b` → « Qwen3.8 27b »."""
    m = str(model_id or "").strip()
    if not m:
        return ""
    for rx, fmt in _MODEL_NAMES:
        h = re.match(rx, m)
        if h:
            maj, mi = h.group(1), (h.group(2) if h.lastindex and h.lastindex >= 2 else None)
            return fmt.format(maj, mi).rstrip(".None").replace(".None", "")
    return " ".join(w[:1].upper() + w[1:] for w in re.split(r"[\s:/_-]+", m.split("@")[0]) if w)


def _transcript_model(sid: str):
    stores = [Path(x).expanduser() for x in os.environ.get("PM_CLAUDE_STORES", str(Path.home() / ".claude" / "projects")).split(":") if x.strip()]
    tp = next((p for root in stores for p in root.glob(f"*/{sid}.jsonl")), None) if sid else None
    if not tp:
        return None
    try:
        with open(tp, "rb") as fh:
            fh.seek(0, 2); size = fh.tell(); fh.seek(max(0, size - 512 * 1024)); tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"type":"assistant"' in line and '"model"' in line:
            m = re.search(r'"model":"([^"]+)"', line)
            if m:
                return m.group(1)
    return None


def agent_signature(sid=None) -> str:
    """Le nom du modèle qui écrit : `PM_THINK_AUTHOR`, sinon le modèle du transcript de la session, sinon « Agent »."""
    env = os.environ.get("PM_THINK_AUTHOR")
    if env:
        return env
    return model_label(_transcript_model(sid or os.environ.get("CLAUDE_CODE_SESSION_ID") or "")) or "Agent"


def human_signature() -> str:
    """Le nom du demandeur : `PM_THINK_HUMAN`, sinon `PM_USER_NAME` du .env perso, sinon le manager IA de pm.config.yml, sinon « Demandeur »."""
    for var in ("PM_THINK_HUMAN", "PM_USER_NAME"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        import yaml
        from pm_paths import PMConfig
        cfg = PMConfig.load()
        data = yaml.safe_load((Path(cfg.pm_dir) / "pm.config.yml").read_text(encoding="utf-8")) or {}
        name = ((data.get("ia") or {}).get("default_manager") or {}).get("name")
        if name:
            return str(name).split(" ")[0]
    except Exception:
        pass
    return "Demandeur"


def signature(by, sid=None) -> str:
    """Résout un code d'auteur : M → demandeur nommé, A → modèle nommé ; un nom déjà explicite passe tel quel."""
    if by in (None, "", "A", "agent"):
        return agent_signature(sid)
    if by in ("M", "demandeur"):
        return human_signature()
    return str(by)


# ── propositions pertinentes de l'IA (RM3062, lot 3) ─────────────────────────
_PROPOSITION = re.compile(r"\b(je propose|je recommande|je suggère|ma préférence|je penche|à mon avis|il faudrait|on pourrait|on devrait|"
                          r"piste|recommandation|deux options|trois options|option [AB1-3]|le mieux serait|je conseille|attention :|à noter :|"
                          r"ce qui manque|risque)\b", re.I)


def proposition_pertinente(text: str):
    """(pertinente, extrait) pour un tour de l'IA : une proposition ou réflexion non posée en question outillée.
    Garde la phrase porteuse (jusqu'à 400 caractères), ignore le compte-rendu d'exécution."""
    s = " ".join(str(text or "").split())
    if len(s) < 60 or not _PROPOSITION.search(s):
        return False, ""
    phrases = re.split(r"(?<=[.!?])\s+", s)
    hit = next((i for i, ph in enumerate(phrases) if _PROPOSITION.search(ph)), 0)
    extrait = " ".join(phrases[hit:hit + 2])[:400]
    return True, extrait


# ── pertinence d'une note (RM3062, refondu RM3066) ──────────────────────────
# Une note ne sert QU'À une chose : retrouver plus tard ce qui n'a PAS été traité. Trois conditions
# CUMULATIVES (NORMS `session-tooling` § « Les quatre rubriques ») :
#   1. un RESTE À FAIRE — report explicite, manque, intention différée. Une contrainte (« doit être… »)
#      n'en est pas une : elle appartient aux décisions.
#   2. AUTO-SUFFISANTE — on comprend quoi reste à faire en lisant la note seule, hors du fil.
#   3. PAS DÉJÀ TRAITÉE — un bug a son ticket, une proposition tranchée a sa décision.
# Ceci en est l'approximation mécanique ; le jugement final reste à l'agent et au demandeur.

#: consigne explicite du demandeur — passe avant tout le reste
_EXPLICITE = re.compile(r"\b(notes? que|consigne[sz]? que|à noter|a noter|pense-bête|pense-bete|retiens|à retenir|a retenir)", re.I)
#: rejets DURS — quelle que soit la suite du texte
_COLLAGE = re.compile(r"(^|\s)(?:[\w.-]+@[\w.-]+:[~/][^\s]*[$#]|root@|Traceback \(most recent|^\s*File \"/)"
                      r"|This session is being continued|^\s*https?://\S+\s*$", re.I | re.M)
#: une réponse à une question outillée (« Q42 : … », « D114 : … », « q20 : oui ») est une DÉCISION, pas une note
_REPONSE_Q = re.compile(r"^\W*[QDCF]\s?0?\d{2,3}\s*[:.)]", re.I)
#: un ordre adressé à l'agent — même long, même s'il contient « il faudra ».
#: RM3281 : les formes qui passaient encore — « go faire 3108 », « ok, continuer sur … », et l'ordre
#: posé en FIN de note (« … . Consigne tout ça dans le ticket maintenant »), qui pilote le tour en
#: cours et ne dit rien de réutilisable. L'infinitif compte autant que l'impératif.
_VERBES_ORDRE = (r"fais|faire|fait|refais|refaire|prends|prendre|prend|étudie|etudie|étudier|etudier|chiffre|chiffrer|"
                 r"lance|lancer|relance|relancer|merge|merger|mergez|ferme|fermer|passe|passer|continue|continuer|"
                 r"reprends|reprendre|reprend|corrige|corriger|teste|tester|test|regarde|regarder|montre|montrer|"
                 r"liste|lister|crée|cree|créer|creer|ajoute|ajouter|mets|mettre|met|pousse|pousser|push|commit|"
                 r"committe|déploie|deploie|déployer|deployer|supprime|supprimer|vire|virer|consigne|consigner|"
                 r"consignes|note|noter|notes|traite|traiter|livre|livrer|réponds|reponds|répondre|repondre|donne|"
                 r"donner|envoie|envoyer|applique|appliquer|renomme|renommer|migre|migrer|analyse|analyser|documente|"
                 r"documenter|génère|genere|générer|generer|core update|attends|attendre|stoppe|stopper|arrête|arrete|arrêter|arreter")
_ORDRE = re.compile(r"^\W*(?:ok[,. ]|oui[,. ]|non[,. ]|go\b|vas-y|nickel|parfait|merci|super|top|c'est bon|bien reçu|bien recu)?\s*"
                    r"(?:peux-tu|pourrais-tu|je veux que tu|il faut que tu|merci de)\b"
                    r"|^\W*(?:ok[,. ]|oui[,. ]|non[,. ]|go|vas-y|nickel|parfait|merci|super|top)?[,.\s]*"
                    rf"(?:{_VERBES_ORDRE})\b", re.I)
#: le même ordre, mais en dernière phrase : « tout ça », « maintenant », « et enchaîne » — il pilote
#: le tour, il ne se relira pas. On ne regarde QUE la fin : au milieu d'un raisonnement, un impératif
#: peut appartenir à l'explication.
_ORDRE_FINAL = re.compile(rf"(?:^|[.!?;]\s+)(?:et\s+)?(?:{_VERBES_ORDRE})\b[^.!?]*"
                          r"(?:maintenant|tout (?:ç|c)a|tout cela|d'abord|stp|s'il te pla[îi]t)[^.!?]*[.!?]?\s*$", re.I)
#: le RESTE À FAIRE — report, manque, intention différée. PAS les contraintes (« doit », « devra ») : ce sont des décisions.
_DETTE = re.compile(r"\b(pour (?:l'|l’)instant|on verra|plus tard|à terme|a terme|en attendant|provisoire|temporaire|"
                    r"(?:un|second|deuxième|deuxieme) (?:premier )?temps|dans un premier temps|il faudra(?:it)?|"
                    r"faudra(?:it)? (?:aussi|bien|encore)|reste (?:à|a) faire|il (?:reste|manque)|ce qui manque|manquera|"
                    r"pas encore|(?:à|a) (?:définir|definir|revoir|trier|prévoir|prevoir|faire plus tard|reprendre)|"
                    r"faute de mieux|en dur pour|quick ?fix|bricol|rustine|dette technique|plus propre|un jour|"
                    r"on pourrait|on devrait|ce serait (?:bien|mieux)|il serait (?:bon|utile)|serait (?:bien|utile) de)", re.I)
_MOT = re.compile(r"[^\W\d_]{2,}", re.U)
#: RM3281 — le RÉFÉRENT. Une note doit dire DE QUOI elle parle : hors de sa conversation, « on verra
#: plus tard pour la suite, il faudra trancher » ne se rattache à rien et ne peut que faire du bruit.
#: Deux formes d'ancrage, l'une suffit : un identifiant qu'on peut chercher (ticket, chemin, terme
#: entre accents graves, nom composé, mot à majuscule interne), ou assez de mots PORTEURS.
_ANCRE = re.compile(r"\bRM\s?\d{3,5}\b|`[^`]+`|[\w.-]+\.(?:py|js|md|yml|yaml|json|sh|css|scss|service)\b"
                    r"|(?:^|\s)/[\w./-]{3,}|\b\w+[_-]\w+\b|\b\w+[a-zà-ÿ][A-ZÀ-Þ]\w*\b|\b[A-ZÀ-Þ][\w-]{2,}\b"
                    r"|(?:^|\s)-{1,2}[A-Za-z][\w-]*\b", re.U)   # une option de commande (« ssh -A », « --dry-run ») désigne quelque chose
_PORTEUR = re.compile(r"\b[^\W\d_]{6,}\b", re.U)
#: mots longs mais vides de référent : ils ne désignent rien qu'on puisse retrouver
_CREUX = {"faudrait", "pourrait", "devrait", "vraiment", "beaucoup", "toujours", "jamais", "quelque",
          "quelques", "certains", "certaines", "plusieurs", "pendant", "ensuite", "maintenant",
          "trancher", "vérifier", "verifier", "regarder", "attendre", "continuer", "terminer",
          "faudra", "instant", "reprendre", "laisser", "laisse", "commencer", "essayer", "penser"}


def _ancrage(s: str) -> bool:
    if _ANCRE.search(s):
        return True
    return len({m.group(0).lower() for m in _PORTEUR.finditer(s)} - _CREUX) >= 3


def note_pertinente(text: str):
    """(pertinente, motif). Approximation mécanique des trois conditions (RM3066) : rejets durs, puis un
    marqueur de reste à faire, puis assez de matière pour être auto-suffisante. Pure — testée sur le corpus réel."""
    s = " ".join(str(text or "").split())
    if not s:
        return False, "vide"
    if _COLLAGE.search(text or ""):
        return False, "collage (console, trace, compaction, url)"
    if _REPONSE_Q.match(s):
        return False, "réponse à une question — c'est une décision"
    if _EXPLICITE.search(s):                 # « note que … » est une consigne, « note ceci » un ordre : l'explicite passe d'abord
        return True, "explicite"
    if _ORDRE.search(s):
        return False, "ordre à l'agent"
    if _ORDRE_FINAL.search(s):
        return False, "ordre à l'agent (en fin de note) — pilote le tour, ne se relira pas"
    if not _DETTE.search(s):
        return False, "rien à faire plus tard (constat, contrainte, opinion)"
    if len(s) < 45 or len(_MOT.findall(s)) < 7:
        return False, "trop courte pour être auto-suffisante"
    if not _ancrage(s):
        return False, "aucun référent — rien à quoi la rattacher hors de sa conversation"
    return True, "dette"


def has_text_anywhere(parsed: dict, text: str) -> bool:
    """Ce texte est-il déjà consigné, dans N'IMPORTE quelle rubrique ? RM3090.

    Le classement d'un même tour peut changer (une remarque relue devient une question) : sans ce
    contrôle, la reprise l'ajouterait une seconde fois sous l'autre rubrique, et le carnet dirait
    deux fois la même chose. Reclasser est un geste explicite (`--set`), pas un effet de bord."""
    return any(has_text(parsed, kind, text) for kind in KINDS)


def _norm(s: str) -> str:
    s = " ".join(str(s or "").lower().split())
    return s.strip(" «»\"'“”‘’").strip()[:200]


def col_index(header, nom: str):
    """Index de la colonne `nom` dans cet en-tête, ou None. Insensible à la casse et aux accents
    d'usage : un `.think.md` ancien peut écrire « Etat » là où la grammaire dit « État »."""
    def norm(s):
        s = " ".join(str(s or "").split()).lower()
        for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ç", "c")):
            s = s.replace(a, b)
        return s
    cible = norm(nom)
    for i, h in enumerate(header or []):
        if norm(h) == cible:
            return i
    return None


def cell(sec: dict, row: dict, nom: str, defaut: str = "") -> str:
    """RM3262 — la cellule `nom` d'une ligne, LUE PAR LE NOM DE SA COLONNE.

    Les lecteurs disaient `cells[1]`, `c[3]`… : ajouter une colonne les cassait tous en silence,
    et un carnet non encore migré n'a pas la même largeur que la grammaire courante. Le nom, lui,
    ne bouge pas. Colonne absente ⇒ `defaut` : un vieux carnet rend une chaîne vide, jamais la
    valeur d'une colonne voisine."""
    i = col_index((sec or {}).get("header"), nom)
    cells = (row or {}).get("cells") or []
    return cells[i] if i is not None and i < len(cells) else defaut


def texte(sec: dict, row: dict, kind: str) -> str:
    """Le texte d'une entrée, quelle que soit la rubrique (et quelle que soit la largeur du carnet)."""
    val = cell(sec, row, TEXTE_COL[kind])
    if val:
        return val
    # carnet d'avant RM3262 (pas de colonne « Date · auteur ») : le texte est en 2ᵉ position
    cells = (row or {}).get("cells") or []
    return cells[1] if len(cells) > 1 else ""


def has_text(parsed: dict, kind: str, text: str) -> bool:
    """Déjà consigné ? (dédoublonnage des moissons automatiques)."""
    key = _norm(text)[:120]
    if not key:
        return False
    sec = parsed.get(kind, {})
    for r in sec.get("rows", []):
        cell_ = _norm(texte(sec, r, kind))
        if not cell_:
            continue
        cell = cell_
        # sous-chaîne (un verbatim consigné à la main porte ses guillemets, une moisson non) ;
        # un texte court doit matcher exactement pour ne pas absorber ses voisins
        if (key in cell) if len(key) >= 12 else (cell == key):
            return True
    return False


# ── Écriture ─────────────────────────────────────────────────────────────────

def gabarit(rm_id: int, title: str = "") -> str:
    t = f" — {title}" if title else ""
    L = [f"# RM{rm_id}{t} — Réflexion (`.think.md`)", "",
         "> Notes verbatim (N), questions (Q), décisions et conseils (D/C), fonctionnalités (F) du ticket.",
         "> La fiche `.md` est le contrat, le `.log.md` le journal d'événements ; ce fichier est le **pourquoi**.",
         "> États : ✅ validé · ❌ invalidé (motif) · 🟡 proposé (à arbitrer) · 🕐 en attente · ⏸ en réserve.",
         "> Ids locaux au ticket, trois chiffres, jamais réattribués ; préfixés `RM<id>-` à la fusion (`pm-think-merge`).",
         "> Chaque ligne est **signée** par son auteur nommé — une personne ou un modèle (RM3062).",
         ""]
    for kind in ("note", "question", "decision", "feature"):
        _, titre, hdr = KINDS[kind]
        L += [f"## {titre}", "", f"> {LEGEND[kind]}", "", "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr), ""]
    return "\n".join(L)


def _clean(s: str) -> str:
    return " ".join(str(s or "").replace("|", "/").split())


def next_id(parsed: dict, kind: str, prefix: str) -> str:
    n = 0
    for r in parsed.get(kind, {}).get("rows", []):
        m = re.match(rf"^{prefix}(\d+)", r["id"])
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:03d}"


def row_cells(kind: str, rid: str, text: str, *, by="A", state=None, when=None, sid=None,
              bloque="", urgence="", domaine="", version="", origine="", lot="", dest="") -> list:
    """Les cellules d'une ligne selon la grammaire de sa section."""
    when = when or datetime.now().strftime("%Y-%m-%d")
    icon = STATE_ICON.get(state, state) if state else ("🕐" if kind != "decision" else "🟡")
    by = signature(by, sid)                       # RM3062 : auteur nommé, jamais un code
    who = f"{when} · {by}" + (f" · s:{str(sid)[:8]}" if sid else "")
    if kind == "note":
        return [rid, who, _clean(text), icon, _clean(dest), _clean(origine)]
    if kind == "question":
        # RM3262 : « Tranchée par » est le miroir du « Traitée par » des notes — l'id de la
        # décision qui y répond, écrit quand elle arrive (`--dest`), sinon vide.
        return [rid, who, _clean(text), _clean(bloque), _clean(urgence), icon, _clean(dest), _clean(origine)]
    if kind == "decision":
        # RM3262 : la signature était COLLÉE au libellé (« … (2026-09-01 · Mathieu) ») — donc
        # recopiée dans chaque registre fusionné, et intriable. Elle a sa colonne.
        return [rid, who, _clean(text), icon, _clean(origine)]
    return [rid, who, _clean(text), _clean(domaine), _clean(version), _clean(origine), icon, _clean(lot)]


def _section_prete(p: Path, kind: str, rm_id=None, title=""):
    """Le fichier et la section existent (créés au besoin) ; rend (texte, parsed, sec)."""
    if not p.is_file():
        rid_ = rm_id or rm_id_of(p) or 0
        p.write_text(gabarit(rid_, title), encoding="utf-8")
    text_ = p.read_text(encoding="utf-8")
    parsed = parse(text_)
    if kind not in parsed or parsed[kind].get("header") is None:
        _, titre, hdr = KINDS[kind]
        block = ["", f"## {titre}", "", "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
        text_ = text_.rstrip("\n") + "\n" + "\n".join(block) + "\n"
        parsed = parse(text_)
    return text_, parsed, parsed[kind]


def _insere(p: Path, text_: str, sec: dict, cells: list) -> None:
    """Écrit `cells` en fin de table, alignées sur la largeur RÉELLE du fichier
    (un think plus ancien peut avoir une table plus étroite)."""
    width = len(sec["header"])
    cells = (cells + [""] * width)[:width]
    lines = text_.splitlines()
    lines.insert(sec["line_end"], "| " + " | ".join(cells) + " |")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append(path, kind: str, text: str, *, prefix=None, rm_id=None, title="", **fields) -> str:
    """Ajoute une ligne normée ; crée le fichier depuis le gabarit s'il n'existe pas.
    Retourne l'id attribué. Ne committe pas (l'appelant décide).

    RM3356 — les cellules sont posées PAR NOM sur l'en-tête réel du fichier. Un carnet pas encore
    migré (RM3262) a une table plus étroite : aligner les valeurs sur sa largeur, en position,
    écrivait la signature dans « Question » et le texte dans « Bloque ». Six entrées ont été
    écrites ainsi le jour du déploiement, entre la mise en place du code et la migration."""
    p = Path(path)
    text_, parsed, sec = _section_prete(p, kind, rm_id, title)
    rid = next_id(parsed, kind, prefix or KINDS[kind][0])
    _insere(p, text_, sec, _apparie(KINDS[kind][2], sec["header"], row_cells(kind, rid, text, **fields)))
    # RM3262 : une décision qui cite Qnnn REND cette question tranchée — on l'inscrit dans sa
    # colonne « Tranchée par ». Ici plutôt que dans le CLI : la moisson écrit aussi des décisions.
    if kind == "decision":
        for qid in questions_citees(text):
            set_dest(p, qid, rid)
    return rid


def _apparie(src_header: list, dst_header: list, cells: list) -> list:
    """RM3264 — les cellules d'une ligne, portées d'une table à l'autre PAR NOM DE COLONNE.

    Deux carnets n'ont pas forcément la même grammaire : celui d'un ticket ancien n'a pas encore
    « Date · auteur » (RM3262), celui d'un ticket neuf l'a. Recopier par position mettait alors le
    texte de la question dans la colonne de la date. Une colonne que la cible n'a pas est perdue
    sciemment ; une colonne qu'elle a en plus naît vide. En-têtes identiques (le cas courant) :
    la ligne passe telle quelle."""
    if not src_header or not dst_header or src_header == dst_header:
        return list(cells)
    val = {}
    for i, nom in enumerate(src_header):
        val[nom] = cells[i] if i < len(cells) else ""
    out = []
    for nom in dst_header:
        j = col_index(list(val), nom)
        out.append(list(val.values())[j] if j is not None else "")
    return out


def find_row(parsed: dict, rid: str):
    """(kind, row) de la ligne `rid`, ou (None, None). Pure."""
    cible = str(rid or "").strip().upper()
    for kind, sec in parsed.items():
        for r in sec["rows"]:
            if r["id"].upper() == cible:
                return kind, r
    return None, None


#: une cellule qui contient une signature (« 2026-09-21 · Mathieu · s:… ») là où on attend du texte
_SIGNATURE_CELL = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s·\s")


def reparer_decalage(path) -> list:
    """RM3356 — remet en place les lignes dont le texte a glissé d'une colonne. Rend les ids réparés.

    On ne répare QUE les lignes dont on est sûr : la colonne de signature est VIDE et la colonne du
    texte contient une signature. Le décalage est alors d'exactement un cran, et le remettre en
    place est sans ambiguïté. Toute autre forme est laissée telle quelle — une réparation qui
    devine abîmerait ce qu'elle prétend sauver. Idempotente."""
    p = Path(path)
    if not p.is_file():
        return []
    parsed = parse(p.read_text(encoding="utf-8"))
    lines = p.read_text(encoding="utf-8").splitlines()
    faits = []
    for kind, sec in parsed.items():
        if kind not in KINDS:
            continue
        i_sig = col_index(sec["header"], SIGNATURE_COL)
        i_txt = col_index(sec["header"], TEXTE_COL[kind])
        if i_sig is None or i_txt is None or i_txt <= i_sig:
            continue
        for r in sec["rows"]:
            cells = list(r["cells"])
            if i_txt >= len(cells) or (cells[i_sig] or "").strip():
                continue
            if not _SIGNATURE_CELL.match(cells[i_txt] or ""):
                continue
            # la cellule vide en trop saute : tout recule d'un cran, la signature rejoint sa colonne
            decale = (cells[:i_sig] + cells[i_sig + 1:] + [""] * len(sec["header"]))[:len(sec["header"])]
            # l'état, lui, a été PERDU à l'écriture (la ligne était tronquée) : on ne l'invente pas,
            # on rend la ligne à son état de départ — en attente, comme toute entrée non triée.
            i_etat = col_index(sec["header"], "État")
            if i_etat is not None and not (decale[i_etat] or "").strip():
                decale[i_etat] = STATE_ICON["attente"]
            lines[r["line"]] = "| " + " | ".join(decale) + " |"
            faits.append(r["id"])
    if faits:
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return faits


def move_row(src, rid: str, dst, *, rm_id=None, title=""):
    """RM3258 — DÉPLACE une entrée vers le carnet d'un autre ticket.

    Une question consignée au mauvais ticket bloque la clôture de celui-ci et manque à
    celui qu'elle concerne : la supprimer perdrait le verbatim, la réécrire perdrait sa
    date, son auteur et sa session. On déplace donc les CELLULES telles quelles ; seul
    l'id change, parce qu'il est local au ticket et jamais réattribué (RM3053).
    Rend (kind, ancien_id, nouvel_id) ou None si la ligne est introuvable.
    """
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("source et destination identiques")
    kind, row = find_row(load(src), rid)
    if not kind:
        return None
    src_header = (load(src).get(kind) or {}).get("header") or []
    text_, parsed, sec = _section_prete(dst, kind, rm_id, title)
    neuf = next_id(parsed, kind, row["prefix"] or KINDS[kind][0])
    cells = _apparie(src_header, sec["header"], row["cells"])
    cells[0] = (f"~~{neuf}~~" if row["closed"] else neuf)
    # RM3290 — une question TRANCHÉE qui déménage laisse sa décision derrière elle : la décision
    # appartient au ticket où l'arbitrage a eu lieu. Le lien devient donc inter-tickets
    # (« RM2316-D004 ») au lieu de pointer un « D004 » qui, dans le carnet d'arrivée, désigne
    # une autre décision — ou aucune.
    src_rm = rm_id_of(src)
    j = col_index(sec["header"], "Tranchée par")
    if kind == "question" and j is not None and j < len(cells):
        lien = str(cells[j] or "").strip()
        if lien and src_rm and not lien.upper().startswith("RM"):
            cells[j] = f"RM{src_rm}-{lien}"
    # l'origine dit d'où l'entrée vient, sans écraser une piste déjà présente (requalif + déplacement)
    o = col_index(sec["header"], "Origine")
    if o is not None:
        cells = (cells + [""] * (o + 1))[:max(len(cells), o + 1)]
        piste = f"RM{src_rm}-{row['id']}" if src_rm else str(row["id"])
        cells[o] = _clean((cells[o] + " " if cells[o] else "") + piste)
    _insere(dst, text_, sec, cells)
    remove_rows(src, [row["id"]])
    return kind, row["id"], neuf


def requalify_row(path, rid: str, new_kind: str, *, prefix=None, rm_id=None, title=""):
    """RM3290 — CHANGE UNE ENTRÉE DE RUBRIQUE, dans le même carnet.

    `move_row` change de TICKET, `requalify_row` change de RUBRIQUE : c'est le même geste dans
    l'autre dimension, et il repose sur le même appariement par nom de colonne.

    Pourquoi il manquait : une capture du harvest rangée en QUESTION bloque la clôture du ticket
    (`pm_questions_gate` refuse tant qu'une question est ouverte). Les deux seules sorties étaient
    mauvaises — `--delete` (on perd le verbatim, la date, l'auteur, et l'id, que la règle du carnet
    dit « jamais réattribué ») ou trancher une non-question (on écrit un arbitrage qui n'a jamais
    eu lieu). On requalifie donc, sans rien détruire.

    Ce qui est préservé : « Date · auteur » (même nom dans les quatre rubriques, donc reporté par
    `_apparie`), l'état, et le TEXTE — dont la colonne, elle, CHANGE de nom selon la rubrique
    (« Verbatim », « Question », « Objet », « Fonctionnalité ») : `_apparie` ne peut pas l'apparier,
    on le repose donc explicitement. L'origine (`ex-Q004`) part dans la colonne « Origine ».

    Rend (ancien_kind, ancien_id, nouveau_kind, nouveau_id), ou None si la ligne est introuvable.
    Lève ValueError si la rubrique d'arrivée est celle de départ (rien à faire, et le dire).
    """
    p = Path(path)
    if new_kind not in KINDS:
        raise ValueError(f"rubrique inconnue : {new_kind} (attendu : {', '.join(KINDS)})")
    parsed = load(p)
    kind, row = find_row(parsed, rid)
    if not kind:
        return None
    # le préfixe VISÉ, défaut de la rubrique compris : sans ça, D→C (même rubrique « decision »,
    # préfixe différent) serait refusé à tort, et Q→Q accepté à tort.
    vise = (prefix or KINDS[new_kind][0]).upper()
    actuel = (row["prefix"] or KINDS[kind][0]).upper()
    if kind == new_kind and vise == actuel:
        raise ValueError(f"{rid} est déjà une entrée de la rubrique « {new_kind} »")

    src_header = (parsed.get(kind) or {}).get("header") or []
    texte_ = texte(parsed[kind], row, kind)          # lu par le nom de SA colonne
    text_, parsed2, sec = _section_prete(p, new_kind, rm_id, title)
    neuf = next_id(parsed2, new_kind, vise)
    cells = _apparie(src_header, sec["header"], row["cells"])
    cells[0] = (f"~~{neuf}~~" if row["closed"] else neuf)

    col_txt = col_index(sec["header"], TEXTE_COL[new_kind])
    if col_txt is not None:
        cells = (cells + [""] * (col_txt + 1))[:max(len(cells), col_txt + 1)]
        cells[col_txt] = _clean(texte_)
    col_org = col_index(sec["header"], "Origine")
    if col_org is not None:
        cells = (cells + [""] * (col_org + 1))[:max(len(cells), col_org + 1)]
        # on n'écrase pas une origine déjà là : une entrée déplacée PUIS requalifiée garde sa piste
        cells[col_org] = _clean((cells[col_org] + " " if cells[col_org] else "") + f"ex-{row['id']}")
    # « Tranchée par » n'a de sens que pour une question : une question requalifiée en note
    # emporterait sinon un lien vers une décision dans une colonne qui ne veut plus dire ça.
    if kind == "question" and new_kind != "question":
        for mort in ("Tranchée par",):
            j = col_index(sec["header"], mort)
            if j is not None and j < len(cells):
                cells[j] = ""
    _insere(p, text_, sec, cells)
    remove_rows(p, [row["id"]])
    return kind, row["id"], new_kind, neuf


def remove_rows(path, ids) -> int:
    """Supprime des lignes pour de bon (RM3062 : « les notes pourries, tu peux les supprimer vraiment »). Retourne le nombre retiré."""
    p = Path(path)
    parsed = load(p)
    kill = {r["line"] for sec in parsed.values() for r in sec["rows"] if r["id"] in set(ids)}
    if not kill:
        return 0
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join(l for i, l in enumerate(lines) if i not in kill) + "\n", encoding="utf-8")
    return len(kill)


def set_state(path, rid: str, state: str, dest: str = "") -> bool:
    """Change l'état d'une ligne (✅ ❌ 🟡 🕐 ⏸) ; `dest` renseigne « traitée par » d'une note."""
    p = Path(path)
    parsed = load(p)
    icon = STATE_ICON.get(state, state)
    lines = p.read_text(encoding="utf-8").splitlines()
    for kind, sec in parsed.items():
        for r in sec["rows"]:
            if r["id"] != rid:
                continue
            cells = list(r["cells"])
            st_col = next((j for j, h in enumerate(sec["header"]) if re.search(r"[ée]tat", h, re.I)), None)
            if st_col is not None and st_col < len(cells):
                old = cells[st_col]
                cells[st_col] = icon + (old[1:] if old and old[0] in STATES else "")
                cells[st_col] = cells[st_col].strip() or icon
            # RM3262 : « Traitée par » (note) et « Tranchée par » (question) — par nom, et pour
            # les deux rubriques : trancher une question disait où, sans jamais l'écrire.
            if dest:
                dc = col_index(sec["header"], "Traitée par")
                if dc is None:
                    dc = col_index(sec["header"], "Tranchée par")
                if dc is not None and dc < len(cells):
                    cells[dc] = _clean(dest)
            lines[r["line"]] = "| " + " | ".join(cells) + " |"
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


def set_text(path, rid: str, texte: str) -> tuple:
    """AMENDE une ligne : remplace son texte, sans toucher à son état. Rend (ok, ancien_texte).

    Corriger trois mots d'une décision demandait jusqu'ici de l'invalider et d'en écrire une autre :
    le carnet se remplissait de doublons dont l'un est barré, et la décision qui fait foi devenait
    plus difficile à trouver — l'inverse de ce à quoi il sert (RM3161).

    L'état n'est PAS touché : corriger le texte d'une décision validée la laisse validée. C'est ce
    qui distingue un amendement d'un revirement — et le second a déjà son geste, `--state`.
    """
    p = Path(path)
    parsed = load(p)
    lines = p.read_text(encoding="utf-8").splitlines()
    for kind, sec in parsed.items():
        for r in sec["rows"]:
            if r["id"] != rid:
                continue
            cells = list(r["cells"])
            # RM3262 : la colonne du texte se trouve PAR SON NOM (« Verbatim », « Question »,
            # « Objet », « Fonctionnalité »), pas par une position qui dépend de la rubrique et de
            # l'ancienneté du carnet. `_clean` échappe les barres verticales : un texte qui en
            # contiendrait casserait la ligne du tableau, et donc la lecture de tout le carnet.
            col = col_index(sec["header"], TEXTE_COL[kind])
            if col is None:
                col = 2 if kind == "note" and len(cells) > 2 else 1
            if col >= len(cells):
                return False, ""
            ancien = cells[col]
            # Une décision d'AVANT RM3262 porte sa signature à la fin de son texte — « … (2026-09-14
            # · Mathieu) ». L'amendement corrige les mots, pas la paternité : effacer la signature
            # ferait perdre QUI a décidé. Depuis RM3262, elle est dans sa colonne et ce cas ne se
            # présente plus que sur les carnets pas encore migrés.
            m = re.search(r"\s*\((\d{4}-\d{2}-\d{2} · [^()]+)\)\s*$", ancien)
            cells[col] = _clean(texte) + (f" ({m.group(1)})" if m else "")
            lines[r["line"]] = "| " + " | ".join(cells) + " |"
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True, ancien
    return False, ""


def summary(parsed: dict, limit: int = 5) -> list:
    """Le résumé lu par le brief, la fiche et `pm-task-think --show` : compteurs, Q ouvertes, D récentes."""
    c = counters(parsed)
    L = [f"réflexion : {c['questions_open']} question(s) ouverte(s) · {c['decisions']} décision(s) validée(s) · "
         f"{c['features']} fonctionnalité(s) · {c['notes_pending']} note(s) à trier"]
    qs = [r for r in parsed.get("question", {}).get("rows", []) if not r["closed"] and r["state"] not in ("valide", "invalide")]
    for r in qs[:limit]:
        L.append(f"  ? {r['id']} {r['cells'][1][:110] if len(r['cells']) > 1 else ''}")
    ds = [r for r in parsed.get("decision", {}).get("rows", []) if r["prefix"] == "D"]
    for r in ds[-limit:]:
        L.append(f"  {STATE_ICON.get(r['state'], '·')} {r['id']} {r['cells'][1][:110] if len(r['cells']) > 1 else ''}")
    return L


# ── Compteurs dans le frontmatter de la fiche (D007) ─────────────────────────

FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def set_counters(sheet, cnt: dict) -> bool:
    """Pose `think: {…}` dans le frontmatter (sans toucher `updated`). Vrai si écrit."""
    p = Path(sheet)
    txt = p.read_text(encoding="utf-8")
    m = FM_RE.match(txt)
    if not m:
        return False
    fm = m.group(1)
    block = "think:\n" + "".join(f"  {k}: {v}\n" for k, v in cnt.items())
    if re.search(r"(?m)^think:\s*$", fm):
        # (?m) SANS (?s) : avec DOTALL, « . » matche aussi les sauts de ligne, si bien que
        # `[ \t]+.*` avalait TOUT le frontmatter situé après le bloc — test_protocol, tags,
        # reporting… disparaissaient en silence à chaque mise à jour des compteurs (RM3091).
        new_fm = re.sub(r"(?m)^think:\n(?:[ \t]+.*\n?)*", block, fm + "\n")
    else:                               # pas de bloc existant → ajout en fin de frontmatter
        new_fm = fm + "\n" + block
    new_fm = new_fm.rstrip("\n")
    if new_fm == fm:
        return False
    p.write_text("---\n" + new_fm + "\n---\n" + txt[m.end():], encoding="utf-8")
    return True


# ── Fusion vers les fichiers du projet (D004, D009) ──────────────────────────

def load_all(tasks_dir) -> dict:
    """{rm_id: parsed} pour tous les think d'un dossier tasks/ (ordre croissant)."""
    out = {}
    for f in sorted(Path(tasks_dir).glob("RM*" + THINK_SUFFIX)):
        rid = rm_id_of(f)
        if rid is not None and is_think(f):
            out[rid] = load(f)
    return dict(sorted(out.items()))


# ── Les questions d'un ticket, dans son CF Redmine 36 « Questions à trancher » (RM3116 → RM3226) ──
#
# Les questions gouvernent déjà des choses sérieuses — un ticket ne se ferme pas avec une question
# ouverte — mais elles ne se voyaient nulle part où l'on LIT un ticket. RM3116 les a régénérées dans la
# DESCRIPTION, entre marqueurs ; RM3226 les en sort vers leur champ dédié, même trajet que les critères
# d'acceptation (CF 33, RM2882) : la description change quand la demande change, les questions au fil
# de l'étude. Deux rythmes, deux contenants. Le `.think.md` reste la SOURCE ; le CF est une vue.
#
# Une question ne se résout pas en cochant une case, elle se résout par une RÉPONSE. Une question
# tranchée s'affiche donc cochée AVEC la décision qui l'a tranchée : sans elle, la trace mentirait par
# omission — on verrait que c'est réglé sans savoir comment.
QUESTIONS_CF_NAME = "Questions à trancher"
QUESTIONS_CF_ENV = "REDMINE_CF_QUESTIONS_ID"
#: marqueurs de l'ANCIENNE section de description (RM3116) — lus pour la retirer, plus jamais écrits
QUESTIONS_BEGIN = "<!-- questions:begin — section RÉGÉNÉRÉE depuis le .think.md, ne pas éditer entre les marqueurs -->"
QUESTIONS_END = "<!-- questions:end -->"
#: une question est CLOSE quand elle est tranchée (validée) ou écartée (invalidée) ; le reste attend
_Q_CLOSES = ("valide", "invalide")


def _decision_liee(parsed: dict, qid: str) -> str:
    """La décision qui a tranché cette question, s'il y en a une qui la nomme.

    Convention légère : une décision qui cite `Q001` dans son texte est la réponse à Q001. Rien n'oblige
    à la poser, mais quand elle existe elle est ce qu'un lecteur cherche. La DERNIÈRE qui la cite gagne :
    une réponse corrigée remplace la précédente."""
    trouvee = ""
    for r in (parsed.get("decision", {}) or {}).get("rows", []):
        texte = " ".join(str(c) for c in r.get("cells", [])[1:])
        if qid and re.search(rf"\b{re.escape(qid)}\b", texte) and r.get("state") != "invalide":
            trouvee = " ".join(texte.split())[:300]
    return trouvee


def decision_liante(parsed: dict, qid: str, dest: str = "") -> str:
    """RM3269 — CE QUI TRANCHE la question `qid`, ou "" si rien ne la tranche.

    Trois sources, de la plus explicite à la plus implicite :
      1. `dest` — la décision que l'appelant désigne à l'instant (`--dest D004`) ;
      2. la colonne « Tranchée par » de la question, si elle est déjà renseignée (RM3262) ;
      3. une décision NON invalidée qui cite `Qnnn` dans son texte (`_decision_liee`).

    Sert au garde-fou : trancher une question sans qu'aucune des trois n'existe, c'est clore le
    sujet en perdant le pourquoi — le défaut vécu sur RM2316-Q004, marquée ✅ sans aucune décision,
    dont il a fallu rouvrir l'antériorité trois jours plus tard pour reconstituer l'arbitrage.
    """
    if str(dest or "").strip():
        return str(dest).strip()
    sec = parsed.get("question", {}) or {}
    _, row = find_row(parsed, qid)
    if row is not None:
        deja = cell(sec, row, "Tranchée par").strip()
        if deja:
            return deja
    return _decision_liee(parsed, qid)


def questions_orphelines(parsed: dict) -> list:
    """RM3269 — les questions TRANCHÉES (✅) que rien ne relie à une décision.

    Le garde-fou n'agit qu'au moment de trancher : les carnets d'avant lui en portent déjà.
    Les rendre listables est ce qui permet de les reprendre au lieu de les découvrir par hasard.
    Rend [(qid, libellé), …]. Pure.
    """
    sec = parsed.get("question", {}) or {}
    out = []
    for r in sec.get("rows", []):
        if r.get("state") != "valide":
            continue                      # seul « tranchée » est concerné : écartée ≠ tranchée
        if decision_liante(parsed, r["id"]):
            continue
        out.append((r["id"], " ".join(str(texte(sec, r, "question")).split())))
    return out


def questions_text(parsed: dict) -> str:
    """Le contenu du CF 36 : une case par question, cochée si elle est tranchée. Jamais vide — un PUT
    de CF à vide EFFACE le champ, et « aucune question » est une information."""
    rows = (parsed.get("question", {}) or {}).get("rows", [])
    if not rows:
        return "*Aucune question consignée sur ce ticket.*"
    ouvertes = [r for r in rows if not r["closed"] and r["state"] not in _Q_CLOSES]
    L = [f"**{len(ouvertes)} ouverte(s) sur {len(rows)}** — un ticket ne se ferme pas avec une question "
         "en attente. Vue régénérée depuis le `.think.md` du ticket (`mmi-pm task-questions`) : "
         "trancher se fait là, pas ici.", ""]
    sec_q = parsed.get("question", {}) or {}
    for r in rows:
        libelle = " ".join(str(texte(sec_q, r, "question")).split())
        tranchee = r["closed"] or r["state"] in _Q_CLOSES
        ligne = f"- {'[x]' if tranchee else '[ ]'} **{r['id']}** — {libelle}"
        if tranchee:
            rep = _decision_liee(parsed, r["id"])
            ligne += f"  \n  → {rep}" if rep else "  \n  → *(tranchée ; la décision n'est pas reliée)*"
        L.append(ligne)
    return "\n".join(L)


def strip_questions(description: str) -> str:
    """La description SANS l'ancienne section RM3116 (marqueurs compris). Le reste n'est pas touché."""
    d = description or ""
    if QUESTIONS_BEGIN not in d or QUESTIONS_END not in d:
        return d
    a = d.index(QUESTIONS_BEGIN); b = d.index(QUESTIONS_END) + len(QUESTIONS_END)
    avant, apres = d[:a].rstrip(), d[b:].lstrip("\n")
    if not avant:
        return apres
    return avant + ("\n\n" + apres if apres.strip() else "\n")


def cochees_a_la_main(texte: str, parsed: dict) -> list:
    """Les questions cochées dans une vue (CF, ou ancienne section de description) alors que le think
    les dit encore ouvertes.

    On ne les décoche pas en silence : quelqu'un a voulu dire quelque chose. On les rapporte pour
    qu'elles soient tranchées là où ça compte — une coche n'est pas une réponse."""
    bloc = texte or ""
    if QUESTIONS_BEGIN in bloc:
        bloc = bloc.split(QUESTIONS_BEGIN, 1)[1].split(QUESTIONS_END, 1)[0]
    cochees = {m.group(1) for m in re.finditer(r"- \[x\]\s+\*\*(Q\d{3}[a-z]?)\*\*", bloc, re.I)}
    ouvertes = {r["id"] for r in (parsed.get("question", {}) or {}).get("rows", [])
                if not r["closed"] and r["state"] not in _Q_CLOSES}
    return sorted(cochees & ouvertes)


def cite_question(texte: str) -> bool:
    """Ce texte (une décision) répond-il à une question ? — `Q001` cité quelque part."""
    return bool(re.search(r"\bQ\d{3}[a-z]?\b", texte or ""))


def questions_citees(texte: str) -> list:
    """Les ids de questions cités par une décision, dans l'ordre. Pure."""
    return list(dict.fromkeys(re.findall(r"\bQ\d{3}[a-z]?\b", texte or "")))


def set_dest(path, rid: str, dest: str) -> bool:
    """RM3262 — renseigne « Traitée par » / « Tranchée par » SANS toucher à l'état.

    Le lien décision → question existait déjà, mais calculé à la lecture (`_decision_liee`) : la
    table, elle, restait muette. L'écrire quand la décision arrive rend le carnet lisible sans
    outil, et c'est le pendant du « Traitée par » des notes."""
    p = Path(path)
    parsed = load(p)
    lines = p.read_text(encoding="utf-8").splitlines()
    for sec in parsed.values():
        for r in sec["rows"]:
            if r["id"] != rid:
                continue
            col = col_index(sec["header"], "Tranchée par")
            if col is None:
                col = col_index(sec["header"], "Traitée par")
            if col is None:
                return False               # carnet pas encore migré : rien à écrire
            cells = (list(r["cells"]) + [""] * (col + 1))[:max(len(r["cells"]), col + 1)]
            cells[col] = _clean(dest)
            lines[r["line"]] = "| " + " | ".join(cells) + " |"
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


def render_merged(kind: str, thinks: dict) -> str:
    """Le bloc fusionné d'une rubrique : une table, ids `RM<id>-Xnnn`, colonne Ticket."""
    _, _, hdr = KINDS[kind]
    cols = [hdr[0], "Ticket"] + hdr[1:]
    L = [MERGE_BEGIN, "", f"> {LEGEND.get(kind, '')}", "",
         "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    n_open = n_total = 0
    for rid, parsed in thinks.items():
        sec = parsed.get(kind)
        if not sec:
            continue
        for r in sec["rows"]:
            cells = (r["cells"] + [""] * len(hdr))[:len(hdr)]
            idc = f"~~RM{rid}-{r['id']}~~" if r["closed"] else f"RM{rid}-{r['id']}"
            L.append("| " + " | ".join([idc, f"RM{rid}"] + cells[1:]) + " |")
            n_total += 1
            if not r["closed"] and r["state"] not in ("valide", "invalide"):
                n_open += 1
    if n_total == 0:
        L.append("| — | — | " + " | ".join(["*(aucune entrée : les tickets n'ont pas encore de `.think.md`)*"] + [""] * (len(cols) - 3)) + " |")
    L += ["", f"*{n_total} entrée(s), {n_open} en attente — régénéré le {datetime.now().strftime('%Y-%m-%d %H:%M')} par `pm-think-merge`.*",
          "", MERGE_END]
    return "\n".join(L)


def render_features_by_version(thinks: dict) -> str:
    """Les F des tickets groupées domaine × version (D009 : la version est une colonne,
    jamais une copie dans la roadmap)."""
    groups = {}
    for rid, parsed in thinks.items():
        sec = parsed.get("feature", {})
        for r in sec.get("rows", []):
            # RM3262 : par NOM — un carnet migré a une colonne de plus que l'ancien, et la version
            # se serait lue dans la case du domaine.
            c = {k: cell(sec, r, k) for k in ("Domaine", "Version", "Origine", "État", "Lot")}
            c["texte"] = texte(sec, r, "feature")
            dom = c["Domaine"] or "Autre"; ver = c["Version"] or "—"
            groups.setdefault(dom, {}).setdefault(ver, []).append((rid, r, c))
    L = [MERGE_BEGIN, ""]
    if not groups:
        L.append("*(aucune fonctionnalité détaillée dans les `.think.md` des tickets)*")
    for dom in sorted(groups):
        L += [f"### {dom}", ""]
        for ver in sorted(groups[dom], key=lambda v: (v == "—", v)):
            L += [f"**{ver}**", "", "| # | Ticket | Fonctionnalité | Origine | État | Lot |", "|---|---|---|---|---|---|"]
            for rid, r, c in groups[dom][ver]:
                idc = f"~~RM{rid}-{r['id']}~~" if r["closed"] else f"RM{rid}-{r['id']}"
                L.append(f"| {idc} | RM{rid} | {c['texte']} | {c['Origine']} | {c['État']} | {c['Lot']} |")
            L.append("")
    L += [f"*régénéré le {datetime.now().strftime('%Y-%m-%d %H:%M')} par `pm-think-merge`.*", "", MERGE_END]
    return "\n".join(L)


def splice(existing: str, block: str) -> str:
    """Remplace le bloc entre marqueurs ; l'ajoute en fin s'il n'y en a pas. Tout ce qui est
    HORS marqueurs (registre tenu à la main, préambule) est conservé — c'est ce qui permet de
    régénérer sans perdre les décisions consignées avant les think (RM3043)."""
    if MERGE_BEGIN in existing and MERGE_END in existing:
        a = existing.index(MERGE_BEGIN); b = existing.index(MERGE_END) + len(MERGE_END)
        return existing[:a] + block + existing[b:]
    return existing.rstrip("\n") + "\n\n" + block + "\n"


def project_file_template(name: str, projet: str) -> str:
    titres = {
        "cdc.md": ("CDC — projet `{p}`",
                   "Cahier des charges transversal du projet, tenu au fil de l'eau (modèle AtomBox RM2881, RM3015).\n"
                   "Les registres sont **régénérés** depuis les `.think.md` des tickets par `pm-think-merge` :\n"
                   "[questions](cdc-questions.md) · [décisions](cdc-decisions.md) · [fonctionnalités](cdc-features.md) · [notes](cdc-notes.md).\n"
                   "Manuels : [roadmap](cdc-roadmap.md) (un rôle par version) · [aide](cdc-help.md) (complétée par le LLM quand il le peut).\n"
                   "Les CDC **par ticket** (`cdc-rm<id>-*.md`) restent la référence de leur sujet.\n\n"
                   "## Périmètre\n\n_(à rédiger)_\n"),
        "cdc-roadmap.md": ("Roadmap — projet `{p}`",
                           "Une version = un **rôle** (ce qu'elle doit permettre), jamais une copie des fonctionnalités :\n"
                           "la version est une **colonne** de [cdc-features.md](cdc-features.md) (RM3015-D009). Tenue **sur demande**.\n\n"
                           "| Version | Rôle | État | Critère de passage |\n|---|---|---|---|\n| V0 | _(à définir)_ | 🕐 | |\n"),
        "cdc-help.md": ("Aide — projet `{p}`",
                        "Aide utilisateur du projet, **complétée par le LLM tout seul quand il le peut** (RM3015-D009) :\n"
                        "toute fonctionnalité livrée qui ne s'explique pas ici en langage d'utilisateur revient en question.\n\n"
                        "## Premiers pas\n\n_(à rédiger)_\n"),
        "cdc-questions.md": ("Questions ouvertes — projet `{p}`",
                             "Ce qui n'est pas tranché, ce que ça bloque. Bloc fusionné depuis les `.think.md` des tickets\n"
                             "(`pm-think-merge`) ; une question tranchée reste, barrée, avec sa décision.\n"),
        "cdc-decisions.md": ("Registre des décisions — projet `{p}`",
                             "Toutes les propositions, le conseil rendu (`C`), l'arbitrage (`D`) et son état ; une décision\n"
                             "invalidée reste avec son motif. Bloc fusionné depuis les `.think.md` des tickets (`pm-think-merge`).\n"),
        "cdc-notes.md": ("Notes — projet `{p}`",
                         "Remarques **verbatim**, tracées jusqu'à leur destination. Bloc fusionné depuis les tickets ;\n"
                         "**au-dessus des marqueurs : la boîte de réception des idées sans ticket** (une ligne `N`, puis elle migre\n"
                         "vers un ticket).\n\n| # | Date · auteur | Verbatim | État | Traitée par |\n|---|---|---|---|---|\n"),
        "cdc-features.md": ("Fonctionnalités — projet `{p}`",
                            "Par domaine et par version de la roadmap (RM3015-D004/D009). Registre par ticket tenu par\n"
                            "`pm-cdc-features` (`docs/cdc/fonctionnalites.yml`), détail par fonctionnalité fusionné depuis les `.think.md`.\n"),
    }
    t, body = titres[name]
    return f"# {t.format(p=projet)}\n\n{body}"
