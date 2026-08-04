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
"""
import re

CHECK_LINE_RE = re.compile(r"^(\s*[-*]\s*\[)([ xX])(\].*)$")
FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
LIST_ITEM_RE = re.compile(r"^ {0,3}([-*+]|\d+[.)])\s")
INDENTED_RE = re.compile(r"^(?: {4,}|\t)")


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
