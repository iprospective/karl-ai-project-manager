"""pm_cf_scope — quels champs personnalisés un tracker accepte VRAIMENT (RM3368).

Redmine attache chaque champ personnalisé à une liste de trackers. Écrire un
champ sur un ticket dont le tracker ne le porte pas ne produit **aucune erreur** :
l'API répond « succès » et jette la valeur. C'est ainsi que RM3224, ouvert en
Assistance, a gardé 2 459 caractères de proposition d'implémentation dans son
miroir local et rien sur la fiche web, pendant neuf jours.

Ce module donne à l'outillage de quoi refuser l'écriture AVANT de la perdre, et
de dire quoi faire à la place : requalifier le ticket, ou porter le
développement dans un ticket lié (cf. NORMS, module `methodes-travail`).

Source de vérité : `GET /custom_fields.json`, qui porte `trackers[]` par champ.
Elle est **mémorisée sur disque** (var/cf-scope.json, 24 h) : un garde-fou
appelé à chaque écriture ne peut pas coûter un aller-retour réseau. Quand l'API
n'est pas joignable, on retombe sur `redmine.reference.yml` ; et quand on ne sait
vraiment pas, **on laisse passer** — un garde-fou qui bloque sur une panne de
lecture ferait plus de mal que le trou qu'il bouche.
"""
import json
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS.parent
CACHE_TTL = 24 * 3600

_mem = {"at": 0.0, "data": None}

# Les champs qui DISENT qu'on livre du code. Sur un tracker qui ne les porte pas,
# l'écriture est refusée net : le remède est de requalifier le ticket ou de porter
# le développement ailleurs (NORMS, module methodes-travail).
#
# Les autres champs indisponibles — ROI, Gain/Perte, Task type… — ne sont pas de
# cette nature : une assistance a parfaitement un ROI, et le remède n'est pas de
# la requalifier mais d'activer le champ (RM3367). Les refuser bloquerait une
# estimation légitime, alors on se contente de DIRE que la valeur n'arrivera pas.
CODE_FIELD_NAMES = frozenset({
    "GIT Branche", "GIT PR", "GIT Branche mergée", "Actions au déploiement",
    "Environnement de test", "Proposition d'implémentation", "AI Test par agent",
})


class FieldNotOnTracker(Exception):
    """Le champ n'existe pas pour ce tracker : écrire le perdrait en silence."""

    def __init__(self, cf_id, cf_name, tracker, message):
        super().__init__(message)
        self.cf_id, self.cf_name, self.tracker = cf_id, cf_name, tracker


# ───────────────────────────────── pur ──────────────────────────────────────

def scope_from_api(payload):
    """{cf_id: [noms de trackers]} depuis la réponse de /custom_fields.json.

    Un champ sans `trackers` est rendu avec `None` : « on ne sait pas », ce qui
    n'est pas la même chose que « aucun tracker » et ne doit rien bloquer.
    """
    out = {}
    for cf in (payload or {}).get("custom_fields") or []:
        cid = cf.get("id")
        if cid is None or cf.get("customized_type") not in (None, "issue"):
            continue
        trackers = cf.get("trackers")
        out[int(cid)] = ([str(t.get("name")) for t in trackers if t.get("name")]
                         if isinstance(trackers, list) else None)
    return out


def scope_from_reference(reference):
    """{cf_id: [trackers]} depuis redmine.reference.yml — le repli hors ligne.

    La référence nomme les trackers en minuscules PM (`bugfix`, `feature`,
    `assistance`, `autre`) ; on les traduit vers les noms Redmine pour que les
    deux sources se comparent au même vocabulaire.
    """
    noms = {"bugfix": "Anomalie", "feature": "Evolution",
            "assistance": "Assistance", "autre": "Tâche"}
    out = {}
    for cid, spec in ((reference or {}).get("custom_fields") or {}).items():
        if not isinstance(spec, dict) or spec.get("type") != "issue":
            continue
        trackers = spec.get("trackers")
        out[int(cid)] = ([noms.get(str(t), str(t)) for t in trackers]
                         if isinstance(trackers, list) else None)
    return out


def field_allowed(scope, cf_id, tracker_name):
    """Ce champ est-il écrivable sur ce tracker ?

    Trois façons de ne pas savoir — champ inconnu, portée inconnue, tracker
    inconnu — et toutes les trois autorisent : on ne bloque que sur une
    certitude.
    """
    if cf_id is None or not tracker_name:
        return True
    trackers = (scope or {}).get(int(cf_id), None)
    if trackers is None:
        return True
    return str(tracker_name) in trackers


