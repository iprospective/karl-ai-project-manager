#!/usr/bin/env python3
"""Utilitaires markdown partagés par l'outillage PM (RM2540).

Raison d'être : une description de ticket cite parfois du markdown en exemple —
un gabarit fautif qu'on décrit, une sortie attendue. Les cases à cocher qui s'y
trouvent ne sont PAS des critères d'acceptation. Les traiter comme tels a deux
conséquences vécues : `--check-all` coche la citation (elle devient fausse), et
le contrôle « critères non cochés » de la livraison compte des cases que
personne ne peut cocher.

`checklist_lines()` est la source unique de vérité : elle rend les lignes de
checklist réelles, blocs de code exclus.

RM2789 — deux ajouts, sur le même principe « ce qui ressemble à X n'est pas X » :

  · `is_placeholder()` — « (à compléter) » n'est PAS un critère d'acceptation.
    Posé en case à cocher, il bloquait la livraison sans que personne puisse le
    cocher, et le seul recours (`--allow-unchecked`) désactivait le garde-fou
    pour les VRAIS critères aussi : le contournement était plus grossier que le
    problème.
  · `unwrap()` — l'outillage compose du markdown enveloppé à ~95 colonnes ;
    Redmine rend chaque retour à la ligne comme un `<br>`, donc le texte arrive
    haché. Ce qui est lisible dans un fichier source ne l'est pas dans un
    navigateur, qui sait envelopper tout seul.
"""
import re
from pathlib import Path

import yaml

CHECK_LINE_RE = re.compile(r"^(\s*[-*]\s*\[)([ xX])(\].*)$")
FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
LIST_ITEM_RE = re.compile(r"^ {0,3}([-*+]|\d+[.)])\s")
INDENTED_RE = re.compile(r"^(?: {4,}|\t)")
# Un item de checklist qui ne désigne aucun travail : gabarit de création, reste
# de rédaction. Il ne compte ni comme critère à cocher ni comme critère manquant.
PLACEHOLDER_RE = re.compile(r"^\W*(à compléter|a completer|à définir|a definir|tbd|todo)\W*$", re.I)
# Lignes dont le retour à la ligne PORTE du sens : les dé-envelopper les casserait.
STRUCT_RE = re.compile(r"^ {0,3}(#{1,6} |>|\||[-*+] |\d+[.)] |(-{3,}|\*{3,}|_{3,})\s*$)")

# RM2764 — foyer unique du frontmatter YAML des fiches PM. Auparavant recopié
# à l'identique dans 8 scripts (pm-conso-report, pm-dashboard, pm-task-list,
# pm-stats, priority, validate-task…) sous 3 contrats de retour divergents ;
# on unifie ici les DEUX primitives dont ils ont réellement besoin.
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_frontmatter(text):
    """Découpe un doc markdown : (fm, body, end).

    - `fm`  : dict du frontmatter ; **None** si aucun bloc, YAML invalide, ou
              YAML non-dict (une liste ou un scalaire n'est pas une fiche).
    - `body`: ce qui suit le bloc (tout le texte s'il n'y a pas de bloc).
    - `end` : offset de fin du bloc dans `text` (0 s'il n'y a pas de bloc) —
              pour les appelants qui réécrivent le corps en préservant l'entête.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text, 0
    try:
        d = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, text[m.end():], m.end()
    return (d if isinstance(d, dict) else None), text[m.end():], m.end()


def read_frontmatter(path):
    """Frontmatter d'un FICHIER → dict, ou None si illisible / absent / invalide
    / non-dict. Contrat unifié des lecteurs de fiches PM (RM2764). Les appelants
    gardent tous par `if fm:` : None et {} y sont équivalents, et renvoyer None
    sur un YAML non-dict est plus sûr que l'ancien `safe_load` brut (qui laissait
    passer une liste/chaîne jusqu'au premier `.get`)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    fm, _body, _end = split_frontmatter(text)
    return fm


