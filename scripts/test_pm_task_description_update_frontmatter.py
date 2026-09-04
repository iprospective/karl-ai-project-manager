#!/usr/bin/env python3
"""Tests RM2820 — le frontmatter d'une fiche PM ne part jamais en description.

Bug couvert : `--set-from-file` recevant la fiche `RM<id>.md` COMPLÈTE poussait
son frontmatter YAML dans la description Redmine, et — depuis RM2578 — le
recopiait dans le CORPS du MD (deux blocs frontmatter). Constaté sur RM2426.

Lancer : python3 scripts/test_pm_task_description_update_frontmatter.py
"""
import importlib.util
import io
import contextlib
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "pm_task_description_update", HERE / "pm-task-description-update.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


FM = """---
schema_version: 1.11.0
redmine_id: 2426
title: Renouvellement serveurs OVH
reporting:
  cf17_tokens: 323800
---
"""
BODY = "## Contexte\n\n- [ ] un\n- [ ] deux\n"
FICHE = FM + BODY

# --- 1. La fonction pure -----------------------------------------------------

clean, stripped = mod.strip_task_frontmatter(FICHE)
check("fiche complète : frontmatter retiré", stripped is True and clean == BODY)
check("fiche complète : aucune clé de frontmatter ne survit",
      "schema_version" not in clean and "cf17_tokens" not in clean)

clean2, stripped2 = mod.strip_task_frontmatter(BODY)
check("corps seul : inchangé, non signalé", stripped2 is False and clean2 == BODY)

# Un corps qui CITE du YAML de fiche plus bas n'est pas amputé.
CITING = ("## Doc\n\nLe frontmatter ressemble à ceci :\n\n```yaml\n---\n"
          "schema_version: 1.11.0\nredmine_id: 42\n---\n```\n\nFin.\n")
clean3, stripped3 = mod.strip_task_frontmatter(CITING)
check("citation de YAML dans le corps : intacte",
      stripped3 is False and clean3 == CITING)

# Un `---` de séparation en tête, sans clé de fiche : ce n'est pas un frontmatter.
SEP = "---\ntitre: doc libre\nauteur: moi\n---\n\n## Suite\n"
clean4, stripped4 = mod.strip_task_frontmatter(SEP)
check("bloc YAML sans clé de fiche : laissé intact",
      stripped4 is False and clean4 == SEP)

# Un seul marqueur suffit (fiche partielle / ancien schéma).
ONE = "---\nredmine_id: 7\ntitle: x\n---\n## C\n"
clean5, stripped5 = mod.strip_task_frontmatter(ONE)
check("redmine_id seul suffit à reconnaître une fiche",
      stripped5 is True and clean5 == "## C\n")

check("texte vide : pas de crash", mod.strip_task_frontmatter("") == ("", False))
check("None : pas de crash", mod.strip_task_frontmatter(None) == (None, False))

# --- 2. Ce que voient Redmine ET le corps MD (RM2578) ------------------------

# main() strippe AVANT build_new_description : la description poussée et le
# corps MD réécrit sont le même texte, donc les deux sont propres.
stripped_text, _ = mod.strip_task_frontmatter(FICHE)
new_desc, total, checked, changed, bits, dchanged = mod.build_new_description(
    "ancienne", stripped_text, {1}, set(), False)
check("description poussée : sans frontmatter", "schema_version" not in new_desc)
check("corps MD (= new_desc, RM2578) : sans frontmatter",
      not new_desc.lstrip().startswith("---"))
check("les coches s'appliquent toujours (RM2281 non régressé)",
      "- [x] un" in new_desc and total == 2 and checked == 1)

# --- 3. Le chemin CLI --set-from-file en --dry-run ---------------------------


class _FakeCfg:
    projects_root = pathlib.Path("/")

    @staticmethod
    def load():
        return _FakeCfg()

    def find_task(self, rm_id):
        return pathlib.Path("/tmp/RM%s_x.md" % rm_id)


def run_cli(path):
    argv, fetch, cfg = sys.argv, mod.fetch_issue, mod.PMConfig
    sys.argv = ["prog", "2426", "--set-from-file", str(path), "--dry-run"]
    mod.fetch_issue = lambda rm_id: {"description": "ancienne desc"}
    mod.PMConfig = _FakeCfg
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                mod.main()
            except SystemExit:
                pass
    finally:
        sys.argv, mod.fetch_issue, mod.PMConfig = argv, fetch, cfg
    return buf.getvalue()


with tempfile.TemporaryDirectory() as d:
    fiche = pathlib.Path(d) / "RM2426_x.md"
    fiche.write_text(FICHE, encoding="utf-8")
    o = run_cli(fiche)
    check("CLI --dry-run : frontmatter absent de l'aperçu", "schema_version" not in o)
    check("CLI --dry-run : avertissement visible", "frontmatter de fiche PM retiré" in o)
    check("CLI --dry-run : le corps est bien là", "## Contexte" in o)

    propre = pathlib.Path(d) / "corps.md"
    propre.write_text(BODY, encoding="utf-8")
    o2 = run_cli(propre)
    check("CLI --dry-run : fichier propre, pas d'avertissement",
          "frontmatter de fiche PM retiré" not in o2 and "## Contexte" in o2)

if fails:
    print(f"\n✗ {len(fails)} échec(s)")
    raise SystemExit(1)
print("\nOK — garde-fou frontmatter (RM2820)")
