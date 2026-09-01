"""redmine_utils — Helpers partagés pour interagir avec l'API Redmine.

Centralise :
- résolution des credentials (.env)
- détection du custom field `IA` (mutex entre tickets Redmine purs et
  tickets PM-trackés, cf. NORMS « Filtrage IA »)
- helpers HTTP simples

Aucune logique métier PM ici — uniquement de l'I/O Redmine.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_REFERENCE_FILE = Path(__file__).resolve().parent.parent / "redmine.reference.yml"
_REFERENCE_CACHE = None

# Fallback minimal si redmine.reference.yml est introuvable/illisible — garde les
# transitions critiques fonctionnelles même sans le fichier de référence.
_FALLBACK_STATUS_IDS = {
    "a_etudier_chiffrer": 8, "etude_chiffrage_en_cours": 14,
    "etude_chiffrage_a_valider": 21, "a_faire": 12,
    "en_cours": 2, "a_tester_dev": 19, "a_tester_demandeur": 9, "a_mep": 3,
    "en_mep": 20, "en_pause": 13, "a_corriger": 11, "ferme": 18,
}
_FALLBACK_STATUS_ALIASES = {"a_tester_verifier": "a_tester_demandeur"}
# Raisons de fermeture → toutes vers le statut `ferme` (id porté par la réf).
_CLOSE_REASONS = ("resolu", "abandonne", "wont_fix", "hors_perimetre", "invalide", "doublon")


def api_ts_local(value, minutes=True):
    """Timestamp API Redmine (UTC, ex. '2026-07-11T10:51:40Z') → heure locale naïve.

    L'API REST renvoie de l'UTC ; tout le reste de l'outillage écrit des
    timestamps naïfs en heure locale (datetime.now()). Convertir ici évite le
    mélange naïf-UTC / naïf-local (RM2237 : `updated` reculé de 2 h au sync).
    Retourne '' si vide ; une valeur non parsable est renvoyée tronquée telle
    quelle (comportement historique).
    """
    s = (value or "").strip()
    width = 16 if minutes else 19
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s.replace("Z", "")[:width]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().isoformat()[:width]


def load_reference():
    """Charge redmine.reference.yml (les IDs Redmine bindés). Cache mémoire.

    Retourne un dict (sections custom_fields/statuses/status_aliases/trackers/
    priorities/activities) ou {} si le fichier est absent/illisible (les helpers
    retombent alors sur leurs fallbacks).
    """
    global _REFERENCE_CACHE
    if _REFERENCE_CACHE is not None:
        return _REFERENCE_CACHE
    try:
        import yaml
        _REFERENCE_CACHE = yaml.safe_load(_REFERENCE_FILE.read_text(encoding="utf-8")) or {}
    except Exception:  # OSError, ImportError, yaml.YAMLError → fallback silencieux
        _REFERENCE_CACHE = {}
    return _REFERENCE_CACHE


def cf_id_by_name(name):
    """ID du custom field nommé `name` d'après la référence, ou None."""
    for cid, spec in (load_reference().get("custom_fields") or {}).items():
        if isinstance(spec, dict) and spec.get("name") == name:
            return cid
    return None


# Fallback si la référence est absente/incomplète (cf. redmine.reference.yml ::
# type_to_activity, source de vérité). Garde la convention vivante hors-fichier.
#   31 Developpement/Feature · 16 Développement/Debug · 30 Développement/Refacto/Clean
#   13 SysAdmin/Conf/Debug · 10 Audit/Analyse · 11 Assistance · 18 Autre
_FALLBACK_TYPE_TO_ACTIVITY = {
    "feature": 31, "bugfix": 16, "maintenance": 30, "infrastructure": 13,
    "research": 10, "assistance": 11, "autre": 18,
}
_DEFAULT_ACTIVITY_ID = 18  # "Autre"


