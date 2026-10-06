#!/usr/bin/env python3
"""pm_notify — le fil de notifications de l'instance (RM2792, lot 2).

Trois canaux disaient déjà des choses, chacun dans son coin : le **journal** (`pm_log`) trace tout ce qui
se passe, le **worklog de session** (`pm-session-status notify`) retient ce qui est notable dans UNE
session, et l'**ordonnanceur** (`pm-scheduler`) garde l'historique de ses travaux. Aucun ne répond à la
question qu'on se pose vraiment en arrivant le matin : **qu'est-ce qui demande mon attention, là,
maintenant, toutes sources confondues ?**

Ce fil est cette réponse. Il ne remplace aucun des trois : il **agrège** et retient l'état.

  - Un journal est une TRACE : on y cherche après coup, il ne se lit pas en entier.
  - Un fil est une FILE : chaque entrée attend d'être lue, puis traitée, puis disparaît de la vue.

D'où ce que porte une entrée, et rien de plus : son **origine** (qui l'a émise), son **niveau**, son
horodatage, un message, et son **état** — `neuf` → `lu` → `traite`. L'identifiant est une **empreinte du
contenu** : ré-émettre la même notification ne la duplique pas, elle remonte. C'est l'anti-répétition
demandée, obtenue sans table de déduplication séparée.

Une entrée peut viser **quelqu'un** (`user=`). Trois cas, et un seul défaut sûr :

  - sans `user` : la notification concerne l'instance — tout le monde la voit ;
  - avec `user` : elle concerne d'abord cette personne, mais reste lisible par les autres (savoir
    qu'une sauvegarde a échoué chez un collègue n'a rien de confidentiel) ;
  - avec `user` ET `private=True` : elle n'est visible QUE d'elle. Le lecteur se déclare par `viewer`,
    et **sans `viewer` déclaré, aucune entrée privée n'est rendue** — un fil qui montre par défaut ce
    qu'il devrait cacher n'est pas un fil, c'est une fuite.

Filtrer par utilisateur (`user=` côté lecture) rend ce qui **concerne** cette personne : ses entrées
ET celles de l'instance, parce qu'une alerte sans destinataire concerne aussi bien celui qui filtre.

Fichier : `<state_dir>/notifications.jsonl`, une ligne par entrée, réécrit à la marque (le volume se
compte en centaines, pas en millions). Jamais d'exception vers l'appelant : un fil qui casse ce qu'il
observe n'aide personne.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

NIVEAUX = ("info", "warn", "critical")
ETATS = ("neuf", "lu", "traite")
#: qui a le droit d'émettre — nommer les sources évite que chacune invente son vocabulaire
ORIGINES = ("scheduler", "session", "agent", "forge", "mail", "system")
FICHIER = "notifications.jsonl"
GARDE = 500                      # au-delà, les plus anciennes traitées sont oubliées

_LOCK = threading.Lock()


def _state_dir() -> Path:
    d = os.environ.get("PM_NOTIFY_DIR") or os.environ.get("KARL_AGENT_STATE_DIR")
    if d:
        return Path(d)
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pm_stores      # RM2992 : la racine des stores, résolue une seule fois (et qui SURVIT
        root = pm_stores.state_root()   # à l'absence de config PM, là où `PMConfig.load()` sortait)
        if root:
            return root
    except Exception:      # noqa: BLE001
        pass
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "karl-agent"


def path() -> Path:
    return _state_dir() / FICHIER


def cle(origine: str, message: str, **champs) -> str:
    """L'empreinte d'une notification : même origine, même message, mêmes références → même entrée.
    C'est ce qui fait qu'un travail qui échoue toutes les heures ne produit pas 24 lignes par jour."""
    refs = "|".join(f"{k}={champs[k]}" for k in sorted(champs)
                    if k in ("job", "rm", "sid", "ref", "user"))
    return hashlib.sha256(f"{origine}\x1f{message}\x1f{refs}".encode("utf-8")).hexdigest()[:12]


def _lire() -> list:
    p = path()
    if not p.is_file():
        return []
    out = []
    try:
        for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                out.append(json.loads(ligne))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _ecrire(entrees: list) -> bool:
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entrees), encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        return False


def _taille(entrees: list) -> list:
    """Au-delà de la garde, on oublie les plus anciennes TRAITÉES — jamais une qui attend."""
    if len(entrees) <= GARDE:
        return entrees
    traitees = [e for e in entrees if e.get("etat") == "traite"]
    a_jeter = {id(e) for e in traitees[: len(entrees) - GARDE]}
    return [e for e in entrees if id(e) not in a_jeter]


def _user(x) -> str:
    """Un identifiant d'utilisateur normalisé : c'est une CLÉ (elle entre dans l'empreinte), donc une
    seule graphie possible. « Mathieu », « mathieu » et « mathieu » entouré d'espaces sont la même
    personne — sans cette normalisation, ils auraient trois fils séparés."""
    return str(x or "").strip().lower()[:64]


def owner() -> str:
    """Le propriétaire déclaré de l'instance, quand il n'y a personne d'authentifié.

    Le cockpit peut tourner derrière un secret partagé : personne n'est alors nommé, et le défaut sûr
    (ne rien montrer de privé) rendrait le privé illisible sur une instance mono-utilisateur. Cette
    variable dit « ici, l'utilisateur non nommé, c'est cette personne-là » — à poser explicitement,
    jamais deviné : le démon tourne sous son propre compte système, qui n'est personne."""
    return _user(os.environ.get("PM_NOTIFY_OWNER"))


def _visibles(entrees: list, viewer: str | None) -> list:
    """Ce que CE lecteur a le droit de voir. Sans lecteur déclaré, le privé n'est rendu à personne :
    le défaut d'un fil partagé ne peut pas être « tout montrer »."""
    qui = _user(viewer)
    return [e for e in entrees if not e.get("private") or (qui and e.get("user") == qui)]


def _ctx_projet(depart=None) -> dict:
    """Client et projet du workspace courant, lus au `meta.yml` du dossier PM (RM3206).

    Source DÉCLARÉE, pas devinée : `meta.yml` porte `client` et `slug`, et il est là dans les
    deux cas de figure — workspace de code (`.mmi-pm` est un lien vers le dossier PM) comme
    dépôt de données (`.mmi-pm` est un vrai dossier). Une première version déduisait le couple
    du CHEMIN résolu ; elle marchait pour les liens et rendait vide sur un dépôt de données,
    dont le chemin ne contient ni « clients » ni « projects ».

    Parse volontairement minimal — deux clés au premier niveau d'un fichier généré — pour que
    `pm_notify` reste importable sans PyYAML : il est chargé par des scripts isolés et par le
    serveur, et une notification ne doit jamais dépendre d'une bibliothèque tierce.
    """
    d = Path(depart).resolve() if depart else Path.cwd()
    for base in [d] + list(d.parents):
        meta = base / ".mmi-pm" / "meta.yml"
        if not meta.is_file():
            continue
        try:
            texte = meta.read_text(encoding="utf-8")
        except OSError:
            return {}
        out = {}
        for cle_yaml, sortie in (("client", "client"), ("slug", "projet")):
            m = re.search(rf"^{cle_yaml}:\s*(\S.*?)\s*$", texte, re.M)
            if m:
                out[sortie] = m.group(1).strip("'\"")
        return out
    return {}


def _ctx_ticket(depart=None):
    """Le ticket courant, lu à la sentinelle `<workspace>/.mmi-pm/CURRENT_TASK`.

    Même source que `pm-task-tick` (son repli), volontairement : deux définitions du « ticket
    courant » finiraient par diverger. On ne lit PAS le transcript ici — trop lourd pour un
    chemin qui doit rester muet et rapide.
    """
    d = Path(depart).resolve() if depart else Path.cwd()
    for base in [d] + list(d.parents):
        s = base / ".mmi-pm" / "CURRENT_TASK"
        if s.is_file():
            try:
                v = s.read_text(encoding="utf-8").strip()
            except OSError:
                break
            if v.isdigit():
                return v
            break
    # Repli : la BRANCHE de travail. Une branche de ticket s'appelle `<RMid>-<slug>` (norme
    # git-mep), donc elle dit le ticket même là où la sentinelle n'est pas posée — typiquement
    # un worktree de ticket, c'est-à-dire précisément là où l'on travaille.
    for base in [d] + list(d.parents):
        if not (base / ".git").exists():
            continue
        try:
            import subprocess
            r = subprocess.run(["git", "-C", str(base), "branch", "--show-current"],
                               capture_output=True, text=True, timeout=3)
        except Exception:      # noqa: BLE001
            return None
        m = re.match(r"^(\d{3,6})-", (r.stdout or "").strip())
        return m.group(1) if m else None
    return None


def _ctx_session():
    """L'identifiant de la session d'agent, si l'on tourne dans une."""
    for var in ("CLAUDE_SESSION_ID", "KARL_SESSION_ID"):
        v = (os.environ.get(var) or "").strip()
        if v:
            return v
    try:
        import pm_session
        return pm_session.claude_session_id() or None
    except Exception:      # noqa: BLE001 — sans session, une notification reste valide
        return None


def contexte_auto(depart=None) -> dict:
    """Où l'on se trouve, au moment d'émettre : ticket, session, projet, client (RM3206).

    **Pourquoi enrichir par défaut plutôt qu'ajouter des paramètres.** Le champ `rm` était déjà
    accepté, déjà rendu, déjà cliquable dans le fil — et AUCUN des quatre émetteurs ne le
    passait. Un paramètre optionnel qu'il faut penser à remplir ne se remplit pas. Le contexte
    se prend donc ici, et l'appelant n'a rien à faire pour en bénéficier.

    Chaque source échoue seule et en silence : une notification mal située vaut mieux qu'une
    notification perdue.
    """
    out = {}
    try:
        rm = _ctx_ticket(depart)
        if rm:
            out["rm"] = rm
    except Exception:      # noqa: BLE001
        pass
    try:
        sid = _ctx_session()
        if sid:
            out["sid"] = sid
    except Exception:      # noqa: BLE001
        pass
    try:
        out.update(_ctx_projet(depart))
    except Exception:      # noqa: BLE001
        pass
    return out


def add(origine: str, niveau: str, message: str, user: str | None = None,
        private: bool = False, **champs) -> dict | None:
    """Ajoute une notification, ou fait REMONTER celle qui dit déjà la même chose.

    `user` désigne la personne concernée ; `private` la réserve à elle seule. Une notification privée
    SANS destinataire est refusée (None) : elle ne serait visible de personne, et l'oubli du `user`
    passerait alors pour un fil silencieux plutôt que pour l'erreur d'appel qu'il est.

    Rend l'entrée (avec `repeats` incrémenté si elle existait), ou None si le fil n'a pas pu être écrit."""
    u = _user(user)
    prive = bool(private)
    if prive and not u:
        return None
    o = origine if origine in ORIGINES else "system"
    n = niveau if niveau in NIVEAUX else "info"
    maintenant = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    k = cle(o, str(message), user=u, **champs)
    with _LOCK:
        entrees = _lire()
        for e in entrees:
            if e.get("id") == k and e.get("etat") != "traite":
                # déjà dans la file et pas encore traitée : on ne la duplique pas, on la rafraîchit
                e["repeats"] = int(e.get("repeats", 1)) + 1
                e["last"] = maintenant
                e["level"] = n if NIVEAUX.index(n) > NIVEAUX.index(e.get("level", "info")) else e.get("level")
                # RM3177 — la remontée RAFRAÎCHIT ce qui a été mesuré. Sans cela une alerte qui
                # dure gardait les chiffres de son premier jour : le fil affichait 96 % quand on en
                # était à 98 %, et jamais la tendance — une veille qui ment précisément là où elle
                # sert. Les champs de la clé (job, rm, sid, ref, user) sont identiques par
                # construction ; seuls les autres changent. Une valeur absente (None) ne remplace
                # pas une valeur connue : on ne perd pas une mesure faute de l'avoir reprise.
                for cl, v in champs.items():
                    if v is None:
                        continue
                    try:
                        json.dumps(v); e[cl] = v
                    except TypeError:
                        e[cl] = str(v)
                _ecrire(_taille(entrees))
                return e
        entree = {"id": k, "ts": maintenant, "last": maintenant, "origin": o, "level": n,
                  "msg": str(message), "etat": "neuf", "repeats": 1}
        if u:
            entree["user"] = u
        if prive:
            entree["private"] = True
        for cl, v in champs.items():
            if v is not None:
                try:
                    json.dumps(v); entree[cl] = v
                except TypeError:
                    entree[cl] = str(v)
        # RM3206 — contexte pris sur place (ticket, session, projet, client). Deux règles :
        #   · `setdefault` : ce que l'appelant a dit explicitement gagne TOUJOURS ;
        #   · le contexte auto n'entre PAS dans `cle()` — elle est calculée plus haut, sur les
        #     seuls champs explicites. C'est capital : `cle()` intègre `sid`, donc enrichir la
        #     clé ferait de la même alerte émise depuis deux sessions DEUX entrées, et
        #     l'anti-répétition — la raison d'être de cette empreinte — tomberait.
        for cl, v in contexte_auto().items():
            entree.setdefault(cl, v)
        entrees.append(entree)
        return entree if _ecrire(_taille(entrees)) else None


def feed(etat=None, origine=None, niveau=None, limit: int = 100,
         viewer: str | None = None, user: str | None = None) -> list:
    """Le fil, du plus récent au plus ancien. `etat` accepte « ouvert » = tout sauf traité.

    `viewer` est CELUI QUI LIT : il décide des entrées privées qu'il a le droit de voir (aucune s'il
    ne se déclare pas). `user` est un FILTRE d'affichage, orthogonal : il rend ce qui concerne cette
    personne — ses entrées et celles de l'instance."""
    entrees = _visibles(_lire(), viewer)
    if user:
        vise = _user(user)
        entrees = [e for e in entrees if not e.get("user") or e.get("user") == vise]
    if etat == "ouvert":
        entrees = [e for e in entrees if e.get("etat") != "traite"]
    elif etat:
        entrees = [e for e in entrees if e.get("etat") == etat]
    if origine:
        voulues = {o.strip() for o in str(origine).split(",") if o.strip()}
        entrees = [e for e in entrees if e.get("origin") in voulues]
    if niveau:
        seuil = NIVEAUX.index(niveau) if niveau in NIVEAUX else 0
        entrees = [e for e in entrees if NIVEAUX.index(e.get("level", "info")) >= seuil]
    entrees.sort(key=lambda e: e.get("last") or e.get("ts") or "", reverse=True)
    return entrees[: max(1, min(int(limit or 100), 1000))]


def mark(ids, etat: str = "lu", viewer: str | None = None) -> int:
    """Marque des entrées. Rend le nombre réellement changé.

    `viewer` s'applique ici comme à la lecture : on ne marque pas ce qu'on n'a pas le droit de voir."""
    if etat not in ETATS:
        return 0
    voulus = {ids} if isinstance(ids, str) else set(ids or [])
    if not voulus:
        return 0
    with _LOCK:
        entrees = _lire()
        autorises = {e.get("id") for e in _visibles(entrees, viewer)}
        voulus &= autorises
        n = 0
        for e in entrees:
            if e.get("id") in voulus and e.get("etat") != etat:
                e["etat"] = etat
                e["marked"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
                n += 1
        if n:
            _ecrire(_taille(entrees))
        return n


def counts(viewer: str | None = None, user: str | None = None) -> dict:
    """Ce qu'on affiche en pastille : combien attendent, et au pire niveau. Compté DANS LA VUE du
    lecteur — une pastille qui compte ce qu'on ne peut pas ouvrir est un compteur menteur."""
    ouverts = [e for e in _visibles(_lire(), viewer) if e.get("etat") != "traite"]
    if user:
        vise = _user(user)
        ouverts = [e for e in ouverts if not e.get("user") or e.get("user") == vise]
    par_niveau = {n: sum(1 for e in ouverts if e.get("level") == n) for n in NIVEAUX}
    pire = next((n for n in reversed(NIVEAUX) if par_niveau.get(n)), None)
    return {"open": len(ouverts), "neuf": sum(1 for e in ouverts if e.get("etat") == "neuf"),
            "by_level": par_niveau, "worst": pire}


def users() -> list:
    """Les destinataires présents dans le fil — de quoi peupler un filtre sans le coder en dur."""
    return sorted({e["user"] for e in _lire() if e.get("user")})


def pending_mail(level_min: str = "warn", viewer: str | None = None) -> list:
    """Ce que le canal mail doit envoyer MAINTENANT, et rien de plus.

    L'anti-répétition tient en deux temps. L'empreinte du contenu fait qu'un incident récurrent est
    UNE entrée qui remonte, pas vingt. Le champ `mailed` fait qu'une entrée déjà partie ne repart
    pas — sauf si elle a EMPIRÉ depuis : passer de `warn` à `critical` est une nouvelle qui vaut un
    second mail, alors que la même alerte répétée à l'identique n'en vaut pas un.
    """
    seuil = NIVEAUX.index(level_min) if level_min in NIVEAUX else 0
    sortie = []
    for e in _visibles(_lire(), viewer):
        if e.get("etat") == "traite":
            continue
        niveau = e.get("level", "info")
        if niveau not in NIVEAUX or NIVEAUX.index(niveau) < seuil:
            continue
        if not e.get("mailed"):
            sortie.append(e)
            continue
        deja = e.get("mailed_level", "info")
        if NIVEAUX.index(niveau) > (NIVEAUX.index(deja) if deja in NIVEAUX else 0):
            sortie.append(e)
    sortie.sort(key=lambda e: e.get("last") or e.get("ts") or "", reverse=True)
    return sortie


def mark_mailed(ids) -> int:
    """Note que ces entrées sont parties par mail, AVEC le niveau auquel elles sont parties.

    Sans le niveau, « déjà envoyé » serait définitif et une alerte qui s'aggrave resterait muette."""
    voulus = {ids} if isinstance(ids, str) else set(ids or [])
    if not voulus:
        return 0
    maintenant = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with _LOCK:
        entrees = _lire()
        n = 0
        for e in entrees:
            if e.get("id") in voulus:
                e["mailed"] = maintenant
                e["mailed_level"] = e.get("level", "info")
                n += 1
        if n:
            _ecrire(_taille(entrees))
        return n
