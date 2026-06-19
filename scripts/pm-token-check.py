#!/usr/bin/env python3
"""pm-token-check — surveille la péremption des PAT GitLab de karl, rote à J-seuil (RM2046).

Sans option : rapporte l'expiration de **chaque** variable `GITLAB_*_TOKEN` du `.env`
canonique du PM (manager, worker, et tout futur token). Pour chacune, interroge
`GET /personal_access_tokens/self` (renvoie name / expires_at / active / revoked —
JAMAIS la valeur du token).

Code retour : 0 si tous sains ; 2 si au moins un est **sous le seuil** (échéance ≤
--threshold jours, ou inactif/révoqué) — pratique pour un cron/hook ; 1 sur erreur.

--rotate-due : rote (`POST /personal_access_tokens/self/rotate`) les tokens sous le
seuil et **réécrit la nouvelle valeur dans le `.env` canonique** de façon atomique.
La valeur d'un token n'est **jamais** imprimée, logguée ni écrite ailleurs que dans
le `.env` (tripwire NORMS #11). La rotation révoque immédiatement l'ancienne valeur.

Vérification recommandée en **début de session PM** (cf. NORMS `git-mep`). Doit être
lancé depuis le runtime (`.mmi-pm-core`, via le symlink) pour viser le `.env`
canonique ; en dev, sourcer le `.env` canonique et passer --env-file pour la rotation.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # charge aussi .env

DEFAULT_HOST = "gitlab.iprospective.fr"
DEFAULT_THRESHOLD = 7        # jours : rotation déclenchée une semaine avant péremption
DEFAULT_ROTATE_DAYS = 365    # durée de vie demandée pour le token roté


def base_url():
    return (os.environ.get("GITLAB_URL") or f"https://{DEFAULT_HOST}").rstrip("/")


def api(method, path, token, fields=None):
    """REST GitLab. Retourne (status, parsed_json|None, raw). Pas d'exception sur 4xx/5xx."""
    url = path if path.startswith("http") else API_BASE + path
    data = urllib.parse.urlencode(fields, doseq=True).encode() if fields else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("PRIVATE-TOKEN", token)
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:
        return 0, None, str(e)
    try:
        return status, json.loads(raw), raw
    except Exception:
        return status, None, raw


def discover_token_vars():
    """Variables d'env nommées `GITLAB_*_TOKEN` (manager, worker, futurs…), triées."""
    return sorted(k for k in os.environ
                  if k.startswith("GITLAB_") and k.endswith("_TOKEN") and os.environ.get(k))


def days_until(exp):
    if not exp:
        return None
    try:
        d = datetime.date.fromisoformat(str(exp)[:10])
    except ValueError:
        return None
    return (d - datetime.date.today()).days


def inspect(var):
    """État du token porté par `var` : dict {var,name,expires_at,days,active,revoked,error}."""
    st, data, raw = api("GET", "/personal_access_tokens/self", os.environ[var])
    if st != 200 or not isinstance(data, dict):
        msg = (data or {}).get("message") if isinstance(data, dict) else None
        return {"var": var, "error": msg or f"HTTP {st}"}
    exp = data.get("expires_at")
    return {
        "var": var, "name": data.get("name"), "expires_at": exp,
        "days": days_until(exp), "active": data.get("active"),
        "revoked": data.get("revoked"), "error": None,
    }


def is_due(info, threshold):
    if info.get("error"):
        return False  # erreur ≠ « due » (un révoqué/expiré ne peut pas s'auto-roter)
    if info.get("revoked") or info.get("active") is False:
        return True
    d = info.get("days")
    return d is not None and d <= threshold


def fmt(info, threshold):
    if info.get("error"):
        return f"  ✗ {info['var']:<22} ERREUR : {info['error']}"
    flag = "⚠ DUE" if is_due(info, threshold) else "ok"
    d = info.get("days")
    djour = f"J-{d}" if d is not None else "sans expiration"
    return (f"  {'⚠' if flag!='ok' else '·'} {info['var']:<22} "
            f"name={info.get('name')}  expire={info.get('expires_at') or '—'} ({djour})  "
            f"active={info.get('active')} revoked={info.get('revoked')}  [{flag}]")


