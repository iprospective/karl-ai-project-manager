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
import shutil
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


# ── KeePass (fichier .kdbx, via pykeepass) — RM2684/L3a ──────────────────────
class KeepassBackend(SecretBackend):
    """Base KeePass locale : un fichier `.kdbx` et une passphrase, aucun serveur.

    C'est le backend le plus autonome — celui qu'un intervenant externe peut
    fournir sans rien installer côté iProspective.

    Déclaration (registre providers, axe `secret`) :
        kdbx-perso: { axis: secret, type: keepass, file: "~/vaults/ipro.kdbx" }
    Le chemin peut aussi venir des identifiants par dev : `SECRET__<SLUG>__FILE`
    (idem `__KEYFILE` pour un fichier-clé). La **passphrase** ne vit qu'en mémoire
    du daemon, fournie à chaque appel comme la session Vaultwarden.

    Chemin d'un secret : `secret://<slug>/<groupe…>/<titre>` — la profondeur est
    libre, KeePass imbriquant les groupes.

    Dépendance **optionnelle** : sans `pykeepass`, l'instance se déclare
    `unreachable` avec la commande d'installation, sans gêner les autres.
    """

    type = "keepass"

    def __init__(self, name="default", session_getter=None, file=None,
                 keyfile=None, **options):
        super().__init__(name=name, **options)
        self._session_getter = session_getter or (lambda: None)
        creds = creds_for(name, legacy=False)
        self._file = file or creds.get("FILE") or ""
        self._keyfile = keyfile or creds.get("KEYFILE") or None

    @property
    def caps(self):
        return Capabilities(needs_unlock=True, listable=True, hierarchical=True)

    # -- accès au fichier ---------------------------------------------------
    def _path(self):
        if not self._file:
            raise UnreachableError(
                "aucun fichier .kdbx : renseigne `file:` dans providers.servers "
                f"ou {creds_env_key(self.name, 'FILE')}", backend=self.name)
        p = os.path.expanduser(self._file)
        if not os.path.isfile(p):
            raise UnreachableError(f"fichier .kdbx introuvable : {p}", backend=self.name)
        return p

    def _open(self):
        """Ouvre la base. La passphrase vient du daemon, jamais du disque.

        La base est rouverte à chaque résolution : c'est quelques centaines de ms
        (dérivation de clé) contre le risque de garder un objet déchiffré vivant.
        Un usage intensif justifierait un cache — pas le nôtre (quelques secrets
        par session).
        """
        # Ordre des diagnostics = ordre dans lequel on les corrige : la
        # configuration d'abord (un chemin manquant ne dépend pas du module),
        # puis la dépendance, puis le déverrouillage.
        path = self._path()
        try:
            from pykeepass import PyKeePass
        except ImportError:
            raise UnreachableError(
                "module `pykeepass` absent — installe-le "
                "(`sudo apt install python3-pykeepass`)", backend=self.name)
        passphrase = self._session_getter()
        if not passphrase:
            raise LockedError("base KeePass verrouillée", backend=self.name)
        keyfile = os.path.expanduser(self._keyfile) if self._keyfile else None
        try:
            return PyKeePass(path, password=passphrase, keyfile=keyfile)
        except Exception as e:  # noqa: BLE001 — pykeepass lève des types variés
            nom = type(e).__name__
            if "Credentials" in nom or "Header" in nom or "password" in str(e).lower():
                raise DeniedError("passphrase (ou fichier-clé) incorrecte",
                                  backend=self.name)
            raise UnreachableError(f"ouverture impossible : {nom}", backend=self.name)

    def status(self):
        try:
            self._path()
        except SecretError:
            return "unreachable"
        try:
            from pykeepass import PyKeePass  # noqa: F401
        except ImportError:
            return "unreachable"
        return "unlocked" if self._session_getter() else "locked"

    def unlock(self, **_):
        """La passphrase est saisie par un humain, comme le mot de passe maître."""
        raise UnsupportedError(
            "déverrouillage humain : lance unlock-vault.sh -i <instance>",
            backend=self.name)

    # -- résolution ---------------------------------------------------------
    def resolve(self, path, field=None):
        if not path:
            raise UriError("aucun item dans le chemin", backend=self.name)
        kp = self._open()
        title = path[-1]
        groups = [g for g in path[:-1] if g]
        entry = self._find(kp, groups, title)
        if entry is None:
            ou = "/".join(path)
            raise NotFoundError(f"entrée introuvable : {ou}", backend=self.name)
        return extract_entry_field(entry, field)

    @staticmethod
    def _find(kp, groups, title):
        """Entrée par titre, filtrée par chemin de groupes s'il en reste un.

        Le chemin est un **suffixe** du groupe réel : `secret://kdbx/acme/db`
        trouve l'entrée « db » du groupe « acme », quelle que soit sa profondeur
        au-dessus — l'URI reste lisible sans rejouer la racine du fichier.
        """
        candidates = kp.find_entries(title=title, first=False) or []
        if not groups:
            return candidates[0] if candidates else None
        want = [g.lower() for g in groups]
        for e in candidates:
            chain = [(g.name or "").lower() for g in _group_chain(e.group)]
            if chain[-len(want):] == want:
                return e
        return None

    def list(self, filt=None):
        kp = self._open()
        out = []
        for e in kp.entries:
            name = e.title or ""
            if filt is not None and filt.lower() not in name.lower():
                continue
            chain = "/".join(g.name for g in _group_chain(e.group) if g.name)
            out.append({"id": str(e.uuid), "org": "-",
                        "collections": [chain] if chain else [], "name": name})
        return out


