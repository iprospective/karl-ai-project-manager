#!/usr/bin/env python3
"""pm-project-config.py — édite la conf structurée d'un projet ou d'un client (RM2531).

Single-writer (RM1669) des champs de conf que la fiche projet du cockpit (RM2353)
affiche. Édition **ciblée** de `meta.yml` : on remplace la valeur des seules clés
demandées et on préserve tout le reste du fichier (commentaires, `schema_version`,
`bootstrap`, ordre des clés…). Jamais de réécriture YAML globale (qui perdrait
commentaires et mise en forme).

Cibles (résolues par pm_paths — jamais de chemin en dur) :
  --client C --project P   → meta.yml du projet          (doit déjà exister)
  --client C   (sans -P)   → meta.yml du client (.mmi-pm-client/meta.yml, déjà
                             présent partout depuis la migration RM1994 ; recréé
                             par filet minimal dans le cas rare où il manquerait).

Champs (posés uniquement si fournis) :
  --name                → name
  --redmine-project-id  → redmine.project_id (projet) | redmine.default_project_id (client)
  --gitlab-repo         → gitlab.repo             (projet seulement)
  --default-branch      → gitlab.default_branch   (projet seulement)

Écrit le fichier puis auto-commit scopé (pm_git, RM2095 — chemin explicite, jamais
git add -A). `--porcelain` : imprime le chemin écrit sur stdout, rien d'autre.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
import pm_git  # noqa: E402

# ── Validation des valeurs (refus de tout ce qui casserait le YAML ou l'identité) ──
# \Z (fin de chaîne stricte) et pas $ : en Python $ tolère un \n final → une
# valeur « x\n » passerait le contrôle.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z")          # redmine project_id
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*\Z")       # gitlab repo / branche

def _v_id(field, v):
    return v if (len(v) <= 100 and _ID_RE.match(v)) else _bad(field, "identifiant [A-Za-z0-9._-]")


def _v_repo(field, v):
    return v if (len(v) <= 200 and _REPO_RE.match(v)) else _bad(field, "chemin/branche [A-Za-z0-9._/-]")


_VALIDATORS = {
    "name": lambda f, v: v if (v and "\n" not in v and "\r" not in v and len(v) <= 200)
            else _bad(f, "1–200 car., sans saut de ligne"),
    "redmine.project_id": _v_id,
    "redmine.default_project_id": _v_id,
    "gitlab.repo": _v_repo,
    "gitlab.default_branch": _v_repo,
}

# Champs éditables par périmètre : (clé_pointée meta.yml, nom d'attribut args).
# Projet : redmine.project_id (id du projet Redmine). Client : redmine.default_project_id
# (projet Redmine PARENT du client — schéma client réel, RM1994).
PROJECT_FIELDS = [("name", "name"), ("redmine.project_id", "redmine_project_id"),
                  ("gitlab.repo", "gitlab_repo"), ("gitlab.default_branch", "default_branch")]
CLIENT_FIELDS = [("name", "name"), ("redmine.default_project_id", "redmine_project_id")]


def _bad(field, expected):
    raise SystemExit(f"pm-project-config: valeur invalide pour {field} (attendu : {expected})")


def _collect_updates(args, fields):
    """Liste ordonnée (clé_pointée, valeur validée) pour les champs fournis."""
    out = []
    for dotted, attr in fields:
        val = getattr(args, attr, None)
        if val is None:
            continue
        out.append((dotted, _VALIDATORS[dotted](dotted, val)))
    return out


def _yaml_scalar(v: str) -> str:
    """Sérialise une valeur en scalaire YAML sûr : plain si possible, sinon
    entre quotes simples (échappement '→''). Volontairement conservateur."""
    if v == "":
        return "''"
    unsafe_start = v[0] in "!&*?|>@%`\"'#[]{},-" or v[0].isspace()
    unsafe_mid = (": " in v) or (" #" in v) or v.endswith(":") or v != v.strip()
    if unsafe_start or unsafe_mid:
        return "'" + v.replace("'", "''") + "'"
    return v


# >>> meta_set  (pur — testé par test_pm_project_config.py)
def _meta_set(text: str, updates) -> str:
    """Applique des updates (liste ordonnée de (clé_pointée, valeur)) à un texte
    YAML, en n'éditant QUE les lignes visées. `clé` = `name` (scalaire racine) ou
    `bloc.sous_clé` (ex. `gitlab.repo`). Insère la clé/le bloc s'il manque. Le
    reste du fichier est rendu à l'identique."""
    lines = text.splitlines()

    def top_index(key):
        for i, ln in enumerate(lines):
            if ln[:1] not in (" ", "\t", "") and re.match(rf"{re.escape(key)}:(\s|$)", ln):
                return i
        return -1

    for dotted, raw in updates:
        scalar = _yaml_scalar(raw)
        if "." not in dotted:
            i = top_index(dotted)
            newline = f"{dotted}: {scalar}"
            if i >= 0:
                lines[i] = newline
            else:
                lines.append(newline)
            continue
        block, sub = dotted.split(".", 1)
        bi = top_index(block)
        if bi < 0:                                   # bloc absent → on le crée
            lines.append(f"{block}:")
            lines.append(f"  {sub}: {scalar}")
            continue
        # parcourt la région indentée du bloc
        j = bi + 1
        child_indent = None
        sub_line = -1
        while j < len(lines):
            ln = lines[j]
            if ln.strip() == "":
                j += 1
                continue
            m = re.match(r"(\s+)(\S)", ln)
            if not m:                                # ligne à la colonne 0 → fin du bloc
                break
            if child_indent is None:
                child_indent = m.group(1)
            if re.match(rf"\s+{re.escape(sub)}:(\s|$)", ln):
                sub_line = j
                break
            j += 1
        indent = child_indent or "  "
        if sub_line >= 0:
            lines[sub_line] = f"{indent}{sub}: {scalar}"
        else:                                        # sous-clé absente → insérée en tête de bloc
            lines.insert(bi + 1, f"{indent}{sub}: {scalar}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
# <<< meta_set


# Filet de sécurité : tous les clients ont déjà un meta.yml (migration RM1994) ;
# ce gabarit ne sert que si l'un venait à en manquer. Champ Redmine = default_project_id
# (projet parent), conforme au schéma client réel.
_CLIENT_TEMPLATE = """\
# meta.yml client — conf structurée (RM2531). Source de vérité machine, lue par
# pm_paths.client_meta(). Édité via pm-project-config.py (cockpit → catalogue PM).
schema_version: 1.0.0
slug: {slug}
name: {name}
redmine:
  instance: null
  default_project_id: {project_id}
"""


def main():
    ap = argparse.ArgumentParser(description="Édite la conf structurée d'un projet ou d'un client (RM2531).")
    ap.add_argument("--client", required=True)
    ap.add_argument("--project")
    ap.add_argument("--name")
    ap.add_argument("--redmine-project-id", dest="redmine_project_id")
    ap.add_argument("--gitlab-repo", dest="gitlab_repo")
    ap.add_argument("--default-branch", dest="default_branch")
    ap.add_argument("--porcelain", action="store_true", help="imprime le seul chemin écrit")
    args = ap.parse_args()

    cfg = PMConfig.load()

    if args.project:
        meta_path = cfg.path("project", entity=args.client, project=args.project) / "meta.yml"
        if not meta_path.is_file():
            raise SystemExit(f"pm-project-config: meta.yml projet introuvable : {meta_path}")
        updates = _collect_updates(args, PROJECT_FIELDS)
        if not updates:
            raise SystemExit("pm-project-config: aucun champ à modifier")
        new = _meta_set(meta_path.read_text(encoding="utf-8"), updates)
        meta_path.write_text(new, encoding="utf-8")
        scope = f"projet {args.client}/{args.project}"
    else:
        if args.gitlab_repo or args.default_branch:
            raise SystemExit("pm-project-config: --gitlab-repo/--default-branch réservés à un projet (--project requis)")
        client_dir = cfg.path("entity_client_dir", entity=args.client)  # …/.mmi-pm-client/client
        try:
            mmi_client = client_dir.resolve().parent
        except OSError:
            mmi_client = client_dir.parent
        if not mmi_client.is_dir():
            raise SystemExit(f"pm-project-config: client inconnu : {args.client} ({mmi_client})")
        meta_path = mmi_client / "meta.yml"
        updates = _collect_updates(args, CLIENT_FIELDS)
        if not updates:
            raise SystemExit("pm-project-config: aucun champ à modifier")
        if meta_path.is_file():
            new = _meta_set(meta_path.read_text(encoding="utf-8"), updates)
            meta_path.write_text(new, encoding="utf-8")
        else:                                        # filet : client sans meta.yml (rare)
            up = dict(updates)
            meta_path.write_text(_CLIENT_TEMPLATE.format(
                slug=args.client,
                name=_yaml_scalar(up.get("name", args.client)),
                project_id=_yaml_scalar(up["redmine.default_project_id"]) if "redmine.default_project_id" in up else "null",
            ), encoding="utf-8")
        scope = f"client {args.client}"

    pm_git.autocommit([meta_path], f"pm(conf): {scope} (RM2531)")

    if args.porcelain:
        print(meta_path)
    else:
        print(f"✓ conf {scope} mise à jour : {meta_path}")


if __name__ == "__main__":
    main()
