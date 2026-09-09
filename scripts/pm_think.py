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
#: kind → (préfixe d'id, titre de section, en-tête de table)
KINDS = {
    "note":     ("N", "Notes — vrac verbatim, jamais reformulé",
                 ["#", "Date · auteur", "Verbatim", "État", "Traitée par"]),
    "question": ("Q", "Questions ouvertes",
                 ["#", "Question", "Bloque", "Urgence", "État"]),
    "decision": ("D", "Décisions",
                 ["#", "Objet", "État"]),
    "feature":  ("F", "Fonctionnalités à implémenter",
                 ["#", "Fonctionnalité", "Domaine", "Version", "Origine", "État", "Lot"]),
}
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


def _norm(s: str) -> str:
    s = " ".join(str(s or "").lower().split())
    return s.strip(" «»\"'“”‘’").strip()[:200]


def has_text(parsed: dict, kind: str, text: str) -> bool:
    """Déjà consigné ? (dédoublonnage des moissons automatiques)."""
    key = _norm(text)[:120]
    if not key:
        return False
    col = {"note": 2, "question": 1, "decision": 1, "feature": 1}[kind]
    for r in parsed.get(kind, {}).get("rows", []):
        if col >= len(r["cells"]):
            continue
        cell = _norm(r["cells"][col])
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
         ""]
    for kind in ("note", "question", "decision", "feature"):
        _, titre, hdr = KINDS[kind]
        L += [f"## {titre}", "", "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr), ""]
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
    who = f"{when} · {by}" + (f" · s:{str(sid)[:8]}" if sid else "")
    if kind == "note":
        return [rid, who, _clean(text), icon, _clean(dest)]
    if kind == "question":
        return [rid, _clean(text), _clean(bloque), _clean(urgence), icon]
    if kind == "decision":
        return [rid, _clean(text) + (f" ({when} · {by})" if by else ""), icon]
    return [rid, _clean(text), _clean(domaine), _clean(version), _clean(origine), icon, _clean(lot)]


def append(path, kind: str, text: str, *, prefix=None, rm_id=None, title="", **fields) -> str:
    """Ajoute une ligne normée ; crée le fichier depuis le gabarit s'il n'existe pas.
    Retourne l'id attribué. Ne committe pas (l'appelant décide)."""
    p = Path(path)
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
    sec = parsed[kind]
    pfx = prefix or KINDS[kind][0]
    rid = next_id(parsed, kind, pfx)
    cells = row_cells(kind, rid, text, **fields)
    # aligner sur la largeur réelle de la table du fichier (un think plus ancien peut différer)
    width = len(sec["header"])
    cells = (cells + [""] * width)[:width]
    lines = text_.splitlines()
    lines.insert(sec["line_end"], "| " + " | ".join(cells) + " |")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rid


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
            if dest and kind == "note" and len(cells) >= 5:
                cells[4] = _clean(dest)
            lines[r["line"]] = "| " + " | ".join(cells) + " |"
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


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
        new_fm = re.sub(r"(?ms)^think:\n(?:[ \t]+.*\n?)*", block, fm + "\n")
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


def render_merged(kind: str, thinks: dict) -> str:
    """Le bloc fusionné d'une rubrique : une table, ids `RM<id>-Xnnn`, colonne Ticket."""
    _, _, hdr = KINDS[kind]
    cols = [hdr[0], "Ticket"] + hdr[1:]
    L = [MERGE_BEGIN, "",
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
        for r in parsed.get("feature", {}).get("rows", []):
            c = (r["cells"] + [""] * 7)[:7]
            dom = c[2] or "Autre"; ver = c[3] or "—"
            groups.setdefault(dom, {}).setdefault(ver, []).append((rid, r, c))
    L = [MERGE_BEGIN, ""]
    if not groups:
        L.append("*(aucune fonctionnalité détaillée dans les `.think.md` des tickets)*")
    for dom in sorted(groups):
        L += [f"### {dom}", ""]
        for ver in sorted(groups[dom], key=lambda v: (v == "—", v)):
            L += [f"**{ver}**", "", "| # | Ticket | Fonctionnalité | Origine | État | Lot |", "|---|---|---|---|---|---|"]
            for rid, r, c in groups[dom][ver]:
                idc = f"~~RM{rid}-{c[0]}~~" if r["closed"] else f"RM{rid}-{c[0]}"
                L.append(f"| {idc} | RM{rid} | {c[1]} | {c[4]} | {c[5]} | {c[6]} |")
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
