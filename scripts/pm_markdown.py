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

CHECK_LINE_RE = re.compile(r"^(\s*[-*]\s*\[)([ xX])(\].*)$")
FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
LIST_ITEM_RE = re.compile(r"^ {0,3}([-*+]|\d+[.)])\s")
INDENTED_RE = re.compile(r"^(?: {4,}|\t)")
# Un item de checklist qui ne désigne aucun travail : gabarit de création, reste
# de rédaction. Il ne compte ni comme critère à cocher ni comme critère manquant.
PLACEHOLDER_RE = re.compile(r"^\W*(à compléter|a completer|à définir|a definir|tbd|todo)\W*$", re.I)
# Lignes dont le retour à la ligne PORTE du sens : les dé-envelopper les casserait.
STRUCT_RE = re.compile(r"^ {0,3}(#{1,6} |>|\||[-*+] |\d+[.)] |(-{3,}|\*{3,}|_{3,})\s*$)")


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
    """
    return bool(PLACEHOLDER_RE.match((label or "").strip()))


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
