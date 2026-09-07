"""pm_license — la licence d'un projet / d'un dépôt, posée à la naissance (RM3030, suite de RM3029).

Un dépôt sans `LICENSE` n'est pas open source : personne n'a le droit de l'utiliser ni de le
modifier. `pm-project-new` pose la question et consigne le choix dans `project/overview.md`
(`license:`) ; `pm-repo-new --push-from` écrit `LICENSE` dans le dépôt s'il n'en a pas.

Catalogue (identifiants SPDX ; textes intégraux dans templates/licenses/) :
    MPL-2.0      recommandée pour « ouvert avec modules » : le cœur reste ouvert, un module dans
                 ses propres fichiers peut rester fermé (copyleft par fichier)
    Apache-2.0   permissive + clause de brevet (+ fichier NOTICE)
    MIT          permissive minimale
    LGPL-3.0     copyleft du cœur, liaison libre
    GPL-3.0      copyleft fort : tout ce qui en dérive est GPL (pas de module fermé)
    AGPL-3.0     GPL + usage réseau (SaaS) couvert
    proprietary  tous droits réservés — rien n'est publié (défaut hors TTY)
"""
import datetime as _dt
import os
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "licenses"

CATALOG = [
    {"id": "MPL-2.0",     "file": "MPL-2.0.txt",       "label": "Mozilla Public License 2.0",
     "hint": "cœur ouvert, modules libres OU fermés (copyleft par fichier) — recommandée", "recommended": True},
    {"id": "Apache-2.0",  "file": "Apache-2.0.txt",    "label": "Apache License 2.0",
     "hint": "permissive, clause de brevet, fichier NOTICE"},
    {"id": "MIT",         "file": "MIT.txt",           "label": "MIT License",
     "hint": "permissive minimale (un fork fermé du cœur est possible)"},
    {"id": "LGPL-3.0",    "file": "LGPL-3.0-only.txt", "label": "GNU LGPL v3",
     "hint": "copyleft du cœur, modules liés libres ou fermés"},
    {"id": "GPL-3.0",     "file": "GPL-3.0-only.txt",  "label": "GNU GPL v3",
     "hint": "copyleft fort : tout module distribué avec le cœur devient GPL"},
    {"id": "AGPL-3.0",    "file": "AGPL-3.0-only.txt", "label": "GNU AGPL v3",
     "hint": "GPL + obligation de publier même en usage réseau (SaaS)"},
    {"id": "proprietary", "file": None,                "label": "Tous droits réservés",
     "hint": "rien n'est publié ; LICENSE court « tous droits réservés » — défaut hors terminal"},
]
IDS = [c["id"] for c in CATALOG]
DEFAULT_HOLDER = os.environ.get("PM_LICENSE_HOLDER") or "iProspective"
# Le défaut de la question (Entrée) : la décision iProspective du 2026-09-07 (RM3029) est la GPL ; `PM_LICENSE_DEFAULT` la change.
DEFAULT_LICENSE = os.environ.get("PM_LICENSE_DEFAULT") or "GPL-3.0"


def entry(license_id: str) -> dict | None:
    lid = str(license_id or "").strip()
    for c in CATALOG:
        if c["id"].lower() == lid.lower():
            return c
    return None


def normalize(license_id: str | None) -> str | None:
    """`mpl-2.0` → `MPL-2.0` ; `none`/`aucune` → `proprietary` ; inconnu → None."""
    if license_id is None:
        return None
    v = str(license_id).strip()
    if v.lower() in ("none", "aucune", "proprio", "proprietaire", "propriétaire", "all-rights-reserved"):
        return "proprietary"
    e = entry(v)
    return e["id"] if e else None


def render(license_id: str, holder: str | None = None, year: int | None = None) -> str:
    """Le texte de `LICENSE` : texte SPDX intégral (MIT : année et titulaire renseignés) ; propriétaire : court."""
    e = entry(license_id)
    if not e:
        raise ValueError(f"licence inconnue : {license_id} (connues : {', '.join(IDS)})")
    holder = holder or DEFAULT_HOLDER
    year = year or _dt.date.today().year
    if e["id"] == "proprietary":
        return (f"Copyright (c) {year} {holder}. Tous droits réservés.\n\n"
                "Ce logiciel n'est pas publié sous licence libre : toute utilisation, copie,\n"
                "modification ou diffusion sans autorisation écrite du titulaire est interdite.\n")
    text = (TEMPLATES / e["file"]).read_text(encoding="utf-8")
    if e["id"] == "MIT":
        text = text.replace("<year>", str(year)).replace("<copyright holders>", holder)
        text = text.replace("[year]", str(year)).replace("[fullname]", holder)
    return text if text.endswith("\n") else text + "\n"