def code_line_flags(lines):
    """Pour chaque ligne, dit si elle appartient à un bloc de code.

    Deux formes markdown :
      - bloc fencé (``` ou ~~~), fermé par le même marqueur — un fence laissé
        ouvert vaut jusqu'à la fin, comme le rendu markdown ;
      - bloc indenté de 4 espaces (ou une tabulation), MAIS seulement hors
        liste : sous un item de liste, cette indentation fait une sous-liste,
        pas du code — sinon des critères imbriqués deviendraient invisibles.
    """
    flags, fence, in_indented, in_list = [], None, False, False
    for line in lines:
        m = FENCE_RE.match(line)
        if fence is not None:                       # dans un bloc fencé
            flags.append(True)
            if m and m.group(1) == fence:
                fence = None
            continue
        if m:                                       # ouverture d'un bloc fencé
            fence, in_indented = m.group(1), False
            flags.append(True)
            continue
        if not line.strip():                        # ligne vide : ne ferme rien
            flags.append(in_indented)
            continue
        indented = bool(INDENTED_RE.match(line))
        if in_indented:
            if indented:
                flags.append(True)
                continue
            in_indented = False                     # retour à la marge = sortie
        if indented:
            # Dans une liste, l'indentation continue l'item (sous-liste ou
            # paragraphe) ; hors liste, elle ouvre un bloc de code.
            if in_list:
                flags.append(False)
                continue
            in_indented = True
            flags.append(True)
            continue
        flags.append(False)
        in_list = bool(LIST_ITEM_RE.match(line))    # état porté par la marge
    return flags


def checklist_lines(text):
    """Rend les lignes de checklist réelles : [(index de ligne, match), …].

    L'index est celui dans `text.split("\\n")`, pour réécrire la ligne en place.
    L'ordre est celui du document : la position dans cette liste est le numéro
    d'item 1-based utilisé par `--check N`.
    """
    lines = text.split("\n")
    flags = code_line_flags(lines)
    out = []
    for i, line in enumerate(lines):
        if flags[i]:
            continue
        m = CHECK_LINE_RE.match(line)
        if m:
            out.append((i, m))
    return out


def is_placeholder(label):
    """Le libellé d'un item de checklist est-il un simple gabarit ? (RM2789)

    « (à compléter) », « à définir », « TBD »… : personne ne peut les cocher, ils ne
    désignent aucun travail. Les compter comme des critères non satisfaits bloquait la
    livraison — et le contournement (`--allow-unchecked`) faisait sauter le contrôle pour
    les vrais critères en même temps.

    Une case **sans aucun texte** (`- [ ]` seul) relève de la même catégorie : elle ne
    désigne rien non plus. `karl-agent.parse_checklist` l'ignorait déjà, pas ici — une
    des trois divergences de parseur relevées par l'étude RM2882. Unifié ici, sur le
    parseur que tout le monde partage.
    """
    label = (label or "").strip()
    return not label or bool(PLACEHOLDER_RE.match(label))


def real_checklist_lines(text):
    """Les items de checklist qui désignent un VRAI travail (gabarits exclus)."""
    return [(i, m) for i, m in checklist_lines(text) if not is_placeholder(m.group(3)[1:])]


def unwrap(text):
    """Dé-enveloppe les paragraphes : joint les lignes d'un même paragraphe (RM2789).

    Préserve tout ce dont le retour à la ligne porte le sens : blocs de code (clôturés
    ou indentés), titres, listes, tableaux, citations, règles horizontales, lignes vides,
    et les **sauts durs** markdown (deux espaces en fin de ligne, ou backslash final).

    Idempotent : un texte déjà dé-enveloppé en ressort inchangé.
    """
    if not text:
        return text
    lines = text.split("\n")
    flags = code_line_flags(lines)
    out, buf = [], []

    def flush():
        if buf:
            out.append(" ".join(buf))
            buf.clear()

    for i, line in enumerate(lines):
        strip = line.strip()
        dur = line.endswith("  ") or line.rstrip().endswith("\\")
        if flags[i] or not strip or STRUCT_RE.match(line) or CHECK_LINE_RE.match(line):
            flush()
            out.append(line)
            continue
        buf.append(strip)
        if dur:                                  # saut DUR voulu : on ne le mange pas
            flush()
            out[-1] = out[-1] + "  "
    flush()
    return "\n".join(out)


