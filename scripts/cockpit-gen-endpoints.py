#!/usr/bin/env python3
"""cockpit-gen-endpoints — régénère src/core/endpoints.js depuis MIGRATION-ROUTES.tsv.

Une route du front ne s'écrit qu'une fois, dans la carte ; ce script en fait
la table nommée que les repositories consomment (RM2889, § 10.4). À rejouer
à chaque route ajoutée à la carte — un test garde les deux alignés.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "deploy" / "karl-agent" / "cockpit"
SRC, OUT = ROOT / "MIGRATION-ROUTES.tsv", ROOT / "src" / "core" / "endpoints.js"

rows = [l.rstrip("\n").split("\t") for l in SRC.read_text(encoding="utf-8").splitlines()][1:]
seen, entries = {}, []
for cur, lot, dom, tgt, n, ex in rows:
    key = ".".join(tgt.strip("/").split("/")[1:]).replace("-", "_")
    key = re.sub(r"[^A-Za-z0-9_.]", "_", key)
    if key in seen:
        key = f"{key}__{re.sub(r'[^a-z0-9]+', '_', cur.strip('/'))}"
    seen[key] = cur
    entries.append((key, cur, tgt, lot, n))
entries.sort()
body = ["// core/endpoints — table unique des routes du front. RM2889, lot L0.",
        "//", "// GÉNÉRÉ par scripts/cockpit-gen-endpoints.py depuis MIGRATION-ROUTES.tsv :",
        "// ne pas éditer à la main, régénérer.", "//",
        "// Une route ne s'écrit plus en dur dans un service : elle se nomme. C'est ce",
        "// qui rend le lot L7 mécanique — basculer `current` sur `target` (grammaire",
        "// /api/<type>/<action>, § 10.4) se fait ici, une fois, pour tous les appelants.",
        "// Les routes actuelles restent servies en alias jusqu'à L7.", "",
        "export const ROUTES = {"]
body += [f'  "{k}": {{ current: "{c}", target: "{t}", lot: "{l}", callers: {n} }},'
         for k, c, t, l, n in entries]
body += ["};", "",
         "/** Chemin à appeler aujourd'hui pour une route nommée. Lève si le nom est inconnu. */",
         "export function route(name) {", "  const e = ROUTES[name];",
         "  if (!e) throw new Error(`route inconnue : ${name}`);", "  return e.current;", "}", "",
         "/** Chemin cible (§ 10.4), pour les tests de dérive et la bascule L7. */",
         "export function targetRoute(name) {", "  const e = ROUTES[name];",
         "  if (!e) throw new Error(`route inconnue : ${name}`);", "  return e.target;", "}", ""]
OUT.write_text("\n".join(body), encoding="utf-8")
print(f"{len(entries)} routes → {OUT.relative_to(ROOT.parent.parent.parent)}")
