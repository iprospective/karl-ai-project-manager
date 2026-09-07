#!/usr/bin/env python3
"""Tests RM3033 — pm_index (port de bin/mmi-pm index/list) : spec, add/remove (dry-run compris), rebuild par découverte des meta.yml
(clients + projets, .git élagué, symlinks non traversés), listing."""
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_index as I  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


check("split_spec", I.split_spec("acme/shop") == ("acme", "shop"))
for bad in ("acme", "acme/", "/shop", "a/b/c"):
    try:
        I.split_spec(bad); check(f"spec invalide refusée : {bad}", False)
    except ValueError:
        check(f"spec invalide refusée : {bad}", True)
with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td); proj = d / "projects"; ws = d / "ws"
    (ws / "acme" / "shop" / ".mmi-pm").mkdir(parents=True); (ws / "acme" / "shop" / ".mmi-pm" / "meta.yml").write_text('slug: "shop"\nclient: acme\n')
    (ws / "acme" / ".mmi-pm-client" / "client").mkdir(parents=True); (ws / "acme" / ".mmi-pm-client" / "memory").mkdir(); (ws / "acme" / ".mmi-pm-client" / "meta.yml").write_text("slug: acme\n")
    (ws / "beta" / "api" / ".mmi-pm").mkdir(parents=True); (ws / "beta" / "api" / ".mmi-pm" / "meta.yml").write_text("slug: api\n")   # client déduit du dossier parent
    (ws / "beta" / "api" / ".git" / ".mmi-pm").mkdir(parents=True); (ws / "beta" / "api" / ".git" / ".mmi-pm" / "meta.yml").write_text("slug: fantome\n")   # sous .git : élagué
    (ws / "old").mkdir(); (ws / "old" / ".mmi-pm").symlink_to(ws / "acme" / "shop" / ".mmi-pm")   # ancienne instance : symlink non traversé
    r = I.add(proj, "acme/shop", ws / "acme" / "shop", dry=True); check("add dry-run : rien écrit", not (proj / "clients").exists() and r["dry"])
    r = I.add(proj, "acme/shop", ws / "acme" / "shop"); link = proj / "clients" / "acme" / "projects" / "shop"
    check("add : lien posé vers <ws>/.mmi-pm", link.is_symlink() and pathlib.Path(link).resolve() == (ws / "acme" / "shop" / ".mmi-pm").resolve() and r["target"].endswith("/.mmi-pm"))
    check("add : défaut = <workspaces_root>/<client>/<projet>", I.add(proj, "beta/api", workspaces_root=ws)["client"] == "beta" and (proj / "clients" / "beta" / "projects" / "api").is_symlink())
    try:
        I.add(proj, "zz/none", ws / "zz" / "none"); check("add : pas de .mmi-pm → erreur", False)
    except FileNotFoundError:
        check("add : pas de .mmi-pm → erreur", True)
    check("remove dry-run garde le lien", I.remove(proj, "beta/api", dry=True)["dry"] and (proj / "clients" / "beta" / "projects" / "api").is_symlink())
    I.remove(proj, "beta/api"); check("remove retire le lien", not (proj / "clients" / "beta" / "projects" / "api").exists())
    try:
        I.remove(proj, "beta/api"); check("remove : absent → erreur", False)
    except FileNotFoundError:
        check("remove : absent → erreur", True)
    clients, projects = I.discover(ws)
    check("discover : 1 client, 2 projets (fantôme sous .git et symlink ignorés)", len(clients) == 1 and sorted(p[0].name for p in projects) == ["api", "shop"], str((clients, projects)))
    said = []; r = I.rebuild(proj, ws, dry=True, say=said.append)
    check("rebuild dry-run : compte et annonce sans écrire", r == {"clients": 1, "projects": 2, "dry": True} and any("acme/shop" in x for x in said) and not (proj / "clients" / "acme" / "client").exists())
    r = I.rebuild(proj, ws)
    check("rebuild : liens client (client, memory) et projets, client déduit du dossier", r["clients"] == 1 and r["projects"] == 2 and (proj / "clients" / "acme" / "client").is_symlink() and (proj / "clients" / "acme" / "memory").is_symlink() and not (proj / "clients" / "acme" / "projects_used").exists() and (proj / "clients" / "beta" / "projects" / "api").is_symlink())
    rows = I.listing(proj); check("listing", [c for c, _ in rows] == ["acme", "beta"] and rows[0][1][0][0] == "shop" and rows[0][1][0][1].endswith("/.mmi-pm"))
    txt = I.format_listing(rows); check("format", txt.splitlines()[0] == "acme" and "  └ shop -> " in txt)
    try:
        I.listing(d / "nope"); check("listing : index absent → erreur", False)
    except FileNotFoundError:
        check("listing : index absent → erreur", True)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — pm_index (RM3033)")