def placeholder_lines(text):
    """Les items de checklist qui ne sont que des GABARITS : [(index de ligne, match), …]."""
    return [(i, m) for i, m in checklist_lines(text) if is_placeholder(m.group(3)[1:])]


def drop_placeholders(text):
    """Retire les items de checklist qui ne sont que des gabarits (RM2789).

    Le chemin de sortie EXPLICITE quand un ticket n'a pas de critères à définir : plutôt
    que de contourner le garde-fou avec `--allow-unchecked` — qui désarme aussi le contrôle
    des VRAIS critères — on retire la case vide, et le ticket assume qu'il n'en a pas.
    """
    idx = {i for i, _ in placeholder_lines(text)}
    if not idx:
        return text, 0
    lines = text.split("\n")
    return "\n".join(l for i, l in enumerate(lines) if i not in idx), len(idx)


# ── Rendu HTML pour les emails (RM3440) ──────────────────────────────────────
# `to_html()` s'appuie sur python-markdown quand il est installé (extensions `tables`,
# `sane_lists`, `nl2br`) ; sinon il bascule sur un convertisseur intégré qui couvre ce que
# nos documents contiennent : titres, paragraphes, listes (imbriquées par indentation),
# TABLEAUX, citations, blocs de code, règles, gras, italique, code en ligne, liens.
#
# Pourquoi un convertisseur intégré : python-markdown n'est pas installé partout (il ne
# l'était pas dans le conteneur `dev`), et le repli historique — le texte dans un <pre> —
# rend un tableau illisible, alors que c'est pour les tableaux qu'on envoie du HTML
# (RM3052). Un rapport client ne doit pas dépendre d'un paquet système.
#
# Contrat commun aux deux moteurs : comme `nl2br`, un retour à la ligne dans un paragraphe
# reste un retour à la ligne. L'entrée est supposée DÉJÀ échappée (`&` et `<`, cf.
# `pm_client_notify.esc_md`) : aucun HTML brut ne doit traverser un mail sortant.

_H_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_H_HR = re.compile(r"^ {0,3}([-*_])(\s*\1){2,}\s*$")
_H_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_H_UL = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_H_OL = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")


def to_html(src):
    """Markdown (déjà échappé) → HTML sans style. Chaîne vide si rien à rendre."""
    if not (src or "").strip():
        return ""
    try:
        import markdown as _md
    except ImportError:
        return builtin_to_html(src)
    return _md.markdown(src, extensions=["tables", "sane_lists", "nl2br"])


def _h_inline(text):
    """Code en ligne d'abord (son contenu n'est pas interprété), puis liens, gras, italique.
    `>` est échappé comme le fait python-markdown : `<` l'est déjà en amont (esc_md), et un
    `&lt;script>` doit ressortir `&lt;script&gt;`, pas à moitié balise."""
    text = text.replace(">", "&gt;")
    codes = []

    def _keep(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    out = re.sub(r"`([^`]+)`", _keep, text)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w_])__(.+?)__(?![\w_])", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", out)
    return re.sub(r"\x00(\d+)\x00", lambda m: "<code>%s</code>" % codes[int(m.group(1))], out)


