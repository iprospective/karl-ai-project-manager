#!/usr/bin/env python3
"""pm_secrets — abstraction de gestionnaire de secrets (vault) — RM2681 (L0).

Découple le PM de Vaultwarden : les appelants (`vault-agentd`, `resolve-secret.sh`)
parlent à une interface `SecretBackend` unique ; l'implémentation vient du **type**
déclaré pour l'instance.

Séparation des responsabilités, calquée sur `pm_forge` :
  - `pm_secrets` = primitives *vault* (parser un URI, résoudre un champ, dire si
    c'est verrouillé/injoignable). RIEN de spécifique au PM.
  - les appelants = *politique PM* (quel slug pour quel projet, quand demander un
    déverrouillage humain, quoi journaliser).

`VaultwardenBackend` reproduit EXACTEMENT le comportement historique de
`vault-agentd.py` (RM1747) : `bw get item <item> --session <token>`, extraction de
`login.password` / `login.username` / `notes` / première `uris[].uri` / champ
personnalisé, et repli sur le JSON complet quand aucun champ n'est demandé et que
l'item n'a pas de mot de passe.

Capabilities : tous les vaults ne se ressemblent pas — un fichier KeePass n'a pas
d'organisation, un backend en ligne peut ne pas savoir lister. L'appelant DÉGRADE
d'après `caps` au lieu d'échouer (même principe que `pm_forge` avec Gogs).

**Lecture seule** : le PM lit des secrets, il n'en dépose pas (décision CDC RM2662).

URI — trois formes, toutes acceptées par `parse_uri()` :

    secret://<slug>/<chemin…>[#champ]   instance déclarée explicitement
    secret:<chemin…>[#champ]            instance par défaut (cascade : RM2682/L1)
    vaultwarden://<org>/<coll>/<item>   forme historique, supportée définitivement

Le champ peut aussi être passé hors URI par l'appelant (2ᵉ argument de
`resolve-secret.sh`) ; dans ce cas il l'emporte sur le `#champ` de l'URI.
"""
import json
import os
import subprocess


# ── Erreurs — un code par situation, pour que l'appelant sache quoi dire ──────
class SecretError(Exception):
    """Erreur générique de résolution. `code` sert au mapping des exit codes."""
    code = "error"

    def __init__(self, message, backend=None):
        self.backend = backend
        super().__init__(f"[{backend}] {message}" if backend else message)


class LockedError(SecretError):
    """Le vault est verrouillé — un humain doit le déverrouiller."""
    code = "locked"


class UnreachableError(SecretError):
    """Backend injoignable : CLI absente, fichier manquant, réseau muet."""
    code = "unreachable"


class NotFoundError(SecretError):
    """L'item (ou le champ) n'existe pas dans ce vault."""
    code = "not_found"


class DeniedError(SecretError):
    """Authentifié mais pas autorisé sur cet item."""
    code = "denied"


class UriError(SecretError):
    """URI de secret malformé."""
    code = "bad_uri"


class UnsupportedError(SecretError):
    """Capacité non offerte par ce backend (ex. lister)."""
    code = "unsupported"


# ── Structures légères ───────────────────────────────────────────────────────
class Capabilities:
    """Ce que ce backend sait faire. L'appelant s'y adapte au lieu d'échouer."""

    def __init__(self, needs_unlock=True, listable=False, hierarchical=True,
                 writable=False):
        self.needs_unlock = needs_unlock      # une session/passphrase est requise
        self.listable = listable              # sait énumérer ses items
        self.hierarchical = hierarchical      # organise en collections/groupes
        self.writable = writable              # hors périmètre V1 — toujours False

    def __repr__(self):
        return (f"Capabilities(needs_unlock={self.needs_unlock}, "
                f"listable={self.listable}, hierarchical={self.hierarchical}, "
                f"writable={self.writable})")


class SecretRef:
    """URI de secret analysé.

    `instance` = slug demandé (None si non précisé → instance par défaut).
    `path`     = segments du chemin, du plus général au plus précis. Le dernier
                 segment est l'item ; ce qui précède est un contexte propre au
                 backend (org/collection pour Vaultwarden, groupes pour KeePass).
    `field`    = champ demandé dans l'URI (`#champ`), ou None.
    `scheme`   = scheme d'origine, conservé pour les messages d'erreur.
    """

    def __init__(self, instance, path, field=None, scheme="secret"):
        self.instance = instance
        self.path = tuple(path)
        self.field = field
        self.scheme = scheme

    @property
    def item(self):
        """Dernier segment — l'item lui-même."""
        return self.path[-1] if self.path else ""

    def __eq__(self, other):
        return (isinstance(other, SecretRef)
                and (self.instance, self.path, self.field, self.scheme)
                == (other.instance, other.path, other.field, other.scheme))

    def __repr__(self):
        return (f"SecretRef(instance={self.instance!r}, path={self.path!r}, "
                f"field={self.field!r}, scheme={self.scheme!r})")


