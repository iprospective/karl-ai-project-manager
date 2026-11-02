#!/usr/bin/env python3
"""pm_secret_scan — reconnaître un secret dans un texte, sans jamais le recopier (RM3274).

⚠ À ne pas confondre avec `pm_secrets`, qui RÉSOUT des secrets depuis un vault
(RM2681). Celui-ci ne résout rien : il RECONNAÎT, dans du texte, ce qui ressemble
à un secret — et ne rend jamais la valeur qu'il a trouvée.

Extrait du garde de `pm-wiki-sync` (RM2466, corrigé RM2826), qui savait déjà
refuser de publier une page porteuse d'un secret. Le même savoir sert maintenant
à deux endroits : ce garde de publication, et la surveillance du transcript de
session (`pm-secret-watch`), qui signale un secret ayant transité dans un tour
d'agent.

**Le point le plus important de ce module : rien de ce qu'il rend ne contient la
valeur détectée.** Une détection porte un libellé (« jeton GitLab ») et une
empreinte courte (`sha256[:12]`), jamais le secret. Un garde qui recopie dans sa
notification ce qu'il dénonce le propage une fois de plus — dans le fil, dans un
ticket Redmine, dans un journal versionné. L'empreinte suffit à reconnaître deux
occurrences du même secret, et ne permet pas de le reconstituer.

Deux signaux, volontairement distincts :

- `scan()` — **le texte montre** un secret : préfixes connus (`glpat-`, `ghp_`,
  `EAA…` Meta, `sk-…`, `AKIA…`, `AIza…`), mot-clé porteur (`password:`,
  `api_key:`…), clé privée PEM, ou fragment base64 de haute entropie.
- `avowal()` — **l'agent le dit** : « affiché en clair », « token compromis »,
  « à régénérer »… C'est le signal le plus fiable, parce qu'il suppose que
  quelqu'un a compris ce qui venait de se passer. Il rattrape aussi le cas où la
  valeur n'est plus dans la fenêtre lue.

Les faux positifs ont une histoire ici : RM2826 a montré que le motif base64
prenait les chemins de fichiers pour des jetons (`/zfs/workspaces/…/modules/x`),
au point de bloquer la publication d'un CDC. L'heuristique de départage est
conservée telle quelle — elle n'abaisse pas la sensibilité, elle écarte ce qui
n'a jamais été un secret.
"""

import hashlib
import re

# Le seul signal STATISTIQUE : une suite qui a la forme d'un jeton, sans rien qui dise
# lequel. Le plus bruité — il notifie, mais n'ouvre pas de ticket seul (RM3465).
LABEL_HAUTE_ENTROPIE = "jeton haute entropie (≥32c base64)"

# ── Ce qui ressemble à un secret ──────────────────────────────────────────
_RX_BASE64 = re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")

_SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "clé privée PEM"),
    (re.compile(r"(?i)\bpassword\s*[:=]\s*\S+"), "password: <valeur>"),
    (re.compile(r"(?i)\bpasswd\s*[:=]\s*\S+"), "passwd: <valeur>"),
    (re.compile(r"(?i)\bsecret\s*[:=]\s*\S+"), "secret: <valeur>"),
    (re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*\S+"), "api_key: <valeur>"),
    # Jetons de forge, ancrés sur leur préfixe (RM2826). Le motif base64 ne les
    # voit pas : `_` et `-` cassent la classe de caractères, si bien que `\b…{32,}`
    # n'y trouve jamais 32 caractères contigus.
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}"), "jeton GitLab (glpat-)"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "jeton GitHub (ghp_/gho_/ghu_/ghs_/ghr_)"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "jeton GitHub à portée fine"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "jeton Slack (xox…-)"),
    # RM3274 — les fournisseurs rencontrés en séance. Meta d'abord : c'est lui qui
    # a motivé ce module (RM3273, un FPA_TOKEN_API affiché par un SELECT non filtré).
    (re.compile(r"\bEAA[A-Za-z0-9]{40,}"), "jeton Meta/Facebook (EAA…)"),
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"), "clé d'API modèle (sk-…)"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "clé d'accès AWS (AKIA…)"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "clé d'API Google (AIza…)"),
    (re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S{16,}"), "en-tête Authorization: Bearer"),
]