def _group_chain(group):
    """Groupes de la racine jusqu'à `group` (compatible toutes versions pykeepass)."""
    chain = []
    g = group
    while g is not None:
        chain.append(g)
        g = getattr(g, "parentgroup", None)
    return list(reversed(chain))


def extract_entry_field(entry, field):
    """Champ d'une entrée KeePass, aligné sur le contrat de `extract_field`.

    Sans champ demandé → le mot de passe s'il existe, sinon un résumé JSON de
    l'entrée (jamais le mot de passe s'il est vide : il n'y a rien à cacher).
    """
    props = dict(getattr(entry, "custom_properties", None) or {})
    if field is None:
        if entry.password:
            return entry.password
        return json.dumps({"title": entry.title, "username": entry.username,
                           "url": entry.url, "notes": entry.notes,
                           "fields": sorted(props)}, ensure_ascii=False)
    if field == "password":
        return entry.password or ""
    if field == "username":
        return entry.username or ""
    if field == "notes":
        return entry.notes or ""
    if field == "uri":
        return entry.url or ""
    return props.get(field, "")


# ── Fichier chiffré age (CLI `age`) ──────────────────────────────────────────
class AgeBackend(SecretBackend):
    """Fichier YAML/JSON chiffré avec **age**, déchiffré à la volée en mémoire.

    Le cas « on me partage trois identifiants » : ni serveur, ni compte, ni vault
    à administrer — un fichier chiffré qu'on s'échange et une clé privée sur le
    poste. C'est le backend le plus léger du lot.

    Déclaration (registre providers, axe `secret`) :
        age-acme: { axis: secret, type: age, file: "~/vaults/acme.yml.age" }
    La **clé privée** ne se déclare jamais dans la conf partagée : elle vient des
    identifiants par dev, `SECRET__<SLUG>__AGE_KEY_FILE` (chemin d'un fichier
    d'identité age, à garder en 0600). Le chemin du fichier chiffré peut lui aussi
    venir de `SECRET__<SLUG>__FILE`.

    **sops écarté** (décision RM2713) : pas de paquet Debian — un binaire à
    télécharger depuis GitHub, donc une dépendance qu'`apt` ne sait pas vérifier
    sur chaque poste. Son apport (chiffrement partiel d'un YAML, backends KMS) ne
    sert pas ici : on chiffre le fichier entier, avec la même brique
    cryptographique (age). Un `type: sops` déclaré tombera donc sur « type de
    vault inconnu », avec `age` dans la liste des types connus.

    Pas de déverrouillage interactif : si la clé est lisible, l'instance est
    utilisable — `caps.needs_unlock = False`. C'est le compromis assumé de ce
    backend : la clé dort sur le disque, protégée par les droits du fichier, là
    où Vaultwarden et KeePass exigent une saisie humaine à chaque session.

    Chemin d'un secret : `secret://<slug>/<clé…>[#champ]`, qui suit l'imbrication
    du document. Un chemin qui tombe sur un mapping sans `password` est REFUSÉ
    (`not_found`), avec la liste des clés disponibles — à la différence des autres
    backends, qui rendent `""` pour un champ inconnu. Raison : ici le schéma est
    libre, donc une faute de frappe ne peut pas être distinguée d'un champ vide, et
    une chaîne vide injectée en silence dans une conf est pire qu'une erreur.
    """

    type = "age"

    def __init__(self, name="default", file=None, identity=None, **options):
        super().__init__(name=name, **options)
        creds = creds_for(name, legacy=False)
        self._file = file or creds.get("FILE") or ""
        self._identity = identity or creds.get("AGE_KEY_FILE") or ""

    @property
    def caps(self):
        return Capabilities(needs_unlock=False, listable=True, hierarchical=True)

    # -- accès au fichier ---------------------------------------------------
    def _paths(self):
        """(fichier chiffré, fichier d'identité), tous deux vérifiés."""
        if not self._file:
            raise UnreachableError(
                "aucun fichier chiffré : renseigne `file:` dans providers.servers "
                f"ou {creds_env_key(self.name, 'FILE')}", backend=self.name)
        chiffre = os.path.expanduser(self._file)
        if not os.path.isfile(chiffre):
            raise UnreachableError(f"fichier chiffré introuvable : {chiffre}",
                                   backend=self.name)
        if not self._identity:
            raise UnreachableError(
                f"aucune clé age : renseigne {creds_env_key(self.name, 'AGE_KEY_FILE')} "
                "(chemin d'un fichier d'identité age)", backend=self.name)
        cle = os.path.expanduser(self._identity)
        if not os.path.isfile(cle):
            raise UnreachableError(f"clé age introuvable : {cle}", backend=self.name)
        return chiffre, cle

    def _plaintext(self):
        """Clair du fichier, en mémoire uniquement — jamais écrit sur disque.

        Ordre des diagnostics = ordre dans lequel on les corrige : la
        configuration d'abord (un chemin manquant ne dépend pas du binaire), puis
        la dépendance, puis le déchiffrement lui-même.
        """
        chiffre, cle = self._paths()
        exe = shutil.which("age")
        if not exe:
            raise UnreachableError(
                "binaire `age` absent — installe-le (`sudo apt install age`)",
                backend=self.name)
        try:
            p = subprocess.run([exe, "--decrypt", "-i", cle, chiffre],
                               capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise UnreachableError("`age` n'a pas répondu en 30 s", backend=self.name)
        if p.returncode != 0:
            detail = _derniere_ligne(p.stderr)
            # Classer sur la sortie ENTIÈRE, pas sur la ligne retenue : `age` fait
            # suivre son diagnostic d'une ligne d'invitation à signaler le bug, qui
            # serait la dernière et ne contiendrait aucun des mots-clés.
            brut = (p.stderr or "").lower()
            if "identity" in brut or "recipient" in brut:
                raise DeniedError(f"aucune identité ne déchiffre ce fichier : {detail}",
                                  backend=self.name)
            raise UnreachableError(f"échec de `age --decrypt` : {detail}",
                                   backend=self.name)
        return p.stdout

    def _doc(self):
        """Document déchiffré → mapping Python."""
        txt = self._plaintext()
        try:
            import yaml
        except ImportError:
            try:
                doc = json.loads(txt)
            except ValueError:
                raise UnreachableError(
                    "contenu déchiffré illisible (JSON attendu, `pyyaml` absent)",
                    backend=self.name)
        else:
            try:
                doc = yaml.safe_load(txt)
            except Exception as e:  # noqa: BLE001 — pyyaml lève des types variés
                # Un message de parseur CITE la ligne fautive : il ne doit JAMAIS
                # ressortir, il contiendrait du clair (tripwire 11). Type seul.
                raise UnreachableError(
                    f"contenu déchiffré illisible ({type(e).__name__})",
                    backend=self.name)
        if not isinstance(doc, dict):
            raise UnreachableError(
                "le fichier déchiffré doit être un mapping YAML/JSON (clé → valeur)",
                backend=self.name)
        return doc

    def status(self):
        try:
            self._paths()
        except SecretError:
            return "unreachable"
        return "unlocked" if shutil.which("age") else "unreachable"

    def unlock(self, **_):
        raise UnsupportedError(
            "rien à déverrouiller : la clé age est un fichier "
            f"({creds_env_key(self.name, 'AGE_KEY_FILE')}) — protège-le en 0600",
            backend=self.name)

    # -- résolution ---------------------------------------------------------
    def resolve(self, path, field=None):
        if not path:
            raise UriError("aucun item dans le chemin", backend=self.name)
        node = self._doc()
        parcouru = []
        for seg in path:
            if not isinstance(node, dict) or seg not in node:
                ou = "/".join(parcouru) or "(racine)"
                raise NotFoundError(f"clé {seg!r} absente sous {ou} — "
                                    f"présentes : {_cles_dispo(node)}",
                                    backend=self.name)
            node = node[seg]
            parcouru.append(seg)
        ou = "/".join(parcouru)
        if isinstance(node, dict):
            if field is not None:
                if field not in node:
                    raise NotFoundError(f"champ {field!r} absent de {ou} — "
                                        f"présents : {_cles_dispo(node)}",
                                        backend=self.name)
                return _valeur_texte(node[field])
            if "password" in node:
                return _valeur_texte(node["password"])
            raise NotFoundError(
                f"{ou} est un groupe, pas une valeur — précise un champ "
                f"(#champ) parmi : {_cles_dispo(node)}", backend=self.name)
        if field is not None:
            raise NotFoundError(f"{ou} est une valeur simple : pas de champ {field!r}",
                                backend=self.name)
        return _valeur_texte(node)

    def list(self, filt=None):
        out = []
        for chemin in _age_records(self._doc()):
            nom = chemin[-1]
            if filt is not None and filt.lower() not in nom.lower():
                continue
            groupes = "/".join(chemin[:-1])
            out.append({"id": "/".join(chemin), "org": "-",
                        "collections": [groupes] if groupes else [], "name": nom})
        return sorted(out, key=lambda r: r["id"])


# `age` termine ses erreurs par une invitation à signaler le bug. Elle serait la
# « dernière ligne » et masquerait le vrai diagnostic — on l'écarte.
_AGE_BOILERPLATE = "report unexpected or unhelpful errors"


def _derniere_ligne(txt, limite=200):
    """Dernière ligne UTILE d'une sortie d'erreur, bornée. Jamais de clair :
    `age` écrit ses diagnostics sur stderr, le déchiffré part sur stdout."""
    lignes = [l.strip() for l in (txt or "").splitlines()
              if l.strip() and _AGE_BOILERPLATE not in l]
    return (lignes[-1] if lignes else "sans message")[:limite]


def _cles_dispo(node, limite=12):
    """Clés d'un mapping, pour guider l'appelant. Des NOMS, jamais des valeurs."""
    if not isinstance(node, dict):
        return "(valeur simple)"
    cles = sorted(node)
    if not cles:
        return "(aucune)"
    if len(cles) > limite:
        return ", ".join(cles[:limite]) + f", … (+{len(cles) - limite})"
    return ", ".join(cles)


def _valeur_texte(v):
    """Valeur du document → texte, tel qu'un appelant shell l'attend."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)


def _age_records(node, prefix=()):
    """Chemins « enregistrement » du document, pour `list()`.

    Un enregistrement = un mapping dont toutes les valeurs sont scalaires (le cas
    courant : un item avec ses champs), ou un scalaire isolé au milieu de
    sous-mappings. On ne rend que des CHEMINS — jamais les valeurs.
    """
    if not isinstance(node, dict):
        if prefix:
            yield prefix
        return
    sous = {k: v for k, v in node.items() if isinstance(v, dict)}
    if not sous:
        if prefix:
            yield prefix
        return
    for k, v in node.items():
        if isinstance(v, dict):
            yield from _age_records(v, prefix + (k,))
        else:
            yield prefix + (k,)


# ── Nextcloud Passwords (API REST de l'app `passwords`) ──────────────────────
class NextcloudPasswordsBackend(SecretBackend):
    """Coffre d'une instance Nextcloud portant l'app **Passwords**.

    C'est le backend du cas « le client a déjà son gestionnaire, et c'est celui
    de son Nextcloud » — chez Matériaux Naturels notamment, où l'outillage PM est
    destiné à tourner.

    Déclaration (registre providers, axe `secret`) :
        ncpw-matnat: { axis: secret, type: nextcloud_passwords,
                       url: "https://cloud.materiaux-naturels.fr" }
    Identifiants par dev, jamais dans la conf partagée :
        SECRET__<SLUG>__USER    compte Nextcloud
        SECRET__<SLUG>__TOKEN   **mot de passe d'application** (pas le mot de
                                passe du compte : révocable, à portée limitée)

    Chemin d'un secret : `secret://<slug>/<dossier…>/<label>[#champ]`. Les
    dossiers de l'app sont un arbre ; le chemin donné est un **suffixe** du chemin
    réel, comme pour KeePass — l'URI reste lisible sans rejouer la racine.

    **Chiffrement côté client (CSE/E2E)** : l'app sait chiffrer un item avec une
    clé que seul le navigateur détient. L'API rend alors un cryptogramme, pas le
    secret. Plutôt que de livrer cette valeur — un agent la prendrait pour un mot
    de passe et l'injecterait dans une conf —, on REFUSE explicitement en disant
    quoi faire. C'est le risque que l'étude (CDC § 6) demandait de traiter.
    """

    type = "nextcloud_passwords"
    API = "/index.php/apps/passwords/api/1.0"

    def __init__(self, name="default", url=None, timeout=20, **options):
        super().__init__(name=name, **options)
        creds = creds_for(name, legacy=False)
        self._url = (url or creds.get("URL") or "").rstrip("/")
        self._user = creds.get("USER") or ""
        self._token = creds.get("TOKEN") or ""
        self._timeout = int(timeout)
        self._session = None          # jeton de session API, en mémoire seulement

    @property
    def caps(self):
        return Capabilities(needs_unlock=False, listable=True, hierarchical=True)

    # -- transport ----------------------------------------------------------
    def _check_conf(self):
        if not self._url:
            raise UnreachableError(
                "aucune URL : renseigne `url:` dans providers.servers ou "
                f"{creds_env_key(self.name, 'URL')}", backend=self.name)
        if not self._user or not self._token:
            manque = [creds_env_key(self.name, s) for s, v in
                      (("USER", self._user), ("TOKEN", self._token)) if not v]
            raise UnreachableError(
                "identifiants absents : renseigne " + ", ".join(manque) +
                " (mot de passe d'application Nextcloud)", backend=self.name)

    def _call(self, endpoint, payload=None, with_session=True):
        """Un appel d'API. Rend le JSON décodé. Ne journalise JAMAIS le jeton."""
        import base64
        import urllib.error
        import urllib.request

        self._check_conf()
        url = f"{self._url}{self.API}/{endpoint}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data,
                                     method="POST" if data is not None else "GET")
        jeton = base64.b64encode(f"{self._user}:{self._token}".encode()).decode()
        req.add_header("Authorization", f"Basic {jeton}")
        req.add_header("Accept", "application/json")
        req.add_header("OCS-APIRequest", "true")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if with_session and self._session:
            req.add_header("X-API-SESSION", self._session)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                corps = r.read().decode("utf-8", errors="replace")
                jeton_session = r.headers.get("X-API-SESSION")
                if jeton_session:
                    self._session = jeton_session
        except urllib.error.HTTPError as e:
            raise self._erreur_http(e.code, endpoint)
        except Exception as e:  # noqa: BLE001 — URLError, socket.timeout, ssl…
            raise UnreachableError(
                f"{self._url} injoignable ({type(e).__name__})", backend=self.name)
        if not corps.strip():
            return {}
        try:
            return json.loads(corps)
        except ValueError:
            # Une page de login HTML, un proxy… : ne PAS recopier le corps, il peut
            # contenir n'importe quoi. Le code de statut a déjà dit l'essentiel.
            raise UnreachableError(
                f"réponse non-JSON de {endpoint} — l'app Passwords est-elle "
                "installée et l'URL exacte ?", backend=self.name)

    def _erreur_http(self, code, endpoint):
        if code in (401, 403):
            return DeniedError(
                "identifiants refusés (compte ou mot de passe d'application) — "
                f"vérifie {creds_env_key(self.name, 'USER')} / "
                f"{creds_env_key(self.name, 'TOKEN')}", backend=self.name)
        if code == 404:
            return NotFoundError(
                f"route {endpoint} absente — app Passwords non installée sur "
                f"{self._url} ?", backend=self.name)
        if code == 412:
            # L'app impose d'ouvrir une session, et l'ouverture demande un secret
            # que seul un humain détient (mot de passe maître de l'app).
            return LockedError(
                "l'instance exige une session déverrouillée par un humain "
                "(mot de passe maître de l'app Passwords) — non automatisable",
                backend=self.name)
        return UnreachableError(f"HTTP {code} sur {endpoint}", backend=self.name)

    def _ouvrir_session(self):
        """Ouvre une session API quand l'instance n'exige aucun défi humain."""
        if self._session:
            return
        infos = self._call("session/request", with_session=False)
        exige = infos.get("challenge") or infos.get("token")
        if exige:
            raise LockedError(
                "cette instance demande un défi de session (mot de passe maître "
                "ou 2ᵉ facteur) que seul un humain peut fournir", backend=self.name)
        self._call("session/open", payload={}, with_session=False)

    # -- lecture ------------------------------------------------------------
    def status(self):
        try:
            self._check_conf()
        except SecretError:
            return "unreachable"
        try:
            self._call("session/request", with_session=False)
        except DeniedError:
            return "locked"          # joignable, mais les identifiants sont refusés
        except SecretError:
            return "unreachable"
        return "unlocked"

    def unlock(self, **_):
        raise UnsupportedError(
            "rien à déverrouiller : l'accès passe par un mot de passe "
            f"d'application ({creds_env_key(self.name, 'TOKEN')})", backend=self.name)

    def _dossiers(self):
        """{id: chemin} des dossiers, racine comprise."""
        brut = self._call("folder/list", payload={"details": "model"})
        par_id = {}
        for f in brut if isinstance(brut, list) else []:
            par_id[f.get("id")] = (f.get("label") or "", f.get("parent"))
        chemins = {}

        def chemin(fid, vus=()):
            if fid in chemins:
                return chemins[fid]
            if fid not in par_id or fid in vus:      # racine, inconnu, ou cycle
                return ""
            label, parent = par_id[fid]
            haut = chemin(parent, vus + (fid,)) if parent else ""
            chemins[fid] = f"{haut}/{label}" if haut else label
            return chemins[fid]

        return {fid: chemin(fid) for fid in par_id}

    def _items(self):
        """(item, chemin de dossier) pour chaque mot de passe visible."""
        self._ouvrir_session()
        dossiers = self._dossiers()
        brut = self._call("password/list", payload={"details": "model"})
        for it in brut if isinstance(brut, list) else []:
            yield it, dossiers.get(it.get("folder"), "")

    def resolve(self, path, field=None):
        if not path:
            raise UriError("aucun item dans le chemin", backend=self.name)
        label = path[-1]
        vise = [s for s in path[:-1] if s]
        trouve = None
        homonymes = 0
        for it, dossier in self._items():
            if (it.get("label") or "") != label:
                continue
            homonymes += 1
            segs = [s for s in dossier.split("/") if s]
            if vise and segs[-len(vise):] != vise:
                continue
            trouve = it
            break
        if trouve is None:
            ou = "/".join(path)
            indice = (f" ({homonymes} item(s) portent ce label, dans d'autres "
                      f"dossiers)" if homonymes else "")
            raise NotFoundError(f"item introuvable : {ou}{indice}", backend=self.name)
        cse = trouve.get("cseType") or "none"
        if cse != "none":
            raise UnsupportedError(
                f"« {label} » est chiffré côté client (cseType={cse}) : l'API n'en "
                "rend qu'un cryptogramme. Déplace-le hors du chiffrement client, ou "
                "utilise un autre coffre pour ce secret", backend=self.name)
        return extract_nc_field(trouve, field)

    def list(self, filt=None):
        out = []
        for it, dossier in self._items():
            nom = it.get("label") or ""
            if filt is not None and filt.lower() not in nom.lower():
                continue
            out.append({"id": str(it.get("id") or ""), "org": "-",
                        "collections": [dossier] if dossier else [], "name": nom})
        return sorted(out, key=lambda r: (r["collections"], r["name"]))


