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
    return [(ok, lab) for _, _, ok, lab in _item_spans(text)]


def _item_spans(text):
    """Items réels avec leurs lignes : [(début, fin_exclue, coché, libellé), …].

    Base commune de `parse_items` et de `purge_decision` : pour savoir si retirer une
    section perd de la matière, il faut savoir quelles lignes les items OCCUPENT — tout
    le reste (prose, tableau, sous-liste sans case) serait perdu en silence.
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
        fin = i + 1
        for j in range(i + 1, len(lines)):
            ln = lines[j]
            if j in coupures or flags[j] or not ln.strip() or _H_RE.match(ln):
                break
            parts.append(ln.strip())
            fin = j + 1
        out.append((i, fin, m.group(2).lower() == "x", "\n".join(parts).strip()))
    return out


_MARKUP_RE = re.compile(r"[*`]")


def norm_label(label):
    """Clé de comparaison d'un item : espaces réduits, casse, markup et ponctuation finale ignorés.

    Sert UNIQUEMENT à décider si deux items sont « le même » de part et d'autre du
    miroir. Le libellé écrit reste celui de la source, jamais cette forme normalisée.

    Pourquoi ignorer le markup : le même critère saisi dans l'UI web de Redmine n'a ni
    gras ni backticks, et l'enveloppe à 95 colonnes du MD n'existe pas non plus côté
    Redmine. Sans cette normalisation, RM2882 lui-même — dont les deux côtés portent
    exactement les mêmes sept critères — sortait en « divergence croisée ». On ne
    touche PAS au souligné `_` : il vit dans les identifiants (`pm_task_md`).
    """
    txt = _MARKUP_RE.sub("", label or "")
    txt = re.sub(r"\s+", " ", txt).strip().lower()
    return txt.rstrip(".;,")


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


def adoptable_section(body):
    """La section de critères d'un corps de MD, PRÊTE à devenir la valeur du champ.

    Rend le texte normalisé des items réels, ou **None** s'il n'y en a aucun. Le
    rejeu à blanc de RM2882 sur tout le corpus a montré pourquoi ce filtre ne peut
    pas rester à l'appelant : des dizaines de tickets portent une section réduite à
    `- [ ] (à compléter)` (gabarit de `pm-task-add`) ou à des cases sans texte. Les
    adopter aurait poussé ces gabarits dans Redmine — précisément ce que RM2789 avait
    retiré de la comptabilité des critères.

    La normalisation (`parse_items` → `render_items`) rend aussi l'opération idempotente :
    une migration rejouée ne produit pas un diff d'enveloppe.
    """
    items = parse_items(extract_section(body) or "")
    return render_items(items) if items else None


# ── RM3241 : retirer la section de la description une fois reprise dans le CF ──────

def _section_bounds(body):
    """[(début, fin_exclue), …] des sections « Critères d'acceptation », titre compris.

    Mêmes bornes que `extract_sections` — c'est voulu : on retire exactement ce qu'on a
    lu et comparé, ni une ligne de plus, ni une de moins.
    """
    lines = (body or "").split("\n")
    flags = pm_markdown.code_line_flags(lines)
    out = []
    for i, line in enumerate(lines):
        if flags[i] or not CRITERIA_HEADING_RE.match(line):
            continue
        level, _ = _heading_level(line)
        end = len(lines)
        for j in range(i + 1, len(lines)):
            if flags[j]:
                continue
            lv, _ = _heading_level(lines[j])
            if lv is not None and lv <= level:
                end = j
                break
        out.append((i, end))
    return out


def strip_sections(body):
    """Le corps SANS ses sections « Critères d'acceptation » ; tout le reste intact.

    Seule retouche hors des sections : les lignes vides à la jointure sont ramenées à
    une, pour ne pas laisser un trou de trois lignes là où la section était.
    """
    bounds = _section_bounds(body)
    if not bounds:
        return body or ""
    lines = (body or "").split("\n")
    retire = set()
    for a, b in bounds:
        retire.update(range(a, b))
    garde = [ln for k, ln in enumerate(lines) if k not in retire]
    out = []
    for ln in garde:
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln)
    return "\n".join(out).strip("\n") + ("\n" if (body or "").endswith("\n") else "")


def _stray_lines(section):
    """Lignes non vides d'une section qui ne sont NI un item réel NI un gabarit."""
    lines = (section or "").split("\n")
    couvertes = set()
    for a, b, _, _ in _item_spans(section):
        couvertes.update(range(a, b))
    couvertes.update(i for i, _ in pm_markdown.placeholder_lines(section or ""))
    return [ln.strip() for k, ln in enumerate(lines)
            if ln.strip() and k not in couvertes and not _is_marker(ln)]