# Un segment de chemin plausible : un nom de fichier ou de dossier, pas un blob.
_RX_SEGMENT_CHEMIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@+-]*\Z")


def _ressemble_a_un_chemin(fragment):
    """Le fragment capté par le motif base64 est-il en réalité un chemin ? (RM2826)

    Le motif accepte le `/`, légitime en base64 — du coup tout chemin un peu long
    devenait un « jeton haute entropie ». Départage : un vrai jeton est une suite
    CONTIGUË de 32 caractères ou plus. Si l'on découpe sur les `/` et que chaque
    morceau est un nom plausible — de moins de 32 caractères, ou sans aucun chiffre
    (un long nom de classe PHP, RM3465) — c'était un chemin.
    """
    if "/" not in fragment:
        return False
    segments = [seg for seg in fragment.split("/") if seg]
    if len(segments) < 2:
        return False
    return all((len(seg) < 32 or not _RX_CHIFFRE.search(seg)) and _RX_SEGMENT_CHEMIN.match(seg)
               for seg in segments)


# ── Ce qui n'en a que l'air (RM3465) ──────────────────────────────────────
# Rejoué sur une séance PrestaShop, le motif base64 a ouvert trois tickets de rotation
# sur 32 valeurs dont AUCUNE n'était un secret : hash git, noms de classes, fichiers de
# cache, jetons d'URL du back-office, DSN Sentry public. Chaque règle ci-dessous écarte
# une de ces familles par son CONTEXTE — jamais l'hexadécimal en bloc : une clé d'API
# Redmine fait 40 caractères hexadécimaux, exactement comme un hash de commit.
_RX_CHIFFRE = re.compile(r"\d")
_RX_HEXA = re.compile(r"[0-9a-f]+\Z")
# Après le fragment : une extension de fichier (`<md5>.php`, `Controller.php:74`).
_RX_SUIVI_FICHIER = re.compile(r"\.(?:php|tpl|twig|js|ts|css|scss|json|ya?ml|md|py|sh|meta|"
                               r"html?|xml|txt|log|lock|sql|csv)\b")
# Avant le fragment : un jeton d'URL du back-office PrestaShop (`?controller=…&token=`),
# anti-CSRF par employé et contrôleur, présent dans toutes les URL de l'admin.
_RX_PRECEDE_TOKEN_URL = re.compile(r"[?&]_?token=\Z")
# Autour : la clé PUBLIQUE d'un DSN Sentry (`https://<clé>@oNNN.ingest.sentry.io/…`).
_RX_PRECEDE_DSN = re.compile(r"https?://\Z")
_RX_SUIVI_DSN = re.compile(r"@[\w.-]*sentry\.io")
# Autour du fragment, on parle de git : un hexadécimal y est un hash de commit, pas une clé.
# Fenêtre et non ligne : `git log` met le hash sous « Merge branch… », `rev-parse` seul sur
# sa ligne ; une clé Redmine (40 hexa aussi) n'est pas entourée de ce vocabulaire.
_RX_LIGNE_GIT = re.compile(r"(?i)\b(?:commit|submodule|sous-module|heads/|HEAD|merge|rebase|"
                           r"checked out|extrait|rev-parse|ls-tree|ls-remote|refs/|reflog|"
                           r"cherry-pick|fast-forward|git)\b")


_FENETRE_GIT = 160
# Après le fragment : un appel de code (`ComposerAutoloaderInit<hash>::getLoader()`).
_RX_SUIVI_CODE = re.compile(r"(?:::|->|\()")
# Avant le fragment : une variable qui annonce un hash (`EXPECTED_SHA=`, `sha: `).
_RX_PRECEDE_SHA = re.compile(r"(?i)sha\w*\s*[=:]\s*['\"]?\Z")
# Au-delà, c'est un blob (image ou fichier encodé dans une sortie d'outil), pas un jeton.
# Une clé privée PEM, seul secret aussi long, a son propre motif ci-dessus.
_LONGUEUR_BLOB = 512