def activity_for_type(task_type):
    """Activité de temps Redmine (id) pour un `type` de tâche NORMS.

    Lit `type_to_activity` de la référence (source unique), retombe sur la table
    fallback puis sur 18 « Autre ». Cf. NORMS § « Journalisation par commit ».
    """
    key = (task_type or "").strip().lower()
    mapping = load_reference().get("type_to_activity") or _FALLBACK_TYPE_TO_ACTIVITY
    return mapping.get(key, _FALLBACK_TYPE_TO_ACTIVITY.get(key, _DEFAULT_ACTIVITY_ID))


def task_type_cf():
    """(cf_id, {type_NORMS: value_id}) pour le CF « Task type » (taxonomie fine).

    Le tracker encode la catégorie coarse ; ce CF porte le détail quand le type
    NORMS est plus fin (ex. `documentation`). Source unique :
    `redmine.reference.yml :: task_type_cf`. Retourne (None, {}) si non configuré.
    """
    ref = load_reference().get("task_type_cf") or {}
    return ref.get("id"), dict(ref.get("values") or {})


def status_aliases():
    """Mapping {statut_déprécié: statut_canonique} depuis la référence (+ fallback)."""
    ref = load_reference().get("status_aliases")
    return dict(ref) if isinstance(ref, dict) and ref else dict(_FALLBACK_STATUS_ALIASES)


def normalize_status(status):
    """Normalise un statut NORMS (résout les alias dépréciés). Idempotent."""
    if not status:
        return status
    base, _, reason = status.partition(":")
    canon = status_aliases().get(base, base)
    return f"{canon}:{reason}" if reason else canon


def status_ids():
    """Mapping {statut_NORMS_canonique: id_Redmine} depuis la référence (+ fallback)."""
    ref = load_reference().get("statuses")
    return dict(ref) if isinstance(ref, dict) and ref else dict(_FALLBACK_STATUS_IDS)


def status_map():
    """Mapping complet {statut_ou_variante: id_Redmine} pour POST/PUT Redmine.

    Inclut : les statuts canoniques, les alias dépréciés, et les variantes
    `ferme:<raison>` (toutes vers l'id du statut `ferme`). C'est la table que
    redmine-post-note.py consomme.
    """
    ids = status_ids()
    out = dict(ids)
    ferme_id = ids.get("ferme")
    if ferme_id is not None:
        for reason in _CLOSE_REASONS:
            out[f"ferme:{reason}"] = ferme_id
    for alias, canon in status_aliases().items():
        if canon in ids:
            out[alias] = ids[canon]
    return out


def valid_statuses():
    """Ensemble des statuts NORMS acceptés en écriture (canoniques + alias dépréciés)."""
    return set(status_ids()) | set(status_aliases())


def instance_env_prefix(name):
    """Nom d'instance du registre → préfixe de variable d'env (RM2653/RM2546).

    `redmine-matnat` → `REDMINE__REDMINE_MATNAT__` (clé API :
    `REDMINE__REDMINE_MATNAT__API_KEY`). Tout caractère non alphanumérique
    devient `_` pour rester un identifiant de variable d'environnement valide.
    """
    slug = "".join(c if c.isalnum() else "_" for c in str(name)).upper()
    return f"REDMINE__{slug}__"


class Creds(tuple):
    """`(url, key)` — plus, en attribut, une éventuelle auth HTTP Basic.

    Reste un tuple à deux éléments : `url, key = creds` et `creds[0]` continuent de
    fonctionner partout. L'auth Basic voyage à côté (`creds.basic`) parce qu'elle n'est
    pas une propriété du compte Redmine mais du **serveur web devant lui** — certaines
    instances partenaires sont protégées par un htpasswd (constaté sur
    `tasks.materiaux-naturels.fr`, realm « Pas touche minouche », RM2657).
    """
    basic = None

    def __new__(cls, url, key, basic=None):
        obj = super().__new__(cls, (url, key))
        obj.basic = basic
        return obj


