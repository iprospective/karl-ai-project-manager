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
    morceau est un nom plausible de moins de 32 caractères, c'était un chemin.
    """
    if "/" not in fragment:
        return False
    segments = [seg for seg in fragment.split("/") if seg]
    if len(segments) < 2:
        return False
    return all(len(seg) < 32 and _RX_SEGMENT_CHEMIN.match(seg) for seg in segments)


def _jetons_haute_entropie(body):
    """Les fragments base64 du corps qui ne sont pas des chemins de fichiers."""
    return [f for f in _RX_BASE64.findall(body) if not _ressemble_a_un_chemin(f)]


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
            ajoute(label, m.group(0))
    for fragment in _jetons_haute_entropie(text):
        ajoute("jeton haute entropie (≥32c base64)", fragment)
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