def _faux_jeton(body, m):
    """Le fragment `m` (motif base64) a-t-il seulement l'air d'un secret ? (RM3465)"""
    frag = m.group(0)
    avant, apres = body[max(0, m.start() - 40):m.start()], body[m.end():m.end() + 80]
    if _ressemble_a_un_chemin(frag):
        return True
    if not _RX_CHIFFRE.search(frag):
        return True                       # identifiant de code (nom de classe, de méthode)
    if _RX_SUIVI_FICHIER.match(apres):
        return True                       # nom de fichier : cache `<md5>.php`, `X.php:74`
    if _RX_PRECEDE_TOKEN_URL.search(avant):
        return True                       # jeton d'URL du back-office PrestaShop
    if _RX_PRECEDE_DSN.search(avant) and _RX_SUIVI_DSN.match(apres):
        return True                       # clé publique d'un DSN Sentry
    if len(frag) > _LONGUEUR_BLOB:
        return True                       # blob encodé (capture d'écran…)
    if _RX_SUIVI_CODE.match(apres):
        return True                       # classe générée appelée dans une pile d'appels
    if _RX_HEXA.match(frag) and (_RX_PRECEDE_SHA.search(avant) or _RX_LIGNE_GIT.search(
            body[max(0, m.start() - _FENETRE_GIT):m.end() + _FENETRE_GIT])):
        return True                       # hash git dans une sortie ou un script git
    return False


def _jetons_haute_entropie(body):
    """Les fragments base64 du corps qui ont l'air d'un secret ET n'en sont pas un faux."""
    return [m.group(0) for m in _RX_BASE64.finditer(body) if not _faux_jeton(body, m)]


# Valeur d'un mot-clé porteur (`secret: …`, `password=…`) qui n'en est pas une (RM3465) :
# un gabarit (`<valeur>`, `${VAR}`, `%s`), un URI de coffre (`secret://<instance>/…`,
# la syntaxe documentée de pm_secrets), une valeur vide ou booléenne.
_RX_VALEUR_FACTICE = re.compile(r"""(?ix) ^ (?: [<${%…] | // | `
    | (?:null|none|true|false|~|""|'')(?:\W|$) )""")
# `secret: <nom>` dans la configuration PM désigne une INSTANCE de coffre, pas sa valeur ;
# `secret:<chemin>` (sans espace) est la forme URI de pm_secrets — une RÉFÉRENCE au coffre.
_RX_SECRET_INSTANCE = re.compile(r"(?i)^secret\s*:\s*[a-z][a-z_-]*$|^secret:\S")


# `un secret : …` — la typographie française (espace AVANT les deux-points) est de la prose ;
# ni YAML, ni .env, ni en-tête HTTP ne l'écrivent ainsi.
_RX_PROSE = re.compile(r"^\w+\s+:")


def _valeur_factice(match):
    valeur = re.split(r"[:=]\s*", match, maxsplit=1)[-1]
    return bool(_RX_VALEUR_FACTICE.match(valeur) or _RX_SECRET_INSTANCE.match(match)
                or _RX_PROSE.match(match))


def fingerprint(value):
    """Empreinte courte et non réversible d'une valeur — jamais la valeur elle-même."""
    return hashlib.sha256(str(value).encode("utf-8", "replace")).hexdigest()[:12]


def scan(text):
    """Détections dans `text` : [{"label": …, "fingerprint": …}], sans aucune valeur.

    Dédoublonné par (libellé, empreinte) : un même secret répété dans le tour ne
    compte qu'une fois, sinon un transcript qui répète un jeton dix fois produirait
    dix alertes pour un seul incident.
    """
    text = text or ""
    hits, seen = [], set()

    def ajoute(label, value):
        fp = fingerprint(value)
        if (label, fp) in seen:
            return
        seen.add((label, fp))
        hits.append({"label": label, "fingerprint": fp})

    for rx, label in _SECRET_PATTERNS:
        for m in rx.finditer(text):
            if not _valeur_factice(m.group(0)):
                ajoute(label, m.group(0))
    for fragment in _jetons_haute_entropie(text):
        ajoute(LABEL_HAUTE_ENTROPIE, fragment)
    return hits