def instance_http_basic(name):
    """(user, password) de l'auth HTTP Basic d'une instance, ou None.

    Variables : `REDMINE__<INST>__HTTP_USER` / `REDMINE__<INST>__HTTP_PASSWORD`.
    Absentes → None (cas général : aucune auth en amont).
    """
    prefix = instance_env_prefix(name)
    user = os.environ.get(f"{prefix}HTTP_USER")
    if not user:
        return None
    return (user, os.environ.get(f"{prefix}HTTP_PASSWORD", ""))


def redmine_creds(instance=None):
    """Retourne (url, key) pour l'utilisateur COURANT. Sys.exit si manquants.

    Identité par utilisateur (T1/RM2497) : préfère la clé perso du dev
    (`REDMINE_API_KEY`, typiquement dans `~/.config/mmi-pm/.env`) ; à défaut,
    retombe sur le compte de service karl (`REDMINE_USER_MAIN_API_KEY`) — pour les
    tâches de fond (cron, promote) et la rétrocompat. Résolveur CANONIQUE unique :
    tout script doit l'importer plutôt que relire les variables lui-même.

    **Multi-instance (RM2653/L0)** : `instance` — un `pm_registry.Instance` ou un nom
    d'instance — cible une AUTRE instance Redmine que la globale (gestionnaire
    partenaire, cf. CDC RM2626). Résolution alors :
      * URL   : `instance.url` (à défaut `REDMINE__<INST>__URL`, sinon `REDMINE_URL`) ;
      * clé   : `REDMINE__<INST>__API_KEY` — sauf si l'URL retenue est celle de la
        globale `REDMINE_URL`, auquel cas les clés globales servent de repli (une
        instance déclarée qui *est* l'instance de travail n'a pas besoin de clé dédiée).
    `instance=None` → comportement historique **strictement** inchangé.
    """
    global_url = os.environ.get("REDMINE_URL", "").rstrip("/")
    global_key = (os.environ.get("REDMINE_API_KEY")
                  or os.environ.get("REDMINE_USER_MAIN_API_KEY"))
    if instance is None:
        if not (global_url and global_key):
            sys.exit("ERREUR : REDMINE_URL + une clé API requis "
                     "(REDMINE_API_KEY perso dans ~/.config/mmi-pm/.env, ou "
                     "REDMINE_USER_MAIN_API_KEY karl dans le .env d'instance)")
        return Creds(global_url, global_key)

    name = getattr(instance, "name", instance)
    prefix = instance_env_prefix(name)
    url = (getattr(instance, "url", "") or os.environ.get(f"{prefix}URL", "")
           or global_url).rstrip("/")
    key = os.environ.get(f"{prefix}API_KEY")
    if not key and url and url == global_url:
        key = global_key            # l'instance déclarée EST l'instance de travail
    if not url:
        sys.exit(f"ERREUR : aucune URL pour l'instance Redmine {name!r} "
                 f"(url du registre, {prefix}URL, ou REDMINE_URL)")
    if not key:
        sys.exit(f"ERREUR : clé API manquante pour l'instance Redmine {name!r} — "
                 f"poser {prefix}API_KEY dans ~/.config/mmi-pm/.env")
    return Creds(url, key, instance_http_basic(name))


def get_ia_cf_id():
    """ID du custom field `IA` côté Redmine (configuré dans `.env :: REDMINE_CF_IA_ID`).

    Retourne `int` ou `None` si non configuré. Quand None, le filtre IA est
    désactivé (mode rétrocompat — tous les tickets sont considérés trackables).
    """
    val = (os.environ.get("REDMINE_CF_IA_ID") or "").strip()
    return int(val) if val.isdigit() else None


def issue_is_ia_tagged(issue):
    """True si le ticket Redmine porte le tag IA (custom field `IA` rempli).

    Si `REDMINE_CF_IA_ID` n'est pas configuré, retourne True (mode non filtré).
    Sinon cherche un custom_field avec cet id dont la valeur est non-vide.
    """
    cf_id = get_ia_cf_id()
    if cf_id is None:
        return True
    for cf in (issue.get("custom_fields") or []):
        if cf.get("id") != cf_id:
            continue
        v = cf.get("value")
        if v is None or v == "" or v == []:
            return False
        return True
    return False