def extract_nc_field(item, field):
    """Champ d'un item Passwords, aligné sur le contrat des autres backends.

    Sans champ demandé → le mot de passe, sinon un résumé JSON de l'item (jamais
    de valeur sensible : des noms de champs).
    """
    perso = {}
    brut = item.get("customFields")
    if isinstance(brut, str) and brut.strip():
        try:
            brut = json.loads(brut)
        except ValueError:
            brut = []
    if isinstance(brut, list):                   # [{label, type, value}, …]
        perso = {c.get("label"): c.get("value") for c in brut if isinstance(c, dict)}
    elif isinstance(brut, dict):
        perso = dict(brut)

    if field is None:
        if item.get("password"):
            return item["password"]
        return json.dumps({"label": item.get("label"), "username": item.get("username"),
                           "url": item.get("url"), "fields": sorted(k for k in perso)},
                          ensure_ascii=False)
    if field == "password":
        return item.get("password") or ""
    if field == "username":
        return item.get("username") or ""
    if field == "notes":
        return item.get("notes") or ""
    if field == "uri":
        return item.get("url") or ""
    return perso.get(field, "") or ""


# ── 1Password (CLI `op`, service account) — RM2711/L3b ───────────────────────
class OnePasswordBackend(SecretBackend):
    """1Password via la CLI `op` v2, authentifiée par un **service account**.

    Déclaration (registre providers, axe `secret`) :
        op-ipro: { axis: secret, type: onepassword, vault: "Agents" }
    `vault:` est le coffre par défaut ; il reste surchargeable par l'URI.

    Le jeton du service account ne se déclare JAMAIS dans le registre : il vit
    dans le `.env` du dev, sous `SECRET__<SLUG>__SERVICE_ACCOUNT_TOKEN`. Il est
    passé à `op` par l'ENVIRONNEMENT (`OP_SERVICE_ACCOUNT_TOKEN`), jamais en
    argument : un argument est lisible par tout le monde dans `ps`.

    Chemin d'un secret : `secret://<slug>/<coffre>/<item>[#champ]`, ou
    `secret://<slug>/<item>` quand `vault:` est déclaré.

    Capabilities : `needs_unlock=False` — le jeton EST la session, il n'y a rien
    à déverrouiller (comme `age` et `nextcloud_passwords`, RM2713/RM2712). Un
    jeton refusé n'est donc pas `locked` mais `denied` : personne ne peut « le
    déverrouiller », il faut en émettre un autre.

    Dépendance **optionnelle** : la CLI `op` n'est pas dans les dépôts Debian
    (paquet 1Password). Absente ⇒ l'instance se déclare `unreachable` avec la
    procédure d'installation, sans gêner les autres coffres.
    """

    type = "onepassword"

    # Le jeton passe par l'environnement ; ces variables-là, au contraire, sont
    # neutralisées : une session `op signin` héritée du shell prendrait le pas
    # sur le service account et l'on résoudrait avec la mauvaise identité.
    _ENV_NEUTRALISEES = ("OP_SESSION", "OP_CONNECT_HOST", "OP_CONNECT_TOKEN")

    def __init__(self, name="default", vault=None, account=None, timeout=30,
                 **options):
        super().__init__(name=name, **options)
        creds = creds_for(name, legacy=False)
        self._vault = vault or creds.get("VAULT") or ""
        self._account = account or creds.get("ACCOUNT") or ""
        # `TOKEN` est toléré en second nom : c'est celui qu'on tape spontanément,
        # et le refuser ne protège rien.
        self._token = (creds.get("SERVICE_ACCOUNT_TOKEN")
                       or creds.get("TOKEN") or "")
        self._timeout = timeout

    @property
    def caps(self):
        return Capabilities(needs_unlock=False, listable=True, hierarchical=True)

    # -- invocation de la CLI -----------------------------------------------
    def _exe(self):
        exe = shutil.which("op")
        if not exe:
            raise UnreachableError(
                "CLI `op` absente — elle n'est pas dans les dépôts Debian : "
                "https://developer.1password.com/docs/cli/get-started/ "
                "(dépôt APT 1Password, paquet `1password-cli`)", backend=self.name)
        return exe

    def _env(self):
        """Environnement de l'appel : le jeton par variable, jamais en argument."""
        if not self._token:
            raise UnreachableError(
                "aucun jeton de service account : renseigne "
                f"{creds_env_key(self.name, 'SERVICE_ACCOUNT_TOKEN')} dans ton .env",
                backend=self.name)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(self._ENV_NEUTRALISEES)}
        env["OP_SERVICE_ACCOUNT_TOKEN"] = self._token
        # Sans cela, `op` peut tenter l'intégration avec l'application de bureau
        # et rester bloquée sur une invite biométrique qu'aucun agent ne verra.
        env["OP_BIOMETRIC_UNLOCK_ENABLED"] = "false"
        return env

    def _op(self, args, timeout=None):
        """`op <args>` avec le service account. Sortie brute, erreurs traduites."""
        exe = self._exe()
        env = self._env()
        argv = [exe, *args]
        if self._account:
            argv += ["--account", self._account]
        try:
            p = subprocess.run(argv, capture_output=True, text=True, env=env,
                               stdin=subprocess.DEVNULL,
                               timeout=timeout or self._timeout)
        except subprocess.TimeoutExpired:
            raise UnreachableError(
                f"`op` n'a pas répondu en {timeout or self._timeout} s",
                backend=self.name)
        if p.returncode != 0:
            raise self._erreur(p.stderr)
        return p.stdout

    def _erreur(self, stderr):
        """Message d'échec de `op` → erreur normalisée.

        Classé sur la sortie ENTIÈRE, pas sur sa dernière ligne : `op` préfixe
        ses diagnostics (`[ERROR] <horodatage> …`) et peut les faire suivre d'une
        ligne d'aide. Retenir « la dernière ligne » avait déjà produit, sur
        `age`, deux diagnostics opposés pour la même cause (RM2713).
        """
        brut = (stderr or "").lower()
        detail = _derniere_ligne_op(stderr)
        if any(m in brut for m in (
                "isn't an item", "isn't a vault", "no item matching",
                "no vault matching", "not found", "doesn't exist")):
            classe = NotFoundError
        # Le réseau AVANT l'autorisation : un échec de connexion mentionne
        # souvent le point d'accès du service account, et serait sinon rapporté
        # comme un jeton refusé — on enverrait le lecteur en émettre un nouveau
        # pour rien.
        elif any(m in brut for m in (
                "connect", "network", "dns", "no such host", "timed out",
                "unreachable", "tls", "certificate")):
            classe = UnreachableError
        elif any(m in brut for m in (
                "unauthorized", "forbidden", "access denied", "not allowed",
                "authentication required", "no account found", "invalid token",
                "token is invalid", "invalid service account token", "expired",
                "401", "403")):
            classe = DeniedError
        else:
            classe = SecretError
        return classe(detail, backend=self.name)

    # -- état ---------------------------------------------------------------
    def status(self):
        """'unlocked' | 'locked' | 'unreachable' — les trois valeurs du contrat.

        Un jeton refusé se rapporte en `locked` : joignable, mais l'accès n'est
        pas accordé. `unlock-vault.sh` le traduit en clair — il faut un AUTRE
        jeton, il n'y a rien à déverrouiller ici.
        """
        try:
            self._exe()
            self._env()
        except SecretError:
            return "unreachable"
        try:
            self._op(["whoami", "--format", "json"], timeout=min(self._timeout, 15))
        except DeniedError:
            return "locked"
        except SecretError:
            return "unreachable"
        return "unlocked"

    def unlock(self, **_):
        raise UnsupportedError(
            "rien à déverrouiller : l'accès passe par un jeton de service account "
            f"({creds_env_key(self.name, 'SERVICE_ACCOUNT_TOKEN')}) — pour le "
            "changer, émets-en un nouveau depuis 1Password", backend=self.name)

    # -- résolution ---------------------------------------------------------
    def _cible(self, path):
        """(coffre, item) depuis le chemin de l'URI, `vault:` en repli."""
        segs = [s for s in path if s]
        if not segs:
            raise UriError("aucun item dans le chemin", backend=self.name)
        item = segs[-1]
        amont = segs[:-1]
        if amont:
            # 1Password n'imbrique pas les coffres : le segment utile est le
            # dernier avant l'item. On ignore ce qui précède plutôt que de
            # refuser une URI écrite avec la profondeur d'un autre backend.
            return amont[-1], item
        if not self._vault:
            raise UriError(
                "coffre non précisé : écris secret://<slug>/<coffre>/<item> ou "
                "déclare `vault:` sur l'instance", backend=self.name)
        return self._vault, item

    def resolve(self, path, field=None):
        coffre, item = self._cible(path)
        out = self._op(["item", "get", item, "--vault", coffre, "--format", "json"])
        try:
            item_json = json.loads(out)
        except ValueError:
            raise UnreachableError("réponse `op` illisible (JSON attendu)",
                                   backend=self.name)
        return extract_op_field(item_json, field)

    def list(self, filt=None):
        coffres = [self._vault] if self._vault else [
            v.get("name") or v.get("id") for v in self._coffres()]
        out = []
        for coffre in [c for c in coffres if c]:
            brut = self._op(["item", "list", "--vault", coffre, "--format", "json"])
            try:
                items = json.loads(brut or "[]")
            except ValueError:
                raise UnreachableError("réponse `op` illisible (JSON attendu)",
                                       backend=self.name)
            for it in items if isinstance(items, list) else []:
                nom = it.get("title") or ""
                if filt is not None and filt.lower() not in nom.lower():
                    continue
                out.append({"id": str(it.get("id") or ""), "org": "-",
                            "collections": [coffre], "name": nom})
        return sorted(out, key=lambda r: (r["collections"], r["name"]))

    def _coffres(self):
        try:
            brut = json.loads(self._op(["vault", "list", "--format", "json"]) or "[]")
        except ValueError:
            raise UnreachableError("réponse `op` illisible (JSON attendu)",
                                   backend=self.name)
        return brut if isinstance(brut, list) else []


