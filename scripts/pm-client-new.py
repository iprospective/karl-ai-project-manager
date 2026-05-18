#!/usr/bin/env python3
"""pm-client-new — Crée un nouveau client/produit/self dans l'arbo PM.

Usage :
    pm-client-new.py --slug acme --name "Acme Corp" --type client
    pm-client-new.py --slug nextcloud --name "Nextcloud" --type product
    pm-client-new.py --slug lemathou --name "Lemathou" --type self
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

VALID_TYPES = {"client", "product", "self"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True, help="Slug kebab-case du client (= nom du dossier)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--type", default="client", choices=sorted(VALID_TYPES))
    ap.add_argument("--gitlab-group", default="", help="ex: iprospective/nextcloud")
    ap.add_argument("--redmine-default-project", default="", help="Slug Redmine du projet 'parent' par défaut")
    ap.add_argument("--contact-name", default="Mathieu Moulin")
    ap.add_argument("--contact-email", default="mathieu@iprospective.fr")
    ap.add_argument("--force", action="store_true", help="Écrase si le dossier existe déjà")
    args = ap.parse_args()

    cfg = PMConfig.load()
    client_root = cfg.path("entity", entity=args.slug)
    if client_root.exists() and not args.force:
        sys.exit(f"ERREUR : {client_root} existe déjà (utiliser --force pour écraser)")

    for sub in ("client", "memory", "projects", "projects_used"):
        (client_root / sub).mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d")
    fm_lines = [
        '---',
        'schema_version: "1.6.0"',
        f'slug: {args.slug}',
        f'name: {args.name}',
        f'type: {args.type}',
        'status: active',
        f'created: {now}',
        '',
        'contacts:',
        f'  - name: {args.contact_name}',
        f'    email: {args.contact_email}',
        '    role: owner',
        '',
        'defaults:',
        '  priority: normal',
        '  team:',
        '    - username: iprospective',
        '      email: mathieu@iprospective.fr',
        '      role: owner',
        '',
        'gitlab:',
        f'  group: {args.gitlab_group}',
        '  default_branch: main',
        'redmine:',
        '  instance:                    # null → hérite de ${REDMINE_URL}',
        f'  default_project_id: {args.redmine_default_project}',
        '',
        'aspects:',
        '  - overview',
        '---',
        '',
        '## Description',
        f'<!-- Activité / contexte de {args.name} -->',
        '',
        '## Aspects documentés',
        '- [overview.md](overview.md)',
        '',
        '## Notes',
        '<!-- Décisions, contexte historique -->',
    ]
    overview = client_root / "client" / "overview.md"
    overview.write_text("\n".join(fm_lines) + "\n", encoding="utf-8")

    print(f"✓ Client {args.slug} ({args.type}) créé :")
    print(f"  {client_root.relative_to(cfg.projects_root)}/")
    print(f"  └── client/overview.md")


if __name__ == "__main__":
    main()