# Champs de texte long dont Redmine rend CHAQUE retour à la ligne comme un <br>.
# L'outillage compose du markdown enveloppé à ~95 colonnes (lisible dans un fichier),
# ce qui arrive haché dans le navigateur — qui sait pourtant envelopper tout seul.
_UNWRAP_FIELDS = ("description", "notes")


def _unwrap_payload(payload):
    """Dé-enveloppe les champs de texte long d'un payload Redmine (RM2789).

    Fait ICI, au point de passage UNIQUE vers l'API, plutôt qu'à chaque appelant : il y en
    a une douzaine (add, description-update, comment, status-update, report…) et en oublier
    un laisserait le défaut revenir par une porte de côté.

    Ne touche qu'aux champs listés, jamais aux autres, et le dé-enveloppement préserve
    blocs de code, listes, tableaux, titres et sauts durs (cf. `pm_markdown.unwrap`).
    """
    if not isinstance(payload, dict):
        return payload
    try:
        from pm_markdown import unwrap
    except ImportError:                          # pragma: no cover - dépendance optionnelle
        return payload
    out = dict(payload)
    for racine, corps in out.items():
        if not isinstance(corps, dict):
            continue
        neuf = dict(corps)
        for champ in _UNWRAP_FIELDS:
            if isinstance(neuf.get(champ), str):
                neuf[champ] = unwrap(neuf[champ])
        out[racine] = neuf
    return out


def http_json(method, url, key, payload=None, timeout=20, basic=None):
    """Requête HTTP JSON simple. Retourne (status_code, body_dict_or_error).

    `basic=(user, password)` ajoute une auth **HTTP Basic** — nécessaire quand un
    serveur web protège l'instance en amont de Redmine (RM2657) ; la clé API seule
    reçoit alors un 401 du serveur web, avant même d'atteindre Redmine.
    """
    payload = _unwrap_payload(payload)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "X-Redmine-API-Key": key,
               "Accept": "application/json"}
    if basic:
        token = base64.b64encode(
            f"{basic[0]}:{basic[1]}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    req = urllib.request.Request(
        url, data=data, headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode(errors="replace")[:500]
        except Exception:
            err_body = ""
        return e.code, {"_error": err_body}


def fetch_issue(issue_id, include=None, creds=None):
    """Fetch un ticket avec inclusions optionnelles."""
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    qs = f"?include={include}" if include else ""
    code, body = http_json("GET", f"{url}/issues/{issue_id}.json{qs}", key, basic=_basic)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} pour issue #{issue_id} : {body.get('_error', '')}")
    return body.get("issue", {})


def fetch_project(project_id, creds=None):
    """Fiche d'un projet Redmine, par id numérique OU identifiant textuel.

    Existe parce que `GET /issues/<id>.json` ne rend du projet que `{id, name}` —
    jamais son `identifier`. Qui veut comparer un ticket au projet déclaré dans un
    `meta.yml` (forme textuelle, le cas normal) doit donc résoudre l'identifier
    ici (RM2784).

    Passer un id NUMÉRIQUE quand on l'a : le front Apache rejette les `%2F`, donc
    un identifiant textuel contenant un slash ne passerait pas (gotcha connu).

    Retourne {} si le projet est introuvable ou l'accès refusé — c'est un appel de
    confort, il ne doit jamais faire tomber l'appelant.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    code, body = http_json("GET", f"{url}/projects/{project_id}.json", key, basic=_basic)
    if code != 200:
        return {}
    return body.get("project", {})


def list_issues(params=None, limit=25, timeout=20, creds=None):
    """Liste des issues via `/issues.json` avec filtres Redmine arbitraires.

    `params` : dict de filtres natifs Redmine (ex: {"assigned_to_id": "me",
    "status_id": "open", "sort": "updated_on:desc"}). `limit` borne le retour.
    Retourne une liste de dicts issue (vide si aucun). Sys.exit si HTTP != 200.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    qp = dict(params or {})
    qp.setdefault("limit", limit)
    qs = urllib.parse.urlencode(qp)
    code, body = http_json("GET", f"{url}/issues.json?{qs}", key, timeout=timeout, basic=_basic)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} sur /issues : {body.get('_error', '')}")
    return body.get("issues", [])


