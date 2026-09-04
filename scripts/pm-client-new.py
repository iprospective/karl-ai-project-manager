#!/usr/bin/env python3
"""pm-client-new — Crée un nouveau client/produit/self dans l'arbo PM.

Modèle co-localisé (RM1769, pendant client de RM1942/RM2228) : avec --workspace,
les données client vivent dans `<workspace>/.mmi-pm-client/` (versionnées par le
repo `<client>-core` du workspace) ; côté repo PM, `clients/<slug>/` ne porte que
des symlinks d'index (client, memory, projects_used, workspace) + le dossier
réel `projects/` (lui-même rempli de symlinks par pm-project-new).

Usage :
    pm-client-new.py --slug acme --name "Acme Corp" --type client \\
                     --workspace /zfs/workspaces/acme
    pm-client-new.py --slug nextcloud --name "Nextcloud" --type product
    pm-client-new.py --slug lemathou --name "Lemathou" --type self

Sans --workspace : ancien modèle (tout dans clients/<slug>/), déprécié — un
avertissement est émis.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from pm_paths import PMConfig

VALID_TYPES = {"client", "product", "self"}

# RM2702 — le contact par défaut est le NÔTRE : il se pose chez chaque client et
# n'identifie donc personne. On le découpe au schéma nom/prénom et on le marque.
OWN_DOMAINS = ("iprospective.fr", "iprospective.net")


def _first_name(full: str) -> str:
    return (full or "").strip().split(" ", 1)[0] if full else ""


def _last_name(full: str) -> str:
    parts = (full or "").strip().split(" ", 1)
    return parts[1] if len(parts) > 1 else ""


def _is_internal(email: str) -> bool:
    return (email or "").lower().rsplit("@", 1)[-1] in OWN_DOMAINS


def _symlink(link: Path, target: Path):
    """Crée/remplace un symlink (idempotent)."""
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            return  # ne jamais écraser un vrai dossier par un lien
        link.unlink()
    link.symlink_to(target)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True, help="Slug kebab-case du client (= nom du dossier)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--type", default="client", choices=sorted(VALID_TYPES))
    ap.add_argument("--gitlab-group", default="", help="ex: iprospective/nextcloud")
    ap.add_argument("--redmine-default-project", default="", help="Slug Redmine du projet 'parent' par défaut")
    ap.add_argument("--contact-name", default="Mathieu Moulin")
    ap.add_argument("--contact-email", default="mathieu@iprospective.fr")
    ap.add_argument("--contact-phone", default="", help="Téléphone du contact (RM2702)")
    ap.add_argument("--workspace", default="",
                    help="Racine du workspace client (ex: /zfs/workspaces/acme) — "
                         "active le modèle co-localisé .mmi-pm-client (RM1769)")
    ap.add_argument("--force", action="store_true", help="Écrase si le dossier existe déjà")
    args = ap.parse_args()

    cfg = PMConfig.load()
    client_root = cfg.path("entity", entity=args.slug)
    if client_root.exists() and not args.force:
        sys.exit(f"ERREUR : {client_root} existe déjà (utiliser --force pour écraser)")

    workspace = Path(args.workspace).resolve() if args.workspace else None
    if workspace:
        coloc = workspace / ".mmi-pm-client"
        if coloc.exists() and not args.force:
            sys.exit(f"ERREUR : {coloc} existe déjà (utiliser --force pour écraser)")
        workspace.mkdir(parents=True, exist_ok=True)
        data_root = coloc
        for sub in ("client", "memory", "projects_used"):
            (data_root / sub).mkdir(parents=True, exist_ok=True)
        # navigation workspace ↔ PM (pendant client de `.mmi-pm/workspace` → ..)
        _symlink(data_root / "workspace", Path(".."))
        # côté repo PM : index de symlinks + projects/ réel (rempli par pm-project-new)
        client_root.mkdir(parents=True, exist_ok=True)
        (client_root / "projects").mkdir(exist_ok=True)
        for sub in ("client", "memory", "projects_used"):
            _symlink(client_root / sub, data_root / sub)
        _symlink(client_root / "workspace", workspace)
    else:
        print("⚠ --workspace omis : modèle historique (données dans clients/<slug>/), "
              "co-localisation .mmi-pm-client recommandée (RM1769).", file=sys.stderr)
        data_root = client_root
        for sub in ("client", "memory", "projects", "projects_used"):
            (data_root / sub).mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d")
    # meta.yml (manifeste machine) + overview.md (prose) — RM1994
    meta = {
        "schema_version": "1.6.0",
        "slug": args.slug,
        "name": args.name,
        "type": args.type,
        "status": "active",
        "created": now,
        # RM2702 : schéma nom/prénom/email/téléphone. `internal` marque nos propres
        # adresses — sans quoi le contact posé par défaut ici se confond avec un vrai
        # contact client (et servirait à router du courrier entrant, cf. RM2669).
        "contacts": [
            {"last_name": _last_name(args.contact_name),
             "first_name": _first_name(args.contact_name),
             "email": args.contact_email, "phone": args.contact_phone,
             "role": "owner",
             "internal": _is_internal(args.contact_email)}
        ],
        "defaults": {
            "priority": "normal",
            "team": [
                {"username": "iprospective", "email": "mathieu@iprospective.fr", "role": "owner"}
            ],
        },
        "gitlab": {"group": args.gitlab_group, "default_branch": "main"},
        "redmine": {"instance": None, "default_project_id": args.redmine_default_project},
        "aspects": ["overview"],
    }
    (data_root / "meta.yml").write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    overview = data_root / "client" / "overview.md"
    overview.write_text(
        f"## Description\n<!-- Activité / contexte de {args.name} -->\n\n"
        "## Aspects documentés\n- [overview.md](overview.md)\n\n"
        "## Notes\n<!-- Décisions, contexte historique -->\n",
        encoding="utf-8",
    )

    print(f"✓ Client {args.slug} ({args.type}) créé :")
    if workspace:
        print(f"  données co-localisées : {data_root}/ (client/, memory/, meta.yml, projects_used/, workspace→..)")
        print(f"  index PM : {client_root.relative_to(cfg.projects_root)}/ (symlinks + projects/)")
        print(f"  → penser au repo -core du workspace ({args.slug}-core) : .gitignore norme + commit de .mmi-pm-client/")
    else:
        print(f"  {client_root.relative_to(cfg.projects_root)}/")
        print(f"  └── client/overview.md")


if __name__ == "__main__":
    main()