_OP_PREFIXE = ("[error]", "[warn]", "[info]")


def _derniere_ligne_op(txt, limite=200):
    """Diagnostic lisible extrait de la sortie d'erreur de `op`.

    On garde la PREMIÈRE ligne d'erreur (celle qui dit la cause) débarrassée de
    son préfixe `[ERROR] <date> <heure> `, et non la dernière : `op` termine
    volontiers par une ligne d'usage qui ne dit rien du problème.
    """
    for ligne in (txt or "").splitlines():
        l = ligne.strip()
        if not l:
            continue
        if l.lower().startswith(_OP_PREFIXE):
            # `[ERROR] 2026/08/27 10:15:42 message…` → `message…`
            morceaux = l.split(None, 3)
            l = morceaux[3] if len(morceaux) >= 4 else l
        return l[:limite]
    return "sans message"


def extract_op_field(item_json, field):
    """Champ d'un item 1Password, aligné sur le contrat des autres backends.

    Les champs d'un item `op` portent un `purpose` normalisé (USERNAME,
    PASSWORD, NOTES) pour les trois champs standards, et un `label` libre pour
    les autres. On lit le `purpose` en premier : c'est lui qui est stable, le
    label suivant la langue de l'interface.
    """
    champs = [f for f in (item_json.get("fields") or []) if isinstance(f, dict)]

    def par_purpose(purpose):
        for f in champs:
            if (f.get("purpose") or "").upper() == purpose:
                return f.get("value") or ""
        return ""

    def par_label(nom):
        for f in champs:
            if f.get("label") == nom or f.get("id") == nom:
                return f.get("value") or ""
        return ""

    def uri():
        urls = [u for u in (item_json.get("urls") or []) if isinstance(u, dict)]
        for u in urls:
            if u.get("primary"):
                return u.get("href") or ""
        return urls[0].get("href", "") if urls else ""

    if field is None:
        mdp = par_purpose("PASSWORD")
        if mdp:
            return mdp
        # Pas de mot de passe : un résumé qui ne cite que des NOMS de champs
        # (tripwire 11) — de quoi comprendre quoi demander en `#champ`.
        return json.dumps(
            {"title": item_json.get("title"),
             "vault": (item_json.get("vault") or {}).get("name"),
             "category": item_json.get("category"),
             "fields": sorted(f.get("label") or f.get("id") or "" for f in champs)},
            ensure_ascii=False)
    if field == "password":
        return par_purpose("PASSWORD") or par_label("password")
    if field == "username":
        return par_purpose("USERNAME") or par_label("username")
    if field == "notes":
        return par_purpose("NOTES") or par_label("notesPlain")
    if field == "uri":
        return uri()
    return par_label(field)

