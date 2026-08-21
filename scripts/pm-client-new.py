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
    ap.add_argument("--force", action="store_true", help="Écrase si le dossier existe déjà")
    args = ap.parse_args()

    cfg = PMConfig.load()
    client_root = cfg.path("entity", entity=args.slug)
    if client_root.exists() and not args.force:
        sys.exit(f"ERREUR : {client_root} existe déjà (utiliser --force pour écraser)")

    for sub in ("client", "memory", "projects", "projects_used"):
        (client_root / sub).mkdir(parents=True, exist_ok=True)

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
    (client_root / "meta.yml").write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    overview = client_root / "client" / "overview.md"
    overview.write_text(
        f"## Description\n<!-- Activité / contexte de {args.name} -->\n\n"
        "## Aspects documentés\n- [overview.md](overview.md)\n\n"
        "## Notes\n<!-- Décisions, contexte historique -->\n",
        encoding="utf-8",
    )

    print(f"✓ Client {args.slug} ({args.type}) créé :")
    print(f"  {client_root.relative_to(cfg.projects_root)}/")
    print(f"  └── client/overview.md")


if __name__ == "__main__":
    main()
