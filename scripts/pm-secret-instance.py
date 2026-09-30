#!/usr/bin/env python3
"""pm-secret-instance — quel coffre pour CE projet ? Réécrit `secret:<chemin>` en `secret://<instance>/<chemin>`.

Un projet peut utiliser un coffre différent des autres — « ce client impose son KeePass » — et le
registre sait le dire : cascade projet → client → défaut d'instance (RM2682). Mais personne ne le lui
demandait. Un secret à instance IMPLICITE (`secret:<chemin>`) partait à `vault-agentd`, qui prenait
toujours son instance par défaut : la surcharge déclarée n'était jamais consultée (RM2662, critère
« deux projets, deux instances de vault distinctes »).

Le démon ne PEUT pas résoudre ça : c'est un service utilisateur partagé par tous les projets, il ne
sait pas depuis quel workspace on l'appelle. La cascade se résout donc CHEZ L'APPELANT, qui connaît
son répertoire courant, avant d'envoyer — et le démon n'a rien à changer : il sait déjà servir
`secret://<instance>/…`.

Règles, dans cet ordre :
  * `secret://<instance>/…` n'est JAMAIS réécrit — l'appelant a choisi, il fait foi ;
  * `vaultwarden://…` non plus — la forme historique désigne le coffre par défaut, par contrat ;
  * `secret:<chemin>` prend l'instance que le registre retient pour le projet du répertoire courant ;
  * hors projet, ou si la résolution échoue, l'URI repart INCHANGÉE — c'est le comportement d'avant,
    et un résolveur qui casserait les secrets de tout un poste pour une config illisible ferait pire
    que le trou qu'il bouche.

  pm-secret-instance secret:prod/db           → secret://keepass-client/prod/db (ou inchangé)
  pm-secret-instance secret:prod/db --explain → dit pourquoi, sur stderr
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def instance_pour(cfg, registry, cwd=None):
    """(instance, source) retenue pour le projet de `cwd`, ou (None, motif)."""
    from pm_registry import resolve_instance
    det = cfg.detect_project_from_cwd(cwd) if cwd is not None else cfg.detect_project_from_cwd()
    if not det:
        return None, "hors projet PM"
    client, project = det
    meta = cfg.project_meta(client, project) or {}
    client_meta = cfg.client_meta(client) or {}
    res = resolve_instance(meta, "secret", registry, client_meta=client_meta)
    return res.instance.name, f"{client}/{project} → {res.source}"


def reecrit(uri: str, instance: str | None) -> str:
    """Pure : réécrit une URI à instance implicite. Tout le reste passe tel quel."""
    brut = (uri or "").strip()
    if not instance or not brut.startswith("secret:") or brut.startswith("secret://"):
        return brut
    return "secret://" + instance + "/" + brut[len("secret:"):].lstrip("/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uri")
    ap.add_argument("--explain", action="store_true", help="dire sur stderr d'où vient l'instance")
    a = ap.parse_args()
    brut = a.uri.strip()
    if not brut.startswith("secret:") or brut.startswith("secret://"):
        print(brut)                    # rien à résoudre : on ne charge même pas la config
        return 0
    try:
        from pm_paths import PMConfig
        from pm_registry import Registry
        cfg = PMConfig.load()
        instance, pourquoi = instance_pour(cfg, Registry.from_config(cfg.providers))
    except Exception as e:      # noqa: BLE001 — un résolveur ne casse jamais le secret qu'il sert
        instance, pourquoi = None, f"résolution impossible ({type(e).__name__}) — instance par défaut"
    if a.explain:
        print(f"pm-secret-instance : {pourquoi}" + (f" → {instance}" if instance else ""), file=sys.stderr)
    print(reecrit(brut, instance))
    return 0


if __name__ == "__main__":
    sys.exit(main())