# ── Fabrique ─────────────────────────────────────────────────────────────────
# Un type par gestionnaire. Les suivants s'enregistrent ici, ou de l'extérieur
# via `register_backend()`, sans toucher aux appelants.
BACKENDS = {
    VaultwardenBackend.type: VaultwardenBackend,
    KeepassBackend.type: KeepassBackend,
    AgeBackend.type: AgeBackend,
    NextcloudPasswordsBackend.type: NextcloudPasswordsBackend,
    OnePasswordBackend.type: OnePasswordBackend,
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
#     SECRET__<SLUG>__CLIENTID / __CLIENTSECRET   Vaultwarden (clé API)
#     SECRET__<SLUG>__FILE                        KeePass / sops (chemin)
#     SECRET__<SLUG>__TOKEN                       backend en ligne
#
# `<SLUG>` est le slug **normalisé** : majuscules, et tout caractère non
# alphanumérique remplacé par `_` — `vw-ipro` → `SECRET__VW_IPRO__CLIENTID`.
# Raison (RM2683) : un nom de variable shell n'accepte pas les tirets, donc la
# forme littérale `SECRET__vw-ipro__…` ne pouvait ni être sourcée depuis un `.env`
# ni être lue par `${!var}` — elle n'était utilisable que depuis Python. La forme
# littérale reste acceptée en lecture, pour ne pas casser un `.env` déjà écrit.
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


def env_slug(instance):
    """Slug normalisé pour un nom de variable d'environnement (shell-compatible)."""
    return "".join(c if c.isalnum() else "_" for c in str(instance)).upper()


def creds_env_key(instance, suffix):
    """Nom canonique de la variable portant un identifiant d'instance."""
    return f"{CREDS_PREFIX}{env_slug(instance)}__{suffix.upper()}"


def creds_for(instance, env=None, legacy=True):
    """Identifiants déclarés pour une instance : {suffixe: valeur}.

    Lit la forme canonique (slug normalisé) ET la forme littérale, cette dernière
    par tolérance pour un `.env` écrit avant RM2683 ; la canonique gagne.
    `legacy=True` complète avec les variables historiques (BW_CLIENTID…) pour les
    clés absentes — la migration vers les clés par slug reste ainsi opt-in.
    """
    env = os.environ if env is None else env
    out = {}
    # Forme littérale d'abord, la canonique ensuite : elle écrase, donc elle gagne.
    for prefix in (f"{CREDS_PREFIX}{instance}__",
                   f"{CREDS_PREFIX}{env_slug(instance)}__"):
        out.update({k[len(prefix):].upper(): v for k, v in env.items()
                    if k.startswith(prefix) and v not in (None, "")})
    if legacy:
        for suffix, var in LEGACY_CREDS.items():
            if suffix not in out and env.get(var):
                out[suffix] = env[var]
    return out


def creds_keys(instance, env=None, legacy=True):
    """Noms des identifiants disponibles, triés — jamais les valeurs.

    C'est ce qu'un diagnostic peut afficher ou journaliser (tripwire 11)."""
    return sorted(creds_for(instance, env=env, legacy=legacy))
