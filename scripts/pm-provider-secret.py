#!/usr/bin/env python3
"""pm-provider-secret — pose, remplace ou efface le SECRET d'une instance de provider (RM3068).

Le secret d'un provider ne vit jamais dans `pm.config.yml` (versionné) : il vit dans un fichier
d'environnement, **par développeur** (`<core>/var/users/<dev>/.env`, RM3318) ou **global** à l'instance
(réservé aux administrateurs, écrit par `sudo`). Ce script est le SEUL écrivain de ces clés, et il
respecte trois règles qui font toute la sécurité de la fonction :

  1. **La valeur ne passe JAMAIS en argument** (garde-fou 11 : `ps` est lisible par tous, le shell
     garde un historique) : elle arrive sur l'ENTRÉE STANDARD, et nulle part ailleurs.
  2. **Rien ne relit une valeur.** `--status` dit « posée le … » ou « absente », jamais le contenu ;
     aucun mode n'imprime un secret, même tronqué, même masqué.
  3. **Le journal garde le fait, pas la matière** : « clé <NOM> de <instance> remplacée », sans
     longueur, sans empreinte, sans extrait.

  pm-provider-secret --instance vw-ipro                                     demande la clé, puis la valeur (masquée)
  pm-provider-secret --instance vw-ipro --key CLIENTID           < valeur     (défaut : le .env du dev courant)
  pm-provider-secret --instance vw-ipro --key CLIENTID --unset               efface la clé
  pm-provider-secret --instance vw-ipro --status                            l'état des clés, jamais leur valeur
  pm-provider-secret … --scope global                                       le .env d'instance (admin + sudo)
  pm-provider-secret … --user <login>                                       le .env d'un autre dev (admin + sudo)

Nom complet de la variable : `<PREFIXE>__<INSTANCE>__<CLE>`, l'instance en majuscules et non-alphanum → `_`
(convention `pm.config.yml`). Le préfixe suit l'axe : REDMINE · GITLAB · GOGS · GITHUB · NC · SECRET · LLM
· DOLIBARR (axe erp, RM2891).
"""
import argparse
import os
import pwd
import getpass
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from pm_log import log as _jlog
except ImportError:                                   # journal indisponible : on n'échoue pas pour si peu
    def _jlog(*a, **k): return None

PREFIXES = {"task": "REDMINE", "forge": "GITLAB", "doc": "NC", "secret": "SECRET", "llm": "LLM",
            "erp": "ERP"}
TYPE_PREFIXES = {"redmine": "REDMINE", "redmine_wiki": "REDMINE", "gitlab": "GITLAB", "gogs": "GOGS",
                 "github": "GITHUB", "nextcloud": "NC", "vaultwarden": "SECRET", "keepass": "SECRET",
                 "age": "SECRET", "onepassword": "SECRET", "nextcloud_passwords": "SECRET",
                 "lemonade": "LLM", "ollama": "LLM", "openai": "LLM", "anthropic": "LLM",
                 "dolibarr": "DOLIBARR"}
_CLE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,60}$")
_INST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,60}$")


