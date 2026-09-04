#!/usr/bin/env python3
"""Tests de pm-cockpit-remap (RM2889) : attribution d'un hunk à son symbole, lecture de la carte."""
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("remap", Path(__file__).with_name("pm-cockpit-remap.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

lines = ["<!doctype html>", "<script>", "let a = 1;", "function un() {", "  x();", "}", "async function deux(p) {", "  y();", "}", "const trois = () => 0;"]
syms = m.symbols(lines)
assert syms == [(3, "a"), (4, "un"), (7, "deux"), (10, "trois")], syms
assert m.locate(syms, 5) == "un" and m.locate(syms, 8) == "deux" and m.locate(syms, 10) == "trois"
assert m.locate(syms, 1).startswith("«hors symbole"), "avant toute déclaration : hors symbole"
root = Path(__file__).resolve().parent.parent
mm = m.read_map(str(root))
assert mm["kill"]["cible"] == "services/sessions.service.js" and mm["kill"]["lot"] == "L2", mm.get("kill")
assert mm["renderMailList"]["couche"] == "view", "la carte lit bien la couche"
print("OK — pm-cockpit-remap : attribution par pré-image et lecture de la carte")