def rewrite_env_value(env_path, key, new_value):
    """Remplace atomiquement la ligne `KEY=…` du .env (préserve les permissions)."""
    if not env_path.exists():
        sys.exit(f"ERREUR : .env introuvable ({env_path}) — lancer depuis le runtime "
                 f"ou passer --env-file vers le .env canonique.")
    lines = env_path.read_text().splitlines(keepends=True)
    out, found = [], False
    for ln in lines:
        if ln.lstrip().startswith(key + "="):
            out.append(f"{key}={new_value}\n")
            found = True
        else:
            out.append(ln)
    if not found:
        sys.exit(f"ERREUR : clé {key} absente de {env_path} — rotation annulée.")
    mode = env_path.stat().st_mode & 0o777
    tmp = env_path.with_name(env_path.name + ".tmp")
    tmp.write_text("".join(out))
    os.chmod(tmp, mode)
    os.replace(tmp, env_path)


def rotate(var, env_path, expiry_days, dry_run):
    new_exp = (datetime.date.today() + datetime.timedelta(days=expiry_days)).isoformat()
    if dry_run:
        print(f"  → [dry-run] roterait {var} (nouvelle expiration demandée : {new_exp})")
        return True
    st, data, _raw = api("POST", "/personal_access_tokens/self/rotate",
                         os.environ[var], fields={"expires_at": new_exp})
    # NE JAMAIS imprimer _raw : sur succès il contient la nouvelle valeur du token.
    if not isinstance(data, dict) or not data.get("token"):
        print(f"  ✗ rotation {var} échouée (HTTP {st}"
              f"{' : ' + data['message'] if isinstance(data, dict) and data.get('message') else ''})",
              file=sys.stderr)
        return False
    new_token = data["token"]
    rewrite_env_value(env_path, var, new_token)
    new_token = None  # on lâche la référence au plus vite
    os.environ[var] = ""  # l'ancien process ne réutilise pas l'ancienne valeur révoquée
    print(f"  ✓ {var} roté — nouvelle expiration {data.get('expires_at', new_exp)} "
          f"(valeur réécrite dans {env_path.name}, non affichée)")
    return True


def main():
    cfg = PMConfig.load()  # charge le .env (GITLAB_*)
    global API_BASE
    API_BASE = base_url() + "/api/v4"

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                    help=f"seuil de rotation en jours (défaut : {DEFAULT_THRESHOLD})")
    ap.add_argument("--rotate-due", action="store_true",
                    help="rote les tokens sous le seuil (réécrit le .env canonique)")
    ap.add_argument("--rotate-expiry-days", type=int, default=DEFAULT_ROTATE_DAYS,
                    help=f"durée de vie du token roté (défaut : {DEFAULT_ROTATE_DAYS} j)")
    ap.add_argument("--env-file", type=lambda s: Path(s).resolve(),
                    help="chemin du .env à réécrire (défaut : <pm_dir>/.env canonique)")
    ap.add_argument("--dry-run", action="store_true",
                    help="avec --rotate-due : montre sans roter")
    args = ap.parse_args()

    env_path = args.env_file or (cfg.pm_dir / ".env")
    token_vars = discover_token_vars()
    if not token_vars:
        print("Aucune variable GITLAB_*_TOKEN dans l'environnement / le .env.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Tokens GitLab ({base_url()}) — seuil rotation J-{args.threshold} :")
    infos = [inspect(v) for v in token_vars]
    for info in infos:
        print(fmt(info, args.threshold))

    errors = [i for i in infos if i.get("error")]
    due = [i for i in infos if is_due(i, args.threshold)]

    rc = 0
    if errors:
        rc = 1
    if due:
        print(f"\n{len(due)} token(s) à roter (≤ J-{args.threshold}) : "
              + ", ".join(i["var"] for i in due))
        if args.rotate_due:
            ok = all(rotate(i["var"], env_path, args.rotate_expiry_days, args.dry_run)
                     for i in due)
            if args.dry_run:
                rc = max(rc, 2)            # rien de réellement roté
            elif not ok:
                rc = 1
            # sinon : rotation réussie → ne compte plus comme « due »
        else:
            print("  (relancer avec --rotate-due pour roter)")
            rc = max(rc, 2)
    elif not errors:
        print("\n✓ Tous les tokens sont sains (aucun sous le seuil).")

    sys.exit(rc)


if __name__ == "__main__":
    main()