def slug(instance: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", instance).upper()


def nom_variable(instance: str, cle: str, prefixe: str) -> str:
    """`SECRET__VW_IPRO__CLIENTID`. Pur, testé."""
    if not _INST_RE.match(instance or ""):
        raise ValueError(f"instance invalide : {instance!r}")
    if not _CLE_RE.match(cle or ""):
        raise ValueError(f"clé invalide : {cle!r} (MAJUSCULES, chiffres, _)")
    if not _CLE_RE.match(prefixe or ""):
        raise ValueError(f"préfixe invalide : {prefixe!r}")
    return f"{prefixe}__{slug(instance)}__{cle}"


#: Les clés usuelles par famille de provider — pour guider la saisie, pas la contraindre.
CLES_USUELLES = {"REDMINE": ("API_KEY", "HTTP_USER", "HTTP_PASSWORD"), "GITLAB": ("TOKEN",),
                 "GOGS": ("TOKEN",), "GITHUB": ("TOKEN",), "NC": ("USER", "PASSWORD"),
                 "SECRET": ("CLIENTID", "CLIENTSECRET", "PASSWORD"), "LLM": ("API_KEY",)}


def demander_nom_cle(prefixe, lecteur=input):
    """Demande le NOM de la clé (jamais sa valeur) : USER, PASSWORD, API_KEY…"""
    exemples = CLES_USUELLES.get(prefixe or "", ("API_KEY", "USER", "PASSWORD"))
    saisie = (lecteur(f"Nom de la clé (ex. {', '.join(exemples)}) : ") or "").strip().upper()
    if not _CLE_RE.match(saisie):
        raise ValueError(f"clé invalide : {saisie!r} (MAJUSCULES, chiffres, _)")
    return saisie


def lire_valeur(interactif, lecteur_masque=None, flux=None):
    """La valeur du secret : masquée au terminal, sinon lue sur l'entrée standard.

    Le terminal était jusqu'ici REFUSÉ, ce qui poussait à `echo 'secret' | …` — et
    déposait le secret dans l'historique du shell. La saisie masquée le garde hors de
    l'historique ET hors de l'écran ; la confirmation évite un secret mal tapé, qui se
    pose sans bruit et ne se relit jamais (rien ne relit une valeur, règle 2).
    """
    if not interactif:
        return ((flux or sys.stdin).read() or "").strip()
    lecteur_masque = lecteur_masque or getpass.getpass
    premiere = lecteur_masque("Valeur (saisie masquée) : ")
    seconde = lecteur_masque("Confirmer : ")
    if premiere != seconde:
        raise ValueError("les deux saisies diffèrent — rien n'a été écrit")
    return (premiere or "").strip()
def deduire_prefixe(prefix, type_, axis, instance, registre=None):
    """Préfixe de la variable : ce qui est donné, sinon ce que le REGISTRE sait déjà.

    L'instance est déclarée dans `pm.config.yml` avec son type et son axe : redemander
    `--type` à l'appelant, c'est lui offrir l'occasion de se tromper — un type erroné
    écrit la clé sous un nom que le provider ne cherchera jamais. `registre` est une
    fonction `nom -> (type, axe)`, injectée pour les tests.
    """
    explicite = prefix or TYPE_PREFIXES.get((type_ or "").lower()) or PREFIXES.get((axis or "").lower())
    if explicite or not instance:
        return explicite
    try:
        itype, iaxis = (registre or _registre_instance)(instance)
    except Exception:
        return None
    return TYPE_PREFIXES.get((itype or "").lower()) or PREFIXES.get((iaxis or "").lower())


def _registre_instance(instance):
    """(type, axe) d'une instance déclarée au registre des providers."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pm_paths import PMConfig
    from pm_registry import Registry
    inst = Registry.from_config(PMConfig.load().providers).get(instance)
    return inst.type, inst.axis


def env_path(scope: str, user: str = None) -> Path:
    """Le fichier visé : celui du dev (courant ou nommé), ou celui de l'instance."""
    if scope == "global":
        core = os.environ.get("PM_CORE_DIR") or str(Path(__file__).resolve().parent.parent)
        return Path(core) / ".env"
    import pm_paths          # RM3318 : `<core>/var/users/<user>/.env`, jamais le home
    return pm_paths.user_conf_dir(user) / ".env"


def ecrit(path: Path, variable: str, valeur, unset=False) -> str:
    """Pose, remplace ou efface la variable. Écriture atomique, 0600, le reste du fichier intact.
    Rend « posée » · « remplacée » · « effacée » · « absente ». Ne rend, ni ne logue, aucune valeur."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lignes = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    rx = re.compile(rf"^\s*(?:export\s+)?{re.escape(variable)}\s*=")
    presente = any(rx.match(l) for l in lignes)
    if unset:
        if not presente:
            return "absente"
        lignes = [l for l in lignes if not rx.match(l)]
        etat = "effacée"
    else:
        ligne = f"{variable}={valeur}"
        lignes = [ligne if rx.match(l) else l for l in lignes] if presente else lignes + [ligne]
        etat = "remplacée" if presente else "posée"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)
    return etat


def etat_cles(path: Path, instance: str = None) -> list:
    """[(variable, posée)] — l'ÉTAT des clés, jamais leur valeur."""
    if not path.is_file():
        return []
    out = []
    marque = f"__{slug(instance)}__" if instance else "__"
    for l in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=(.*)$", l)
        if m and marque in m.group(1):
            out.append((m.group(1), bool(m.group(2).strip())))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", help="requis sauf avec --status, qui liste alors toutes les clés")
    ap.add_argument("--key"); ap.add_argument("--prefix"); ap.add_argument("--type"); ap.add_argument("--axis")
    ap.add_argument("--scope", choices=("user", "global"), default="user")
    ap.add_argument("--user", help="le .env d'un AUTRE développeur (administrateur, par sudo)")
    ap.add_argument("--unset", action="store_true"); ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    try:
        path = env_path(a.scope, a.user)
    except KeyError:
        sys.exit(f"ERREUR : utilisateur inconnu : {a.user}")

    if a.status:
        for variable, posee in etat_cles(path, a.instance if a.instance not in (None, "", "*") else None):
            print(f"{variable}\t{'posée' if posee else 'vide'}")
        return 0

    interactif = sys.stdin.isatty()
    if not a.instance:
        sys.exit("ERREUR : --instance requis (ou --status)")
    # Le préfixe d'abord : c'est lui qui dit quelles clés ce provider attend.
    prefixe = deduire_prefixe(a.prefix, a.type, a.axis, a.instance)
    if not prefixe:
        sys.exit(f"ERREUR : instance {a.instance!r} inconnue du registre (pm.config.yml → "
                 "providers.servers) — la déclarer, ou nommer la variable avec --prefix / "
                 "--type / --axis")
    if not a.key:
        if not interactif:
            sys.exit("ERREUR : --key requis (hors terminal, rien ne peut être demandé)")
        try:
            a.key = demander_nom_cle(prefixe)
        except (ValueError, EOFError, KeyboardInterrupt) as e:
            sys.exit(f"ERREUR : {e or 'saisie interrompue'}")
    try:
        variable = nom_variable(a.instance, a.key, prefixe)
    except ValueError as e:
        sys.exit(f"ERREUR : {e}")

    valeur = None
    if not a.unset:
        try:
            valeur = lire_valeur(interactif)
        except (ValueError, EOFError, KeyboardInterrupt) as e:
            sys.exit(f"ERREUR : {e or 'saisie interrompue'}")
        if not valeur:
            sys.exit("ERREUR : valeur vide (utiliser --unset pour effacer)")
    etat = ecrit(path, variable, valeur, unset=a.unset)
    _jlog("auth", "info", f"clé {variable} {etat}", scope=a.scope, instance=a.instance)   # le FAIT, jamais la matière
    print(f"✓ {variable} {etat} ({path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
