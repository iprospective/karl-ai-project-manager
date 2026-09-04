#!/usr/bin/env python3
"""pm_repos — manifeste `repos[]` d'un projet PM : transport, identité, rattachement.

`repos[].remotes.<nom>` portait UNE chaîne, envoyée telle quelle à `git remote add`.
Or un remote a deux propriétés distinctes, dont aucune ne se déduit de l'autre
(arbitrage du demandeur, 2026-08-20) :

  * le **transport** — l'alias SSH (`gitlab:owner/repo`, `ssh://gogs@matnat-tools/…`)
    qui porte le port et la clé via `~/.ssh/config`. C'est ce que git doit recevoir ;
  * l'**identité** — l'URL canonique, seule à rattacher le dépôt à une instance du
    registre (RM2766). Elle n'avait nulle part où vivre.

Forme riche, rétro-compatible :

    repos:
    - name: matnat_sf7
      instance: gogs-matnat          # rattachement explicite — le plus sûr
      remotes:
        origin:
          url: https://gogs.materiaux-naturels.fr/Materiaux-Naturels/matnat_sf7.git
          ssh: ssh://gogs@matnat-tools/Materiaux-Naturels/matnat_sf7.git
      integration_branch: dev

Une CHAÎNE reste un transport pur, au comportement STRICTEMENT inchangé : les 47
manifestes en place n'ont rien à migrer, et `pm-env-init` / `pm-env-migrate`
continuent d'en faire exactement ce qu'ils en faisaient.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Clés reconnues d'un remote en forme riche. `ssh` est le transport, `url`
# l'identité ; toute autre clé est une faute de frappe qu'on signale plutôt
# que d'ignorer en silence (un `shh:` passerait pour « pas de transport »).
REMOTE_KEYS = ("url", "ssh")


class RepoConfError(Exception):
    pass


def remote_spec(value, where=""):
    """(transport, url) depuis une valeur de `repos[].remotes.<nom>`.

    * chaîne → (chaîne, "") : transport pur, identité inconnue — contrat historique ;
    * mapping → transport = `ssh` s'il est fourni, sinon `url` ; identité = `url`.

    Le transport tombe sur `url` quand `ssh` est absent : une conf qui ne déclare
    que l'identité reste utilisable, git sachant cloner une URL https.
    """
    ctx = f" ({where})" if where else ""
    if value is None:
        raise RepoConfError(f"remote sans valeur{ctx}")
    if isinstance(value, str):
        v = value.strip()
        if not v:
            raise RepoConfError(f"remote vide{ctx}")
        return v, ""
    if isinstance(value, dict):
        unknown = [k for k in value if k not in REMOTE_KEYS]
        if unknown:
            raise RepoConfError(
                f"remote{ctx} : clé(s) inconnue(s) {', '.join(sorted(unknown))} "
                f"— attendu {', '.join(REMOTE_KEYS)}")
        url = str(value.get("url") or "").strip()
        ssh = str(value.get("ssh") or "").strip()
        if not (url or ssh):
            raise RepoConfError(f"remote{ctx} : ni `url` ni `ssh`")
        return (ssh or url), url
    raise RepoConfError(f"remote{ctx} : chaîne ou mapping {{url, ssh}} attendu, "
                        f"reçu {type(value).__name__}")


def remote_transport(value, where=""):
    """Ce que `git remote add` doit recevoir."""
    return remote_spec(value, where)[0]


def remote_url(value, where=""):
    """URL canonique déclarée, ou "" si le remote ne porte qu'un transport."""
    return remote_spec(value, where)[1]


def validate_remotes(repo):
    """Valide `remotes` d'une entrée `repos[]`. Lève RepoConfError au 1er souci."""
    name = repo.get("name") or "?"
    remotes = repo.get("remotes") or {}
    if not isinstance(remotes, dict):
        raise RepoConfError(f"repos[{name}] : `remotes` doit être un mapping")
    for k, v in remotes.items():
        remote_spec(v, f"repos[{name}].remotes.{k}")
    return True


def merge_remote(previous, transport):
    """Valeur d'un remote après constat du transport RÉEL sur le dépôt.

    Un backfill de manifeste régénère `remotes` depuis les remotes du bare, qui
    ne connaissent que le transport. Écraser bêtement effacerait l'URL canonique
    qu'on venait de déclarer — l'identité serait perdue à chaque migration.

    Une chaîne reste donc une chaîne (rien à préserver) ; une forme riche garde
    son `url` et voit son `ssh` recalé sur le transport constaté.
    """
    if isinstance(previous, dict) and str(previous.get("url") or "").strip():
        merged = {k: v for k, v in previous.items() if k in REMOTE_KEYS}
        url = str(merged.get("url") or "").strip()
        if transport and transport != url:
            merged["ssh"] = transport
        else:
            merged.pop("ssh", None)
        return merged
    return transport


