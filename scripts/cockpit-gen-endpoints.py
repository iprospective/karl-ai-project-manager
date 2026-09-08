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
PY_OUT = Path(__file__).resolve().parent / "karl_api_routes.py"   # L7 : alias /api/<type>/<action> → route historique, côté serveur

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
        "// L7 (2026-09-05) : `route()` rend la CIBLE ; le serveur sert /api/<type>/<action> par alias", "// (scripts/karl_api_routes.py, généré ici aussi) et garde les chemins historiques pour les autres clients.", "",
        "export const ROUTES = {"]
body += [f'  "{k}": {{ current: "{c}", target: "{t}", lot: "{l}", callers: {n} }},'
         for k, c, t, l, n in entries]
body += ["};", "",
         "/** Chemin à appeler pour une route nommée — la cible /api/<type>/<action> depuis L7. Lève si le nom est inconnu. */",
         "export function route(name) {", "  const e = ROUTES[name];",
         "  if (!e) throw new Error(`route inconnue : ${name}`);", "  return e.target;", "}", "",
         "/** Le nom d'une route d'après son chemin ACTUEL — pour les doublons hérités",
         " *  dont la cible normalisée est la même (/file et /fs/file). */",
         "export function routeFor(current) {",
         "  const hit = Object.entries(ROUTES).find(([, r]) => r.current === current);",
         "  if (!hit) throw new Error(`route inconnue : ${current}`);",
         "  return hit[0];",
         "}", "",
         "/** Chemin cible (§ 10.4), pour les tests de dérive et la bascule L7. */",
         "export function targetRoute(name) {", "  const e = ROUTES[name];",
         "  if (!e) throw new Error(`route inconnue : ${name}`);", "  return e.target;", "}", ""]
OUT.write_text("\n".join(body), encoding="utf-8")
# — alias serveur (L7) : la cible normalisée → le chemin historique que karl-agent.py sait déjà servir —
alias = {}
for k, c, t, l, n in entries:
    alias.setdefault(t, c)      # deux chemins historiques pour une même cible : le premier sert d'alias
py = ['"""karl_api_routes — alias /api/<type>/<action> → chemin historique (RM2889, L7).',
      '', 'GÉNÉRÉ par scripts/cockpit-gen-endpoints.py depuis deploy/karl-agent/cockpit/MIGRATION-ROUTES.tsv :',
      'ne pas éditer à la main, régénérer. Le front (src/core/endpoints.js, `route()`) appelle les cibles ;',
      'karl-agent.py les ramène au chemin historique avant son dispatch, et continue de servir les chemins',
      'historiques tels quels pour les autres clients (scripts, app mobile).', '"""', '',
      'TARGET_TO_CURRENT = {']
py += [f'    "{t}": "{alias[t]}",' for t in sorted(alias)]
py += ['}', '', '# RM3004 : la table inverse — un chemin historique appelé directement (hors cockpit) est repérable, et journalisé avant retrait.',
       'CURRENT_TO_TARGET = {v: k for k, v in TARGET_TO_CURRENT.items()}', '', '',
       'def historical_target(path):',
       '    """Cible /api/… d\'un chemin HISTORIQUE (sans query string), suffixe conservé ; None si ce n\'est pas un chemin routé."""',
       '    if path.startswith("/api/"):', '        return None',
       '    hit = CURRENT_TO_TARGET.get(path)',
       '    if hit is None:',
       '        for cur in sorted(CURRENT_TO_TARGET, key=len, reverse=True):',
       '            if path.startswith(cur + "/"):',
       '                hit = CURRENT_TO_TARGET[cur] + path[len(cur):]', '                break',
       '    return hit', '', '',
       'def api_alias(path_qs):',
       '    """Réécrit une URL cible en URL historique (la query string est conservée) ; les autres URL passent telles quelles.',
       '    Un suffixe après la cible (identifiant : /api/auth/devices/<id>) est reporté sur le chemin historique."""',
       '    if not path_qs.startswith("/api/"):', '        return path_qs',
       '    path, sep, qs = path_qs.partition("?")',
       '    hit = TARGET_TO_CURRENT.get(path)',
       '    if hit is None:',
       '        for tgt in sorted(TARGET_TO_CURRENT, key=len, reverse=True):',
       '            if path.startswith(tgt + "/"):',
       '                hit = TARGET_TO_CURRENT[tgt] + path[len(tgt):]', '                break',
       '    if hit is None:', '        return path_qs',
       '    return hit + sep + qs', '']
PY_OUT.write_text("\n".join(py), encoding="utf-8")
print(f"{len(alias)} alias → {PY_OUT.relative_to(ROOT.parent.parent.parent)}")
print(f"{len(entries)} routes → {OUT.relative_to(ROOT.parent.parent.parent)}")