def refus_message(cf_name, tracker_name, rm_id=None, trackers=None):
    """Ce que lit l'agent ou l'humain quand l'écriture est refusée.

    Un refus qui ne dit pas quoi faire se contourne ; celui-ci porte les deux
    seules issues admises par la norme.
    """
    ticket = f"RM{rm_id}" if rm_id else "ce ticket"
    ou = (" (il n'existe que pour : " + ", ".join(trackers) + ")") if trackers else ""
    return (
        f"champ « {cf_name} » indisponible sur le tracker « {tracker_name} »{ou}.\n"
        f"    Redmine accepterait l'écriture et la JETTERAIT : le contenu serait perdu\n"
        f"    en silence (cf. RM3224). Deux issues, pas une troisième :\n"
        f"      1. requalifier {ticket} — pm-task-type-update.py {rm_id or '<id>'} --type <type>\n"
        f"      2. porter le développement dans un ticket lié — pm-task-add.py --parent {rm_id or '<id>'}\n"
        f"    NORMS, module methodes-travail § « Assistance → répondre, pas livrer »."
    )


# ──────────────────────────────── I/O ───────────────────────────────────────

def cache_path():
    env = os.environ.get("PM_CF_SCOPE_CACHE")
    return Path(env) if env else REPO_ROOT / "var" / "cf-scope.json"


def _read_cache():
    try:
        d = json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - float(d.get("fetched_at") or 0) > CACHE_TTL:
        return None
    return {int(k): v for k, v in (d.get("scope") or {}).items()}


def _write_cache(scope):
    p = cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": time.time(), "scope": scope},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass          # un cache qu'on ne peut pas écrire ne casse pas l'écriture


def load_scope(force=False):
    """{cf_id: [trackers] | None} — API mémorisée, sinon référence locale."""
    now = time.time()
    if not force and _mem["data"] is not None and now - _mem["at"] < 300:
        return _mem["data"]
    if not force:
        cached = _read_cache()
        if cached is not None:
            _mem.update({"at": now, "data": cached})
            return cached
    scope = None
    try:
        sys.path.insert(0, str(SCRIPTS))
        import redmine_utils as ru
        url, key = ru.redmine_creds()
        st, body = ru.http_json("GET", url.rstrip("/") + "/custom_fields.json", key, timeout=15)
        if st == 200:
            scope = scope_from_api(body)
            _write_cache(scope)
    except Exception:      # noqa: BLE001 — hors ligne, clé absente, droits : on replie
        scope = None
    if scope is None:
        try:
            import yaml
            ref = yaml.safe_load((REPO_ROOT / "redmine.reference.yml").read_text(encoding="utf-8"))
            scope = scope_from_reference(ref)
        except Exception:  # noqa: BLE001 — plus de source : on n'a rien à opposer
            scope = {}
    _mem.update({"at": now, "data": scope})
    return scope


def issue_tracker(rm_id):
    """Nom du tracker d'un ticket, ou None si on ne peut pas le lire."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        import redmine_utils as ru
        issue = ru.fetch_issue(int(rm_id))
        return ((issue or {}).get("tracker") or {}).get("name")
    except Exception:      # noqa: BLE001
        return None


def check_write(rm_id, cf_id, cf_name, tracker_name=None):
    """Ce champ peut-il être écrit sur ce ticket ? Deux sévérités.

    - un **champ de code** sur un tracker qui ne le porte pas → lève
      `FieldNotOnTracker` : c'est la situation que la norme interdit, et le
      message dit laquelle des deux issues prendre ;
    - un autre champ indisponible → rend `False` après l'avoir dit : la valeur
      n'arrivera pas, mais le remède est ailleurs (activer le champ) et bloquer
      ici ferait échouer un travail légitime.

    `tracker_name` peut être fourni par l'appelant qui l'a déjà lu ; sinon on
    l'interroge. Ne rien savoir n'est jamais un motif de blocage.
    """
    if os.environ.get("PM_CF_SCOPE_OFF") == "1":
        return True
    tracker = tracker_name or issue_tracker(rm_id)
    if not tracker:
        return True
    scope = load_scope()
    if field_allowed(scope, cf_id, tracker):
        return True
    trackers = scope.get(int(cf_id)) if cf_id else None
    if cf_name in CODE_FIELD_NAMES:
        raise FieldNotOnTracker(cf_id, cf_name, tracker,
                                refus_message(cf_name, tracker, rm_id, trackers))
    print(f"⚠ champ « {cf_name} » indisponible sur le tracker « {tracker} »"
          + (" (il n'existe que pour : " + ", ".join(trackers) + ")" if trackers else "")
          + f" — Redmine jetterait la valeur : elle n'est PAS poussée. Activer le champ "
            f"pour ce tracker, ou l'accepter comme local seulement (cf. RM3367).",
          file=sys.stderr)
    return False