def menu_text(default: str = DEFAULT_LICENSE) -> str:
    lines = ["Licence du code (identifiant SPDX) :"]
    for i, c in enumerate(CATALOG, 1):
        lines.append(f"  {i}. {c['id']:<12} {c['hint']}" + ("  ← défaut" if c["id"] == default else ""))
    return "\n".join(lines)


def ask(default: str = DEFAULT_LICENSE, stdin=None, stdout=None) -> str:
    """Pose la question en terminal (numéro ou identifiant ; Entrée = défaut). Rend un identifiant du catalogue."""
    stdin = stdin or sys.stdin; stdout = stdout or sys.stdout
    stdout.write(menu_text(default) + "\n")
    while True:
        stdout.write(f"Choix [{default}] : "); stdout.flush()
        raw = stdin.readline()
        if not raw:                      # EOF → défaut
            return default
        v = raw.strip()
        if not v:
            return default
        if v.isdigit() and 1 <= int(v) <= len(CATALOG):
            return CATALOG[int(v) - 1]["id"]
        n = normalize(v)
        if n:
            return n
        stdout.write(f"  ? « {v} » inconnu — un numéro ou un identifiant parmi : {', '.join(IDS)}\n")


def choose(option: str | None, interactive: bool | None = None, default: str = DEFAULT_LICENSE, warn=None, stdin=None, stdout=None) -> str:
    """Le choix effectif : `--license` s'il est donné (validé), sinon la question en TTY, sinon `proprietary` + avertissement."""
    if option:
        n = normalize(option)
        if not n:
            raise ValueError(f"--license {option} : inconnu (connues : {', '.join(IDS)})")
        return n
    if interactive is None:
        interactive = bool(getattr(stdin or sys.stdin, "isatty", lambda: False)()) and os.environ.get("PM_NO_PROMPT") != "1"
    if interactive:
        return ask(default, stdin=stdin, stdout=stdout)
    if warn:
        warn("aucune licence choisie (--license absent, pas de terminal) → « proprietary » : rien n'est publié tant que la décision n'est pas prise")
    return "proprietary"


def write_license(repo_dir, license_id: str, holder: str | None = None, year: int | None = None, force: bool = False) -> Path | None:
    """Écrit `LICENSE` (et `NOTICE` pour Apache-2.0) à la racine du dépôt s'il n'en a pas. Rend le chemin écrit, None si déjà présent."""
    repo_dir = Path(repo_dir)
    existing = [p for p in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md") if (repo_dir / p).exists()]
    if existing and not force:
        return None
    target = repo_dir / "LICENSE"
    target.write_text(render(license_id, holder, year), encoding="utf-8")
    if normalize(license_id) == "Apache-2.0":
        notice = repo_dir / "NOTICE"
        if not notice.exists():
            notice.write_text(f"{repo_dir.name}\nCopyright (c) {year or _dt.date.today().year} {holder or DEFAULT_HOLDER}\n\n"
                              "This product includes software developed by the copyright holder above,\n"
                              "licensed under the Apache License, Version 2.0.\n", encoding="utf-8")
    return target


def read_from_overview(path) -> str | None:
    """`license:` du manifeste d'un projet PM : `meta.yml` (RM1994) ou le frontmatter de `project/overview.md`. Lecture tolérante, sans yaml."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    if str(path).endswith(".yml"):
        fm = text
    elif text.startswith("---"):
        fm = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    else:
        return None
    for line in fm.splitlines():
        s = line.strip()
        if s.startswith("license:"):
            v = s[len("license:"):].split("#", 1)[0].strip().strip('"').strip("'")
            return normalize(v) if v else None
    return None


def project_overview_from_workspace(start) -> Path | None:
    """Remonte depuis un dossier jusqu'à un `.mmi-pm` (workspace PM) et rend son manifeste : `meta.yml`, sinon `project/overview.md`."""
    p = Path(start).resolve()
    for d in [p, *p.parents]:
        mmi = d / ".mmi-pm"
        if mmi.exists():
            root = mmi.resolve()
            for cand in (root / "meta.yml", root / "project" / "overview.md"):
                if cand.is_file():
                    return cand
            return None
    return None