def search_issues(query, limit=15, timeout=20, creds=None):
    """Recherche plein-texte via `/search.json` (scope issues uniquement).

    Retourne une liste de résultats {id, title, type, url, datetime, description}.
    Sys.exit si HTTP != 200.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    qs = urllib.parse.urlencode({"q": query, "issues": 1, "limit": limit})
    code, body = http_json("GET", f"{url}/search.json?{qs}", key, timeout=timeout, basic=_basic)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} sur /search : {body.get('_error', '')}")
    return body.get("results", [])


def list_time_entries(params=None, limit=100, timeout=20, creds=None):
    """Liste des saisies de temps via `/time_entries.json` avec filtres natifs.

    `params` ex: {"user_id": 5, "spent_on": "2026-06-02"}. Retourne une liste de
    dicts time_entry (chacun avec hours, user, issue, custom_fields…).
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    qp = dict(params or {})
    qp.setdefault("limit", limit)
    qs = urllib.parse.urlencode(qp)
    code, body = http_json("GET", f"{url}/time_entries.json?{qs}", key, timeout=timeout, basic=_basic)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} sur /time_entries : {body.get('_error', '')}")
    return body.get("time_entries", [])


def find_users(name, limit=5, timeout=20, creds=None):
    """Recherche d'utilisateurs Redmine par fragment (login/nom/mail).

    Best-effort : nécessite les droits admin sur la clé API. Retourne une liste
    de dicts {id, firstname, lastname, login, ...} ou [] si non autorisé / aucun.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    qs = urllib.parse.urlencode({"name": name, "limit": limit})
    code, body = http_json("GET", f"{url}/users.json?{qs}", key, timeout=timeout, basic=_basic)
    if code != 200:
        return []
    return body.get("users", [])


def add_issue_note(issue_id, note, timeout=20, creds=None):
    """Ajoute une note (journal) à une issue via PUT `notes`. Sys.exit si échec."""
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    payload = {"issue": {"notes": note}}
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key, payload, timeout=timeout, basic=_basic)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} sur note de #{issue_id} : {body.get('_error', '')}")
    return True


def fetch_project(project_ref, timeout=20, creds=None):
    """`GET /projects/<ref>.json` — `ref` accepte l'**id numérique** ou l'`identifier`.

    Rend le dict projet (`id`, `identifier`, `name`, …) ou `None` si introuvable.
    Nécessaire parce que l'API des issues ne rend que `{id, name}` pour le projet :
    comparer un `redmine.project_id` textuel (`calicote-dolibarr`) à une issue
    demande de résoudre d'abord ce texte en id numérique — sinon la comparaison
    échoue toujours, en silence.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    code, body = http_json("GET", f"{url}/projects/{project_ref}.json", key,
                           timeout=timeout, basic=_basic)
    if code != 200:
        return None
    return body.get("project")