def _is_marker(line):
    """Le bandeau « ⚠ À définir » de `render_md` (RM2789) : ni un critère ni de la matière."""
    return line.lstrip().startswith(">") and "définir" in line.lower()


def purge_decision(cf_text, body):
    """Peut-on retirer les sections de critères de `body`, sachant que le CF porte `cf_text` ?

    Rend `(action, motifs)`, action ∈ {"rien", "retire", "garde"}. Fonction PURE.

    La règle de RM3241 telle qu'écrite — « aucun retrait si la coche diffère » — aurait
    laissé en place exactement les descriptions les plus trompeuses : sur les 15 tickets
    où les deux copies avaient déjà divergé (mesure du 2026-09-19), 11 l'étaient parce
    que le CF avait été COCHÉ et la description non (RM3173 : 4/4 dans le CF, 0/4 dans la
    description, ticket en MEP). La règle retenue est donc orientée :

    - le CF est vide                                 → garde (il n'y a pas de copie)
    - un item de la section manque au CF             → garde (on perdrait un critère)
    - un item coché dans la section, pas dans le CF  → garde (la description est EN AVANCE :
                                                       personne ne sait qui a raison)
    - la section porte du texte hors cases           → garde (prose, tableau : perdu sinon)
    - sinon — CF identique ou en avance              → retire
    """
    bounds = _section_bounds(body)
    if not bounds:
        return "rien", []
    cf_items = parse_items(cf_text or "")
    if not cf_items:
        # Rien de réel dans la section (bandeau « À définir », gabarit) : pas une copie,
        # pas un conflit — il n'y a simplement pas encore de critères.
        if not any(parse_items(t) or _stray_lines(t) for _, t in extract_sections(body)):
            return "rien", []
        return "garde", ["CF 33 vide — la section est la seule copie"]
    cf_by = {norm_label(lab): ok for ok, lab in cf_items}
    motifs, en_avance = [], 0
    for titre, texte in extract_sections(body):
        for ok, lab in parse_items(texte):
            key = norm_label(lab)
            court = lab.split("\n")[0][:70]
            if key not in cf_by:
                motifs.append(f"absent du CF : « {court} »")
            elif ok and not cf_by[key]:
                motifs.append(f"coché dans la description, pas dans le CF : « {court} »")
            elif cf_by[key] and not ok:
                en_avance += 1
        for ln in _stray_lines(texte):
            motifs.append(f"texte hors cases dans la section : « {ln[:70]} »")
    if motifs:
        return "garde", motifs
    return "retire", ([f"CF en avance de {en_avance} coche(s) sur la description"]
                      if en_avance else [])


def cf_text_of_issue(issue):
    """Le texte du CF 33 d'un ticket Redmine (dict de l'API), normalisé ; "" si absent."""
    import pm_cf_mirror
    cid = pm_cf_mirror.resolve_cf_id(ENV_VAR, CF_NAME)
    if cid is None:
        return ""
    for cf in (issue or {}).get("custom_fields") or []:
        if cf.get("id") == cid:
            return pm_cf_mirror.normalize_text(cf.get("value")) or ""
    return ""


def split_for_creation(description):
    """RM3241 — à la création, les critères partent dans le champ, pas dans la description.

    Rend `(description_sans_section, critères)` ; `critères` vaut None si la description
    ne porte pas de vrais critères — elle est alors rendue telle quelle, gabarit compris
    (c'est le bandeau « À définir » de RM2789 qui doit continuer de le signaler).
    On ne retire la section que si RIEN d'autre n'y vivait (même garde que la purge).
    """
    crit = adoptable_section(description)
    if not crit:
        return description, None
    action, _ = purge_decision(crit, description)
    if action != "retire":
        return description, None
    return strip_sections(description), crit