def scan_secrets(body, allow_mark=None):
    """Libellés des motifs détectés — forme attendue par le garde de `pm-wiki-sync`.

    `allow_mark` : marque qui, présente dans le corps, désarme le garde (la page
    assume de montrer ce qui ressemble à un secret). Volontairement sans valeur par
    défaut : désarmer une détection doit être un choix explicite de l'appelant.
    """
    if allow_mark and allow_mark in (body or ""):
        return []
    labels = []
    for hit in scan(body):
        if hit["label"] not in labels:
            labels.append(hit["label"])
    return labels


# ── Ce que l'agent en dit ─────────────────────────────────────────────────
# Tournures par lesquelles un agent signale lui-même qu'un secret a transité.
# Elles valent signal FORT : les écrire suppose d'avoir compris l'incident. Elles
# rattrapent le cas où la valeur a quitté la fenêtre de texte relue.
_AVOWAL_PATTERNS = [
    (re.compile(r"(?i)\b(affich|montr|list|imprim)\w*\s+(en\s+clair|sans\s+filtr)"), "affiché en clair"),
    (re.compile(r"(?i)\b(secret|token|jeton|cl[ée]|mot\s+de\s+passe|credential)\w*\s+"
                r"(a\s+été\s+)?(expos|compromis|divulgu|fuit|leak)\w*"), "secret exposé"),
    (re.compile(r"(?i)\b(expos|compromis|divulgu)\w*\s+"
                r"(le|la|les|un|une|ce|cette)?\s*(secret|token|jeton|cl[ée]|mot\s+de\s+passe)"), "secret exposé"),
    (re.compile(r"(?i)\b(r[ée]g[ée]n[ée]r|fai\w*\s+tourner|rotat\w*|r[ée]voqu)\w*\s+"
                r"(le|la|ce|cette|ton|votre)?\s*(token|jeton|secret|cl[ée]|mot\s+de\s+passe)"), "rotation demandée"),
    (re.compile(r"(?i)\bpoint\s+de\s+s[ée]curit[ée]\b"), "point de sécurité signalé"),
    (re.compile(r"(?i)\bdans\s+(le|ce|mon)\s+transcript\b"), "transit par le transcript"),
]


def avowal(text):
    """Libellés des tournures par lesquelles l'agent signale lui-même l'incident."""
    text = text or ""
    found = []
    for rx, label in _AVOWAL_PATTERNS:
        if rx.search(text) and label not in found:
            found.append(label)
    return found


def incident(shown_text, said_text=None):
    """Résumé d'incident pour un tour : ce que le texte montre + ce que l'agent dit.

    `shown_text` : tout ce qui a transité (sorties d'outils incluses).
    `said_text`  : la seule réponse de l'agent, où se cherche l'aveu.

    Rend None s'il n'y a rien à signaler. Sinon un dict sans aucune valeur de
    secret : libellés, empreintes, et la raison du déclenchement.
    """
    hits = scan(shown_text)
    said = avowal(said_text if said_text is not None else shown_text)
    if not hits and not said:
        return None
    return {
        "hits": hits,
        "avowal": said,
        "labels": sorted({h["label"] for h in hits}),
        "fingerprints": sorted({h["fingerprint"] for h in hits}),
        # Clé stable d'un même incident : les empreintes des secrets vus, à défaut
        # les tournures d'aveu. Deux tours qui montrent le même jeton donnent la
        # même clé — c'est elle qui empêche d'ouvrir deux tickets de rotation.
        "key": fingerprint("|".join(sorted({h["fingerprint"] for h in hits}) or sorted(said))),
    }