def move_issue_project(issue_id, project_id, *, notes=None, timeout=20, creds=None):
    """DÉPLACE une issue vers un autre projet (`PUT project_id`) — RM2866.

    `project_id` : id numérique ou `identifier`. `notes` : note jointe au même PUT.
    Retourne `(ok: bool, err: str)`.

    ⚠ Le PUT est **vérifié par relecture**, contrairement à `update_issue_fields` :
    sans la permission « Move issues » (ni « Edit issues »), Redmine répond 204 et
    *drop* l'attribut — un déplacement qui échoue silencieusement laisserait la
    fiche PM et le ticket dans deux projets différents, soit exactement l'incohérence
    que l'outil est censé supprimer.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)

    target = fetch_project(project_id, timeout=timeout, creds=creds)
    if not target:
        return False, f"projet Redmine '{project_id}' introuvable"

    issue = {"project_id": target["id"]}
    if notes:
        issue["notes"] = notes
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key,
                           {"issue": issue}, timeout=timeout, basic=_basic)
    if code not in (200, 204):
        return False, f"HTTP {code} : {body.get('_error', '')[:300]}"

    after = fetch_issue(issue_id, creds=creds) or {}
    got = (after.get("project") or {}).get("id")
    if str(got) != str(target["id"]):
        return False, (f"Redmine a accepté le PUT (HTTP {code}) mais l'issue est "
                       f"toujours dans le projet {got} — permission « Move issues » "
                       f"manquante (cf. knowledge/redmine/gotchas.md)")
    return True, ""


def update_issue_fields(issue_id, *, custom_fields=None, estimated_hours=None,
                        notes=None, timeout=20, creds=None):
    """PUT générique sur une issue : custom_fields + estimated_hours + note.

    `custom_fields` : list[{id, value}]. `estimated_hours` : float (heures natives
    Redmine). `notes` : str optionnel (journalise le changement). N'envoie que les
    attributs fournis. Retourne (ok: bool, err: str).

    ⚠ Piège permissions (cf. knowledge/redmine/api.md) : sans « Edit issues »,
    Redmine renvoie 204 mais *drop* silencieusement les attributs ≠ notes. Ce
    helper ne re-vérifie pas ; l'appelant le fait s'il a besoin de la garantie.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    issue = {}
    if custom_fields:
        issue["custom_fields"] = custom_fields
    if estimated_hours is not None:
        issue["estimated_hours"] = estimated_hours
    if notes:
        issue["notes"] = notes
    if not issue:
        return True, ""
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key,
                           {"issue": issue}, timeout=timeout, basic=_basic)
    if code not in (200, 204):
        return False, f"HTTP {code} : {body.get('_error', '')[:300]}"
    return True, ""


def create_time_entry(issue_id, *, hours, activity_id, spent_on=None,
                      comments=None, custom_fields=None, timeout=20, creds=None):
    """Crée une saisie de temps (`POST /time_entries.json`) sur une issue.

    `hours` : float (> 0 attendu côté Redmine). `activity_id` : id d'activité
    (cf. redmine.reference.yml :: activities). `spent_on` : 'YYYY-MM-DD' (défaut
    aujourd'hui côté Redmine si None). `comments` : str. `custom_fields` :
    list[{id, value}] (ex: CF 16 Tokens). Retourne (ok, time_entry_id_or_err).
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    entry = {"issue_id": issue_id, "hours": round(float(hours), 2),
             "activity_id": activity_id}
    if spent_on:
        entry["spent_on"] = spent_on
    if comments:
        entry["comments"] = comments
    if custom_fields:
        entry["custom_fields"] = custom_fields
    code, body = http_json("POST", f"{url}/time_entries.json", key,
                           {"time_entry": entry}, timeout=timeout, basic=_basic)
    if code not in (200, 201):
        return False, f"HTTP {code} : {body.get('_error', '')[:300]}"
    return True, body.get("time_entry", {}).get("id")


def set_issue_ia_tag(issue_id, value="IA", creds=None):
    """Set le CF IA sur un ticket. `value=''` ou `None` retire le tag."""
    cf_id = get_ia_cf_id()
    if cf_id is None:
        sys.exit("ERREUR : REDMINE_CF_IA_ID non configuré dans .env — impossible de tag")
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    payload = {"issue": {"custom_fields": [{"id": cf_id, "value": value or ""}]}}
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key, payload, basic=_basic)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} : {body.get('_error', '')}")


def set_issue_parent(issue_id, parent_id, creds=None):
    """Pose (ou retire) le parent natif d'une issue Redmine via `parent_issue_id`.

    `parent_id=None` détache l'issue de son parent (envoie une valeur vide, que
    Redmine interprète comme « pas de parent »). Sys.exit si le PUT échoue.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    val = parent_id if parent_id is not None else ""
    payload = {"issue": {"parent_issue_id": val}}
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key, payload, basic=_basic)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} sur parent_issue_id de #{issue_id} : "
                 f"{body.get('_error', '')}")