def _h_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _h_table(lines):
    head, sep = _h_cells(lines[0]), _h_cells(lines[1])
    aligns = ["center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":")
              else "left" if c.startswith(":") else None for c in sep]

    def cell(tag, i, v):
        a = aligns[i] if i < len(aligns) else None
        return "<%s%s>%s</%s>" % (tag, ' align="%s"' % a if a else "", _h_inline(v), tag)

    out = ["<table>", "<thead>", "<tr>" + "".join(cell("th", i, v) for i, v in enumerate(head)) + "</tr>",
           "</thead>", "<tbody>"]
    for row in lines[2:]:
        r = (_h_cells(row) + [""] * len(head))[:len(head)]
        out.append("<tr>" + "".join(cell("td", i, v) for i, v in enumerate(r)) + "</tr>")
    out += ["</tbody>", "</table>"]
    return "\n".join(out)


def _h_is_table(lines, i):
    return lines[i].lstrip().startswith("|") and i + 1 < len(lines) and bool(_H_TABLE_SEP.match(lines[i + 1]))


def _h_block_start(lines, i):
    ln = lines[i]
    return bool(_H_HEADING.match(ln) or _H_HR.match(ln) or FENCE_RE.match(ln) or ln.lstrip().startswith(">")
                or _H_UL.match(ln) or _H_OL.match(ln) or _h_is_table(lines, i))


def _h_list(lines, i):
    """La liste qui commence à lines[i] → (html, index de la ligne suivante)."""
    rx = _H_UL if _H_UL.match(lines[i]) else _H_OL
    tag = "ul" if rx is _H_UL else "ol"
    base = len(rx.match(lines[i]).group(1))
    items = []
    while i < len(lines):
        ln = lines[i]
        m = rx.match(ln)
        if m and len(m.group(1)) == base:
            items.append([m.group(2)])
            i += 1
            continue
        if not ln.strip():
            # une ligne vide n'arrête la liste que si la suivante n'en fait plus partie
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            mn = _H_UL.match(nxt) or _H_OL.match(nxt)
            if mn and len(mn.group(1)) >= base:
                i += 1
                continue
            break
        if items and len(ln) - len(ln.lstrip()) > base:
            items[-1].append(ln[base:])
            i += 1
            continue
        break
    html = []
    for it in items:
        sub = [s for s in it[1:]]
        if any(_H_UL.match(s) or _H_OL.match(s) for s in sub):
            ind = min(len(s) - len(s.lstrip()) for s in sub if s.strip())
            html.append("<li>%s\n%s</li>" % (_h_inline(it[0]), builtin_to_html("\n".join(s[ind:] for s in sub))))
        else:
            html.append("<li>%s</li>" % "<br />\n".join(_h_inline(x.strip()) for x in it))
    return "<%s>\n%s\n</%s>" % (tag, "\n".join(html), tag), i


def builtin_to_html(src):
    """Convertisseur intégré (sans dépendance) — voir l'en-tête de section."""
    lines = (src or "").replace("\r\n", "\n").split("\n")
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        fm = FENCE_RE.match(ln)
        if fm:
            body, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith(fm.group(1)):
                body.append(lines[i])
                i += 1
            out.append("<pre><code>%s</code></pre>" % "\n".join(body))
            i += 1
            continue
        m = _H_HEADING.match(ln)
        if m:
            n = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (n, _h_inline(m.group(2)), n))
            i += 1
            continue
        if _H_HR.match(ln):
            out.append("<hr />")
            i += 1
            continue
        if _h_is_table(lines, i):
            block = [ln, lines[i + 1]]
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(_h_table(block))
            continue
        if ln.lstrip().startswith(">"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>\n%s\n</blockquote>" % builtin_to_html("\n".join(block)))
            continue
        if _H_UL.match(ln) or _H_OL.match(ln):
            html, i = _h_list(lines, i)
            out.append(html)
            continue
        para = []
        while i < len(lines) and lines[i].strip() and (not para or not _h_block_start(lines, i)):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % "<br />\n".join(_h_inline(p) for p in para))
    return "\n".join(out)