def parse_uri(uri):
    """URI de secret → `SecretRef`. Voir les trois formes en tête de module.

    Ne résout rien : ne dit pas si l'instance existe (c'est le registre, RM2682),
    ni si l'item existe (c'est le backend).
    """
    if not isinstance(uri, str) or not uri.strip():
        raise UriError("URI vide")
    raw = uri.strip()

    # `#champ` optionnel, commun aux trois formes.
    field = None
    if "#" in raw:
        raw, field = raw.split("#", 1)
        field = field.strip() or None

    if raw.startswith("vaultwarden://"):
        rest = raw[len("vaultwarden://"):]
        parts = [p for p in rest.split("/") if p != ""]
        if len(parts) != 3:
            raise UriError(
                f"attendu vaultwarden://<org>/<collection>/<item>, reçu {uri!r}")
        # L'instance reste implicite : la forme historique désigne le vault par défaut.
        return SecretRef(None, parts, field, scheme="vaultwarden")

    if raw.startswith("secret://"):
        rest = raw[len("secret://"):]
        parts = [p for p in rest.split("/") if p != ""]
        if len(parts) < 2:
            raise UriError(
                f"attendu secret://<instance>/<chemin…>, reçu {uri!r}")
        return SecretRef(parts[0], parts[1:], field, scheme="secret")

    if raw.startswith("secret:"):
        rest = raw[len("secret:"):]
        parts = [p for p in rest.split("/") if p != ""]
        if not parts:
            raise UriError(f"attendu secret:<chemin…>, reçu {uri!r}")
        return SecretRef(None, parts, field, scheme="secret")

    scheme = raw.split(":", 1)[0] if ":" in raw else raw
    raise UriError(
        f"scheme non reconnu : {scheme!r} — attendus secret://, secret: ou "
        f"vaultwarden:// (reçu {uri!r})")


# ── Interface ────────────────────────────────────────────────────────────────
class SecretBackend:
    """Contrat commun à tous les vaults. Lecture seule."""

    type = "abstract"

    def __init__(self, name="default", **options):
        self.name = name          # slug de l'instance, pour les messages
        self.options = options    # url, file, account… selon le type

    @property
    def caps(self):
        return Capabilities()

    def status(self):
        """'unlocked' | 'locked' | 'unreachable' — jamais d'exception."""
        raise NotImplementedError

    def unlock(self, **credentials):
        """Établit une session. Sémantique propre au backend."""
        raise NotImplementedError

    def resolve(self, path, field=None):
        """Valeur du champ demandé. Lève une sous-classe de `SecretError`."""
        raise NotImplementedError

    def list(self, filt=None):
        """Items visibles, un dict par item. `UnsupportedError` si non listable."""
        raise UnsupportedError("ce backend ne sait pas lister", backend=self.name)


# ── Vaultwarden / Bitwarden (CLI `bw`) ───────────────────────────────────────
class VaultwardenBackend(SecretBackend):
    """Extraction iso-comportement du résolveur historique de `vault-agentd`.

    La session BW n'est PAS stockée ici : le daemon la garde en mémoire et la
    fournit via `session_getter` (appelé à chaque résolution). Le backend reste
    ainsi sans état — donc sans secret à faire fuir.
    """

    type = "vaultwarden"

    def __init__(self, name="default", session_getter=None, timeout=15, **options):
        super().__init__(name=name, **options)
        self._session_getter = session_getter or (lambda: None)
        self._timeout = timeout

    @property
    def caps(self):
        return Capabilities(needs_unlock=True, listable=True, hierarchical=True)

    # -- session ------------------------------------------------------------
    def _session(self):
        session = self._session_getter()
        if not session:
            raise LockedError("vault verrouillé", backend=self.name)
        return session

    def status(self):
        try:
            return "unlocked" if self._session_getter() else "locked"
        except Exception:  # noqa: BLE001 — un statut ne doit jamais lever
            return "unreachable"

    def unlock(self, session=None, **_):
        """Le déverrouillage réel (`bw unlock`) reste dans `unlock-vault.sh` :
        seul un humain saisit le mot de passe maître (tripwire 11)."""
        raise UnsupportedError(
            "déverrouillage humain : lance unlock-vault.sh", backend=self.name)

    # -- résolution ---------------------------------------------------------
    def _bw(self, args, timeout=None):
        """Appelle `bw` avec la session courante. Erreurs traduites en codes."""
        try:
            p = subprocess.run(["bw", *args, "--session", self._session()],
                               capture_output=True, text=True,
                               timeout=timeout or self._timeout)
        except FileNotFoundError:
            raise UnreachableError(
                "CLI `bw` absente (npm i -g @bitwarden/cli)", backend=self.name)
        except subprocess.TimeoutExpired:
            raise UnreachableError("`bw` ne répond pas (timeout)", backend=self.name)
        if p.returncode != 0:
            err = (p.stderr or "").strip()
            low = err.lower()
            if "not found" in low or "could not find" in low:
                raise NotFoundError(err or "item introuvable", backend=self.name)
            if "locked" in low or "session" in low:
                raise LockedError(err or "vault verrouillé", backend=self.name)
            raise SecretError(f"bw failed: {err}", backend=self.name)
        return p.stdout

    def resolve(self, path, field=None):
        # Historique : `bw get item` résout par nom ou UUID ; org et collection
        # de l'URI restent indicatifs (le CLI ne les prend pas en filtre).
        item = path[-1] if path else ""
        if not item:
            raise UriError("aucun item dans le chemin", backend=self.name)
        out = self._bw(["get", "item", item])
        try:
            item_json = json.loads(out)
        except json.JSONDecodeError:
            raise SecretError("réponse `bw` illisible", backend=self.name)
        return extract_field(item_json, field)

    def list(self, filt=None):
        items = json.loads(self._bw(["list", "items"]) or "[]")
        out = []
        for it in items:
            name = it.get("name", "")
            if filt is not None and filt.lower() not in name.lower():
                continue
            out.append({
                "id": it.get("id", ""),
                "org": it.get("organizationId") or "-",
                "collections": it.get("collectionIds") or [],
                "name": name,
            })
        return out

    def sync(self, timeout=60):
        """Rafraîchit le cache local du CLI (`bw sync`)."""
        self._bw(["sync"], timeout=timeout)