def create_redmine_issue(*, project_id, tracker_id, priority_id, subject,
                         description="", author_id=None, tag_ia=True,
                         extra_custom_fields=None, parent_issue_id=None,
                         status_id=None, timeout=20, creds=None):
    """Crée un ticket Redmine côté PM (POST + CF IA + PUT author optionnel).

    Source unique de vérité pour la création de tickets depuis le système PM.
    Le CF IA est setté par défaut — les tickets PM-créés sont IA-trackés par
    construction (cf. NORMS « Filtrage IA »).

    Args:
        project_id: int (id) ou str (identifier) du projet Redmine.
        tracker_id: int — tracker NORMS (cf. NORMS_TYPE_TO_TRACKER côté caller).
        priority_id: int — priorité Redmine (1 low … 4 urgent).
        subject: str — titre.
        description: str — corps Redmine (markdown/textile selon instance).
        author_id: int|None — si fourni, PUT après POST pour réécrire author.
            POST set toujours author=owner-de-la-clé-API ; passer un id ici
            n'a de sens que si différent de cet owner.
        tag_ia: bool — set le CF IA='IA' au POST (défaut True).
            Mettre False uniquement pour cas hors-PM (tickets externes,
            tests, migration historique).
        extra_custom_fields: list[{id, value}] — CFs additionnels (ex: target_env).
        parent_issue_id: int|None — si fourni, crée l'issue comme enfant de ce
            ticket (attribut natif Redmine `parent_issue_id`).
        status_id: int|None — statut Redmine initial. Si None (défaut), Redmine
            applique le statut par défaut du tracker (« Nouveau », id 1 — le
            statut d'entrée NORMS). Passer un id explicite pour créer directement
            dans un autre statut (le MD du caller doit alors refléter le même).

    Returns:
        int : rm_id du ticket créé.

    Raises:
        SystemExit : POST échoué (bloquant).
            PUT author_id échouant n'est pas bloquant — warning stderr et
            le ticket reste author=key-owner.
    """
    creds = creds or redmine_creds()
    url, key = creds
    _basic = getattr(creds, "basic", None)
    payload_issue = {
        "project_id": project_id,
        "tracker_id": tracker_id,
        "priority_id": priority_id,
        "subject": subject,
        "description": description,
    }
    if parent_issue_id is not None:
        payload_issue["parent_issue_id"] = parent_issue_id
    # Statut initial : si non fourni, on laisse Redmine appliquer le statut par
    # défaut du tracker (« Nouveau », id 1 — statut d'entrée NORMS). Les callers
    # qui veulent créer directement dans un autre statut passent status_id, ou
    # (recommandé) créent en Nouveau puis transitionnent via pm-task-status-update
    # pour bénéficier du couplage NORMS (assignation, note, status_history).
    if status_id is not None:
        payload_issue["status_id"] = status_id
    custom_fields = list(extra_custom_fields or [])
    if tag_ia:
        cf_ia_id = get_ia_cf_id()
        if cf_ia_id is not None:
            custom_fields.append({"id": cf_ia_id, "value": "IA"})
    if custom_fields:
        payload_issue["custom_fields"] = custom_fields

    code, body = http_json("POST", f"{url}/issues.json", key,
                           {"issue": payload_issue}, timeout=timeout, basic=_basic)
    if code not in (200, 201):
        sys.exit(f"ERREUR Redmine HTTP {code} sur POST /issues : "
                 f"{body.get('_error', '')[:500]}")
    rm_id = body["issue"]["id"]

    if author_id is not None:
        code2, body2 = http_json("PUT", f"{url}/issues/{rm_id}.json", key,
                                 {"issue": {"author_id": author_id}}, timeout=10, basic=_basic)
        if code2 not in (200, 204):
            print(f"⚠ PUT author_id={author_id} échoué (HTTP {code2}) sur RM{rm_id} — "
                  f"ticket reste author=key-owner", file=sys.stderr)

    return rm_id
