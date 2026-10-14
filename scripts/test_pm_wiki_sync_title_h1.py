#!/usr/bin/env python3
"""Tests RM3474 — pm-wiki-sync : le titre ne doit pas figurer deux fois sur la page.

Le gabarit d'aspect de `pm-task-doc` écrit le titre en `title:` ET en `# <titre>` au
début du corps ; le push réinjectait le H1 par-dessus. Le H1 de titre est désormais
traité comme un wrapper géré : retiré du corps canonique, ajouté à la page, rendu au
fichier local par le fold-back.

Lancer : python3 scripts/test_pm_wiki_sync_title_h1.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_wiki_sync", SCRIPTS / "pm-wiki-sync.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


T = "Déploiement du PM — ce que ça change"

# ── strip_title_h1 : ce qui est un wrapper, et ce qui n'en est pas ────────
check("H1 égal au title retiré", m.strip_title_h1(f"# {T}\n\ncorps\n", T) == "corps\n")
check("plusieurs lignes vides après le H1 absorbées",
      m.strip_title_h1(f"# {T}\n\n\ncorps\n", T) == "corps\n")
check("H1 différent conservé",
      m.strip_title_h1("# Autre titre\n\ncorps\n", T) == "# Autre titre\n\ncorps\n")
check("H1 de titre plus bas dans le corps conservé",
      m.strip_title_h1(f"intro\n\n# {T}\n\ncorps\n", T) == f"intro\n\n# {T}\n\ncorps\n")
check("H2 de même texte conservé",
      m.strip_title_h1(f"## {T}\n\ncorps\n", T) == f"## {T}\n\ncorps\n")
check("sans title: le corps est intact", m.strip_title_h1(f"# {T}\n\ncorps\n", "") == f"# {T}\n\ncorps\n")
check("has_title_h1 reconnaît le wrapper", m.has_title_h1(f"# {T}\n\nx\n", T))
check("has_title_h1 ne confond pas un autre H1", not m.has_title_h1("# X\n\nx\n", T))

# ── symétrie push ↔ canonicalisation du distant ──────────────────────────
corps = "> préambule\n\n## 1. Objet\n\ntexte\n"
page = m.build_page_body("docs/a.md", "abc1234", T, corps)
check("la page porte le titre UNE fois", page.count(f"# {T}") == 1, page[:200])
check("aller-retour sans perte", m.canonicalize_remote(page, T) == corps, repr(m.canonicalize_remote(page, T)))

# le même corps, cette fois écrit avec son H1 dans le fichier : après strip, idem
page2 = m.build_page_body("docs/a.md", "abc1234", T, m.strip_title_h1(f"# {T}\n\n{corps}", T))
check("corps portant déjà le H1 : page identique", page2 == page)

# ── intégration : push d'un aspect dont le corps porte le H1 ─────────────
def fixture(tmp, body):
    repo = Path(tmp)
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    f = repo / "docs" / "essai.md"
    f.write_text(f'---\naspect: essai\ntitle: "{T}"\n---\n\n{body}', encoding="utf-8")
    a = {"slug": "essai", "path": f, "title": T, "rm_ticket": 1,
         "body_canon": m.canonicalize(body), "wiki_title": "Essai"}
    return repo, f, a


def run(a, repo, state_dir, *, exists, wiki_text, pushed, args=None):
    m.git_short_sha = lambda *_: "abc1234"
    m.wiki_get = lambda url, key, proj, title: (exists, wiki_text, 3)
    def put(url, key, proj, title, text):
        pushed.append(text)
    m.wiki_put = put
    args = args or SimpleNamespace(dry_run=False, push_only=False, pull_only=False)
    state = {"schema": 1, "targets": {}}
    base_file = state_dir / "essai.base"
    if base_file.is_file():
        state["targets"]["essai"] = {"kind": "wiki", "last_wiki_version": 3}
    return m.sync_aspect(a, url="u", key="k", rproj="p", repo=repo, state=state,
                         state_dir=state_dir, maps=({}, {}), args=args), state


with tempfile.TemporaryDirectory() as tmp:
    repo, f, a = fixture(tmp, f"# {T}\n\n{corps}")
    sd = repo / ".wiki-sync"
    sd.mkdir()
    pushed = []
    action, state = run(a, repo, sd, exists=False, wiki_text="", pushed=pushed)
    check("page absente → push", action == "pushed", action)
    check("push : le titre n'apparaît qu'une fois", pushed and pushed[0].count(f"# {T}") == 1,
          pushed[0][:200] if pushed else "rien poussé")
    check("base enregistrée sans le H1 de titre",
          (sd / "essai.base").read_text() == corps, repr((sd / "essai.base").read_text()))

# ── intégration : le fold-back rend au fichier son H1 ────────────────────
with tempfile.TemporaryDirectory() as tmp:
    repo, f, a = fixture(tmp, f"# {T}\n\n{corps}")
    sd = repo / ".wiki-sync"
    sd.mkdir()
    (sd / "essai.base").write_text(corps, encoding="utf-8")   # base = corps sans H1
    distant = m.build_page_body("docs/essai.md", "abc1234", T, corps.replace("texte", "texte revu au wiki"))
    pushed = []
    action, state = run(a, repo, sd, exists=True, wiki_text=distant, pushed=pushed)
    check("wiki modifié seul → fold-back", action == "folded", action)
    local = f.read_text(encoding="utf-8")
    check("fold-back : le H1 du fichier est préservé", local.count(f"# {T}") == 1, local[:200])
    check("fold-back : le H1 reste en tête du corps",
          local.split("---\n\n", 1)[1].startswith(f"# {T}\n\n"), local[:200])
    check("fold-back : la modification du wiki est rapatriée", "texte revu au wiki" in local)
    check("fold-back : la base reste sans H1", (sd / "essai.base").read_text() == distant.split("\n\n", 2)[2])

if fails:
    sys.exit("ÉCHEC — " + ", ".join(fails))
print("\nOK — pm-wiki-sync : titre unique sur la page, H1 local préservé (RM3474)")