def extract_field(item_json, field):
    """Champ d'un item Bitwarden. Comportement historique conservé tel quel :
    sans champ demandé → `login.password` s'il existe, sinon le JSON complet."""
    login = item_json.get("login") or {}
    if field is None:
        if login.get("password"):
            return login["password"]
        return json.dumps(item_json, ensure_ascii=False)
    if field == "password":
        return login.get("password", "")
    if field == "username":
        return login.get("username", "")
    if field == "notes":
        return item_json.get("notes") or ""
    if field == "uri":
        uris = login.get("uris") or []
        return uris[0]["uri"] if uris else ""
    for f in item_json.get("fields") or []:
        if f.get("name") == field:
            return f.get("value", "")
    return ""


# ── Fabrique ─────────────────────────────────────────────────────────────────
# Un type par gestionnaire. Les suivants (keepass RM2684, onepassword,
# nextcloud_passwords, sops) s'enregistrent ici sans toucher aux appelants.
BACKENDS = {
    VaultwardenBackend.type: VaultwardenBackend,
}


def register_backend(cls):
    """Enregistre un type de backend (point d'extension des lots L3x)."""
    BACKENDS[cls.type] = cls
    return cls


def get_backend(type_, name="default", **options):
    """Instancie le backend d'un type déclaré. `UnsupportedError` si inconnu."""
    cls = BACKENDS.get(type_)
    if cls is None:
        known = ", ".join(sorted(BACKENDS)) or "aucun"
        raise UnsupportedError(
            f"type de vault inconnu : {type_!r} (connus : {known})", backend=name)
    return cls(name=name, **options)


# ── Identifiants par instance et par développeur (RM2682/L1) ─────────────────
# Le registre déclare les instances SANS secret ; les identifiants d'accès vivent
# dans le `.env` du dev (`~/.config/mmi-pm/.env`, chargé par pm_paths dans
# os.environ), nommés par slug d'instance :
#
#     SECRET__<slug>__CLIENTID / __CLIENTSECRET   Vaultwarden (clé API)
#     SECRET__<slug>__FILE                        KeePass / sops (chemin)
#     SECRET__<slug>__TOKEN                       backend en ligne
#
# Convention alignée sur RM2546 (`REDMINE__<slug>__API_KEY`). Les valeurs ne sont
# jamais journalisées : seules les CLÉS présentes peuvent l'être.
CREDS_PREFIX = "SECRET__"

# Repli par instance : variables historiques, pour ne rien casser tant qu'un dev
# n'a pas nommé ses clés par slug. Ne concerne que l'instance Vaultwarden livrée.
LEGACY_CREDS = {
    "CLIENTID": "BW_CLIENTID",
    "CLIENTSECRET": "BW_CLIENTSECRET",
    "URL": "VAULT_URL",
}


def creds_for(instance, env=None, legacy=True):
    """Identifiants déclarés pour une instance : {suffixe: valeur}.

    `legacy=True` complète avec les variables historiques (BW_CLIENTID…) pour les
    clés absentes — la migration vers les clés par slug reste ainsi opt-in.
    """
    env = os.environ if env is None else env
    prefix = f"{CREDS_PREFIX}{instance}__"
    out = {k[len(prefix):]: v for k, v in env.items()
           if k.startswith(prefix) and v not in (None, "")}
    if legacy:
        for suffix, var in LEGACY_CREDS.items():
            if suffix not in out and env.get(var):
                out[suffix] = env[var]
    return out


def creds_keys(instance, env=None, legacy=True):
    """Noms des identifiants disponibles, triés — jamais les valeurs.

    C'est ce qu'un diagnostic peut afficher ou journaliser (tripwire 11)."""
    return sorted(creds_for(instance, env=env, legacy=legacy))
