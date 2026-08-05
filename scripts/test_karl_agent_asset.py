#!/usr/bin/env python3
"""Tests RM2522 — _resolve_asset : servir les assets du cockpit (xterm.js
vendoré, karl-term.js) sans ouvrir d'évasion de chemin.

La route `/static/<rel>` est PUBLIQUE (comme index.html) : le confinement sous
COCKPIT_DIR et la liste blanche d'extensions sont donc la seule barrière — d'où
ces tests.

Lancer : python3 scripts/test_karl_agent_asset.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, rel, expect_served: bool):
    got = ka._resolve_asset(rel)
    ok = (got is not None) == expect_served
    if ok and expect_served:
        # servi ⇒ doit rester sous COCKPIT_DIR, quoi qu'il arrive
        try:
            got.relative_to(ka.COCKPIT_DIR.resolve())
        except ValueError:
            ok = False
    print(("✓ " if ok else "✗ ") + f"{name} → {'servi' if got else 'refusé'}")
    if not ok:
        fails.append(name)


# — servis : les assets réels du cockpit —
check("vendor/xterm.js", "vendor/xterm.js", True)
check("vendor/xterm.css", "vendor/xterm.css", True)
check("vendor/addon-fit.js", "vendor/addon-fit.js", True)
check("client terminal karl-term.js", "karl-term.js", True)
check("icône svg", "karl-icon.svg", True)

# — refusés : évasion de chemin —
check("traversée simple", "../scripts/karl-agent.py", False)
check("traversée profonde", "../../../../etc/passwd", False)
check("traversée déguisée", "vendor/../../scripts/karl-agent.py", False)
check("chemin absolu", "/etc/passwd", False)

# — refusés : type hors liste blanche —
check("script python", "../scripts/pm-task-add.py", False)
check("markdown de provenance", "vendor/PROVENANCE.md", False)
check("sourcemap (non vendorée)", "vendor/xterm.js.map", False)
check("chaîne vide", "", False)

# Un .js INEXISTANT est accepté par la résolution (le type et le confinement
# sont bons) : c'est la lecture qui échouera en 404 côté handler. On vérifie
# juste que le chemin reste confiné.
check("js inexistant (confiné)", "vendor/pas-la.js", True)

print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("OK — tous les tests d'assets passent")
