#!/usr/bin/env python3
"""pm_acceptance — les critères d'acceptation, source unique de lecture (RM2882).

Le champ canonique est le **CF Redmine 33 « Critères d'acceptation »**, miroir
local dans le frontmatter `acceptance` — même contrat que le protocole de test
(CF 30, RM2229) et la proposition d'implémentation (CF 31) : cf. `pm_cf_mirror`.

Ce module existe pour une raison précise, mesurée par l'étude RM2882 : il y avait
**trois** parsers de checklist divergents dans l'outillage (`pm_markdown`,
`pm-task-status-update`, `karl-agent`), et la migration menaçait d'en ajouter un
quatrième. Tout ce qui lit des critères passe désormais par ici, et ce qui compte
les cases passe par `pm_markdown.checklist_lines` — un seul, pas deux.

## Lecture à double source (sans bascule)

`criteria_text()` rend le texte des critères **et sa provenance** :

- `acceptance` non vide  ⇒ le champ dédié fait foi (`source="acceptance"`) ;
- sinon la section « Critères d'acceptation » de la description (`source="description"`) ;
- sinon rien (`source=None`).

Un ticket non migré fonctionne donc exactement comme avant. Le jour où son champ
est rempli, lecture ET écriture basculent **ensemble** sur le champ : le piège
du § 4.2 de l'étude est là — changer la source de lecture sans changer celle de
l'écriture décale silencieusement les index de `--check N`.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_markdown
from pm_task_md import CRITERIA_HEADING_RE, CODE_FENCE_RE

ENV_VAR = "REDMINE_CF_ACCEPTANCE_ID"
CF_NAME = "Critères d'acceptation"
FM_KEY = "acceptance"

_H_RE = re.compile(r"^ {0,3}(#{1,6})\s*(.*)$")


def _heading_level(line):
    """(niveau, titre) si la ligne est un titre markdown, sinon (None, None)."""
    m = _H_RE.match(line)
    return (len(m.group(1)), m.group(2).strip()) if m else (None, None)


def extract_sections(body):
    """Toutes les sections « Critères d'acceptation » d'un corps : [(titre, texte), …].

    La section court jusqu'au prochain titre de niveau **inférieur ou égal** au sien —
    une section structurée en sous-parties ne doit pas être tronquée à son intro
    (même piège que `pm_cf_mirror.extract_implementation_section`, RM2560).

    Le titre doit **être** « Critères d'acceptation », pas le *contenir* : l'étude a
    relevé deux titres qui parlent des critères sans en être une section
    (« Génération de tests depuis critères d'acceptation »). L'ancrage en début de
    titre de `CRITERIA_HEADING_RE` suffit à les écarter.
    """
    lines = (body or "").split("\n")
    flags = pm_markdown.code_line_flags(lines)
    out = []
    for i, line in enumerate(lines):
        if flags[i] or not CRITERIA_HEADING_RE.match(line):
            continue
        level, titre = _heading_level(line)
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if flags[j]:
                continue
            lv, _ = _heading_level(lines[j])
            if lv is not None and lv <= level:
                end = j
                break
        out.append((titre, "\n".join(lines[i + 1:end]).strip()))
    return out


def extract_section(body):
    """La section de critères qui porte la matière, ou None.

    93 tickets ont plusieurs sections de ce titre, mais dans 90 cas la seconde est un
    **squelette fantôme** (`- [ ] (à compléter)`, séquelle du bug RM2540). On rend donc
    la première section qui contient un vrai item ; à défaut, la première tout court
    (pour que « section présente mais vide » se distingue de « pas de section »).
    """
    sections = extract_sections(body)
    if not sections:
        return None
    for _, txt in sections:
        if pm_markdown.real_checklist_lines(txt):
            return txt
    return sections[0][1]


def parse_items(text):
    """Items de critères : [(coché:bool, libellé:str), …], gabarits exclus.

    S'appuie sur `pm_markdown.real_checklist_lines` — donc blocs de code exclus et
    « (à compléter) » neutralisé, comme partout ailleurs dans l'outillage.

    Le libellé **rassemble les lignes de continuation** : l'outillage PM enveloppe ses
    descriptions à ~95 colonnes, et la majorité des critères réels tiennent sur deux ou
    trois lignes. S'arrêter à la première tronquerait le libellé — donc fausserait la
    comparaison des deux sources, et ferait PERDRE la fin du critère à la réécriture.
    Un libellé peut ainsi contenir des `\n` ; `norm_label` les réduit pour comparer.
    """
    lines = (text or "").split("\n")
    flags = pm_markdown.code_line_flags(lines)
    debuts = pm_markdown.real_checklist_lines(text or "")
    # bornes : la ligne d'un item court jusqu'au prochain item (réel OU gabarit),
    # une ligne vide, un titre, ou la fin du texte.
    coupures = {i for i, _ in pm_markdown.checklist_lines(text or "")}
    out = []
    for i, m in debuts:
        parts = [m.group(3)[1:].strip()]
        for j in range(i + 1, len(lines)):
            ln = lines[j]
            if j in coupures or flags[j] or not ln.strip() or _H_RE.match(ln):
                break
            parts.append(ln.strip())
        out.append((m.group(2).lower() == "x", "\n".join(parts).strip()))
    return out


def norm_label(label):
    """Clé de comparaison d'un item : espaces réduits, casse ignorée.

    Sert UNIQUEMENT à décider si deux items sont « le même » de part et d'autre du
    miroir. Le libellé écrit reste celui de la source, jamais cette forme normalisée.
    """
    return re.sub(r"\s+", " ", (label or "")).strip().lower()


def render_items(items):
    """Items → texte markdown (`- [ ] …` / `- [x] …`).

    Les lignes de continuation d'un libellé sont réindentées sous leur puce, pour que
    le texte relu par `parse_items` rende exactement les mêmes items (aller-retour
    stable — sans quoi une migration rejouée produirait un diff à chaque passage).
    """
    out = []
    for ok, lab in items:
        first, *rest = str(lab).split("\n")
        out.append("- [{}] {}".format("x" if ok else " ", first))
        out += ["      " + r for r in rest]
    return "\n".join(out)


def union(md_items, rm_items):
    """Union ordonnée des deux sources + divergences (§ 2 et § 5.2 de l'étude).

    Aucune source n'est systématiquement la bonne : sur 56 tickets porteurs de
    critères réels, 10 divergeaient, dans les deux sens. On ne choisit donc pas —
    on prend le MD comme ossature, on ajoute à la suite les items que seul Redmine
    porte, et on **signale** le reste.

    Rend `(items, divergences)` où `divergences` est une liste de dicts :
    `{"type": "only_redmine"|"only_md"|"check_differs", "label": …}`.
    Un ticket qui sort une divergence n'est PAS migré automatiquement.
    """
    md_by = {norm_label(l): (ok, l) for ok, l in md_items}
    rm_by = {norm_label(l): (ok, l) for ok, l in rm_items}
    items, diffs = list(md_items), []

    for key, (ok, lab) in rm_by.items():
        if key not in md_by:
            items.append((ok, lab))
            diffs.append({"type": "only_redmine", "label": lab})
    for key, (ok, lab) in md_by.items():
        if key not in rm_by:
            diffs.append({"type": "only_md", "label": lab})
        elif rm_by[key][0] != ok:
            diffs.append({"type": "check_differs", "label": lab})
    return items, diffs


def criteria_text(fm, body):
    """Le texte des critères d'un ticket et sa provenance : (texte, source).

    `source` vaut "acceptance", "description" ou None. C'est LA fonction de lecture :
    tout ce qui compte, affiche ou contrôle des critères doit passer par elle, sinon
    un ticket migré et un ticket non migré ne se lisent pas pareil.
    """
    champ = str((fm or {}).get(FM_KEY) or "").strip()
    if champ:
        return champ, FM_KEY
    section = extract_section(body)
    if section and section.strip():
        return section.strip(), "description"
    return "", None


def stray_checkboxes(body):
    """Cases à cocher situées HORS de la section de critères : [(libellé), …].

    Ce sont elles qui rendent une bascule de `--check N` dangereuse (§ 4.2) : tant
    qu'elles existent, le Nᵉ item du document n'est pas le Nᵉ critère. La migration
    s'en sert pour REFUSER de migrer un ticket automatiquement.
    """
    section = extract_section(body) or ""
    dans = {norm_label(lab) for _, lab in parse_items(section)}
    return [lab for _, lab in parse_items(body or "") if norm_label(lab) not in dans]
