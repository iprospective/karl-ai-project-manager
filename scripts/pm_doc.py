import re
#!/usr/bin/env python3
"""pm_doc — interface DocProvider (gestionnaire de docs agnostique) + backend wiki Redmine.

P3 (RM2545) de la généralisation providers (CDC RM2530 [[Cdc-rm2530-providers-par-projet]]).

Axe **doc** : abstrait le stockage documentaire d'un projet (wiki / GED). Le contrat
générique porte les opérations que tout backend sait faire — get / put d'un document
identifié par (espace, titre) — ; les spécificités Redmine (description native du
projet, versions de page wiki, liens `[[wiki]]`) sont derrière des **capabilities**.

**Backend en P3 : wiki Redmine** (`RedmineWikiDocProvider`), iso avec les primitives
de `pm-wiki-sync` (mêmes endpoints `/projects/{proj}/wiki/{title}.json` et
`/projects/{proj}.json`, via `redmine_utils.http_json`). Un backend **Nextcloud**
(GED, sans versions ni wiki-links → dégradation par capabilities) est la suite de P3.

Le choix d'instance par projet passe par le registre P0 (`pm_registry`) ; la résolution
des creds *par instance* est P4/RM2546. Ce module est **additif** — il n'impose rien à
`pm-wiki-sync`, qui peut y déléguer ses 4 primitives sans changer de comportement.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redmine_utils as _ru
from pm_registry import resolve_instance


class DocProviderError(Exception):
    """Backend de doc manager non supporté / erreur d'I/O documentaire."""


@dataclass(frozen=True)
class DocCapabilities:
    """Ce que le backend doc sait faire au-delà du get/put générique."""
    versioning: bool = False            # versions de document (wiki Redmine)
    wiki_links: bool = False            # liens inter-pages [[wiki]]
    attachments: bool = False           # pièces jointes
    project_description: bool = False   # cible « description native du projet » (Redmine)


class DocProvider:
    """Contrat générique d'un gestionnaire de documents.

    Un document est identifié par un **espace** (`space` — projet/dossier) et un
    **titre** (`title` — page/fichier). Les extras propres à un backend vivent sur
    la sous-classe, gardés par `capabilities`.
    """
    name = "base"
    capabilities = DocCapabilities()

    def __init__(self, instance=None):
        self.instance = instance  # pm_registry.Instance (None en usage direct)

    def get_doc(self, space, title):
        """Retourne (exists: bool, content: str, version). version=None si sans versioning."""
        raise NotImplementedError

    def put_doc(self, space, title, content):
        """Crée/écrase un document. Retourne un statut backend-dépendant."""
        raise NotImplementedError


def wiki_title_for_slug(slug: str) -> str:
    """Identifiant de page wiki dérivé du slug (URL propre, `[[lien]]` stable).

    Décision spec RM1821 §3 : dérivé du **slug**, pas du `title:` frontmatter (qui
    devient le H1). Restreint à `[A-Za-z0-9_-]`, première lettre capitalisée.

    Vit ici depuis RM1890 : `pm-task-doc` doit dériver la MÊME URL que `pm-wiki-sync`
    pour poser le lien du ticket **avant** le premier sync. Deux copies = deux URL le
    jour où la règle bouge.
    """
    clean = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9_-]", "-", slug).strip("-"))
    return clean[:1].upper() + clean[1:] if clean else "Page"


class RedmineWikiDocProvider(DocProvider):
    """Backend wiki Redmine — iso avec les primitives de pm-wiki-sync."""
    name = "redmine_wiki"
    capabilities = DocCapabilities(
        versioning=True, wiki_links=True, attachments=True, project_description=True,
    )

    def _creds(self):
        # Creds globaux actuels (iso pm-wiki-sync) ; creds par instance = P4.
        return _ru.redmine_creds()

    # ── contrat générique ────────────────────────────────────────────────
    def get_doc(self, space, title):
        url, key = self._creds()
        code, body = _ru.http_json("GET", f"{url}/projects/{space}/wiki/{title}.json", key)
        if code == 200:
            wp = body.get("wiki_page", {})
            return True, wp.get("text", ""), wp.get("version")
        if code == 404:
            return False, "", None
        raise DocProviderError(
            f"HTTP {code} GET wiki/{title} (projet {space}) : {body.get('_error', '')}")

    def put_doc(self, space, title, content):
        url, key = self._creds()
        code, body = _ru.http_json("PUT", f"{url}/projects/{space}/wiki/{title}.json", key,
                                   {"wiki_page": {"text": content}})
        if code not in (200, 201, 204):
            raise DocProviderError(
                f"HTTP {code} PUT wiki/{title} (projet {space}) : {body.get('_error', '')}")
        return code

    # ── extras Redmine (gardés par capability project_description) ────────
    def get_project_description(self, space):
        url, key = self._creds()
        code, body = _ru.http_json("GET", f"{url}/projects/{space}.json", key)
        if code != 200:
            raise DocProviderError(
                f"HTTP {code} GET projet {space} : {body.get('_error', '')}")
        return body.get("project", {}).get("description") or ""

    def put_project_description(self, space, text):
        url, key = self._creds()
        code, body = _ru.http_json("PUT", f"{url}/projects/{space}.json", key,
                                   {"project": {"description": text}})
        if code not in (200, 204):
            raise DocProviderError(
                f"HTTP {code} PUT projet {space} : {body.get('_error', '')}")
        return code


_BACKENDS = {"redmine_wiki": RedmineWikiDocProvider}


def get_doc_provider(project_meta=None, registry=None, instance=None):
    """Retourne le `DocProvider` d'un projet.

    Priorité : `instance` explicite > résolution via `registry`/`project_meta` (P0)
    > défaut wiki Redmine (iso-comportement quand aucun registre n'est fourni).
    Lève `DocProviderError` si le type d'instance résolu n'a pas de backend
    (seul 'redmine_wiki' en P3 ; 'nextcloud' = suite).
    """
    if instance is None and registry is not None:
        instance = resolve_instance(project_meta or {}, "doc", registry).instance
    itype = instance.type if instance is not None else "redmine_wiki"
    backend = _BACKENDS.get(itype)
    if backend is None:
        raise DocProviderError(
            f"backend doc '{itype}' non supporté en P3 "
            f"(seul 'redmine_wiki' ; 'nextcloud' = suite P3)")
    return backend(instance)