def merge_entry(previous, entry):
    """Entrée `repos[]` régénérée, en préservant ce que le constat ne sait pas dire.

    `instance:` (rattachement explicite) et l'`url` des remotes sont DÉCLARÉS :
    aucun `git remote get-url` ne les redonnera. Tout le reste vient du constat.
    """
    if not isinstance(previous, dict):
        return entry
    out = dict(entry)
    prev_remotes = previous.get("remotes") or {}
    if isinstance(prev_remotes, dict):
        out["remotes"] = {k: merge_remote(prev_remotes.get(k), v)
                          for k, v in (entry.get("remotes") or {}).items()}
    declared = str(previous.get("instance") or "").strip()
    if declared:
        out["instance"] = declared
    return out


# ── Rattachement d'un dépôt à son instance de forge ──────────────────────────

def _forge():
    """`pm_forge`, ou None. Import local : ce module doit rester lisible par des
    outils qui n'ont rien à faire d'une forge (validation de manifeste seule)."""
    try:
        import pm_forge
        return pm_forge
    except Exception:                       # noqa: BLE001
        return None


def repo_instance(repo, remote="origin"):
    """(instance, comment) — l'instance de forge à laquelle ce dépôt appartient.

    Par ordre de sûreté DÉCROISSANTE, et jamais au-delà :
      1. `instance:` déclaré sur l'entrée `repos[]` — explicite, sans ambiguïté ;
      2. l'URL canonique du remote, comparée aux instances du registre ;
      3. l'alias SSH du transport, déclaré par une instance (`ssh_aliases`).

    Aucun rattachement → (None, "inconnu"). On le DIT au lieu de deviner : se
    tromper d'instance dirige des appels et un token vers la mauvaise forge.
    """
    fg = _forge()
    if fg is None:
        return None, "inconnu (pm_forge indisponible)"

    declared = str(repo.get("instance") or "").strip()
    if declared:
        inst = fg.instance_by_name(declared)
        if inst is not None:
            return inst, f"instance: {declared}"
        return None, (f"instance: {declared} — absente du registre "
                      f"(pm.config.yml :: providers.servers)")

    spec = (repo.get("remotes") or {}).get(remote)
    if spec is None:
        return None, f"inconnu (pas de remote '{remote}')"
    try:
        transport, url = remote_spec(spec, f"repos[{repo.get('name')}].remotes.{remote}")
    except RepoConfError as e:
        return None, f"inconnu ({e})"

    if url:
        import urllib.parse
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        inst = fg.instance_for_host(host)
        if inst is not None:
            return inst, f"url → {host}"

    hint, _ = fg.parse_remote(transport)
    inst = fg.instance_for_hint(hint)
    if inst is not None:
        return inst, f"alias → {hint}"
    return None, "inconnu"


def remote_conflicts(repo, remote="origin"):
    """Messages d'incohérence entre l'identité et le transport d'un remote.

    Un dépôt dont l'URL et l'alias désignent DEUX forges différentes est une
    erreur de conf qu'aucun outil ne voyait : le transport gagne en silence, et
    tout ce qui se fonde sur l'identité (rattachement, choix d'API, token) vise
    la mauvaise instance.
    """
    fg = _forge()
    spec = (repo.get("remotes") or {}).get(remote)
    if fg is None or spec is None:
        return []
    name = repo.get("name") or "?"
    try:
        transport, url = remote_spec(spec, f"repos[{name}].remotes.{remote}")
    except RepoConfError as e:
        return [str(e)]

    # Sans instance de forge déclarée, il n'y a RIEN à comparer : signaler que
    # « l'hôte n'est servi par aucune instance » vaudrait alors pour tous les
    # dépôts de la machine — du bruit, pas un diagnostic.
    if not fg._forge_instances():
        return []

    out = []
    by_url = None
    if url:
        import urllib.parse
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        by_url = fg.instance_for_host(host)
        if by_url is None:
            out.append(f"repos[{name}].remotes.{remote} : l'URL désigne l'hôte "
                       f"'{host}', qu'aucune instance du registre ne sert")

    hint, _ = fg.parse_remote(transport)
    by_alias = fg.instance_for_hint(hint)
    if by_url is not None and by_alias is not None and by_url.name != by_alias.name:
        out.append(f"repos[{name}].remotes.{remote} : l'URL désigne "
                   f"{by_url.name} mais le transport '{hint}' désigne {by_alias.name} "
                   f"— deux forges différentes pour un même remote")

    declared = str(repo.get("instance") or "").strip()
    if declared:
        inst = fg.instance_by_name(declared)
        if inst is None:
            out.append(f"repos[{name}] : instance '{declared}' absente du registre")
        else:
            for found, how in ((by_url, "l'URL"), (by_alias, "le transport")):
                if found is not None and found.name != inst.name:
                    out.append(f"repos[{name}].remotes.{remote} : instance déclarée "
                               f"'{declared}' mais {how} désigne {found.name}")
    return out
