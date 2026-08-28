#!/usr/bin/env python3
"""pm-site-test — Harnais de test / non-régression d'un site (RM2885).

Lit la surface de test générique du type de site (N0, ex.
knowledge/prestashop/test-surface.yml) + le manifeste du site (N1, ex.
<projet>/.mmi-pm/project/test-manifest.yml), tape un environnement cible et
produit un tableau pass/fail. Deux usages :

  - N3 (par ticket)  : --subset home,product,checkout   → sous-ensemble impacté
  - N4 (déploiement) : --full (défaut)                  → tout le site + workflows

Baselines : --record fige l'état courant ; un run normal compare à la baseline
et signale les écarts (CHANGED), en plus des FAIL absolus. Le code de sortie est
non nul dès qu'un FAIL ou un CHANGED est présent (exploitable en gate).

Exemples :
  pm-site-test.py --manifest calicote/.mmi-pm/project/test-manifest.yml --env dev --full
  pm-site-test.py --manifest … --env dev --subset home,product,checkout
  pm-site-test.py --manifest … --env dev --record            # fige la baseline
  pm-site-test.py --manifest … --env preprod --full          # compare à la baseline
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis (pip install pyyaml)")

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_surface(site_type):
    p = REPO_ROOT / "knowledge" / site_type / "test-surface.yml"
    if not p.exists():
        sys.exit(f"surface introuvable pour site_type={site_type} : {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def load_manifest(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"manifeste introuvable : {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def curl(url, env, jar=None, save_cookies=False):
    """Retourne (http_code:int, body:str). Suit les redirections."""
    args = ["curl", "-s", "-L", "--max-time", "30"]
    resolve = env.get("resolve")
    if resolve:  # "host:127.0.0.1" → --resolve host:port:ip
        host, ip = resolve.split(":", 1)
        port = "443" if env["base_url"].startswith("https") else "80"
        args += ["--resolve", f"{host}:{port}:{ip}"]
    if jar:
        args += ["-c", jar] if save_cookies else []
        args += ["-b", jar]
    args += ["-w", "\n__CODE__%{http_code}", url]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=40).stdout
    except subprocess.TimeoutExpired:
        return 0, ""
    m = re.search(r"__CODE__(\d+)\s*$", out)
    code = int(m.group(1)) if m else 0
    body = out[: m.start()] if m else out
    return code, body


def scan_errors(body, surface):
    d = surface["defaults"]
    pats = [p.lower() for p in d.get("error_scan", [])]
    ignore = [re.compile(p, re.I) for p in d.get("error_scan_ignore", [])]
    low = body.lower()
    hits = []
    for p in pats:
        idx = low.find(p)
        if idx == -1:
            continue
        frag = body[max(0, idx - 20): idx + 40]
        if any(rx.search(frag) for rx in ignore):
            continue
        hits.append(p)
    return sorted(set(hits))


def subst(path, samples, defaults):
    vals = dict(defaults)
    vals.update(samples or {})
    for k, v in vals.items():
        path = path.replace("{" + k + "}", str(v))
    return path


def build_checks(surface, manifest, subset):
    """Liste de checks page effectifs (générique + extras, - skips, + overrides)."""
    skip = set(manifest.get("skip", []))
    overrides = manifest.get("expect_overrides", {})
    checks = []
    for pg in surface.get("pages", []):
        if pg["id"] in skip:
            continue
        checks.append({
            "id": pg["id"],
            "path": pg["path"],
            "expect": overrides.get(pg["id"], pg["expect"]),
            "contains": pg.get("contains"),
        })
    for ex in manifest.get("extra_pages", []):
        checks.append({
            "id": ex["id"], "path": ex["path"],
            "expect": ex.get("expect", 200), "contains": ex.get("contains"),
        })
    if subset is not None:
        checks = [c for c in checks if c["id"] in subset]
    return checks


def run_pages(checks, env, surface, samples):
    defaults = {"lang": surface["defaults"].get("lang", "fr"),
                "search_term": surface["defaults"].get("search_term", "a")}
    base = env["base_url"].rstrip("/")
    results = []
    for c in checks:
        url = base + subst(c["path"], samples, defaults)
        code, body = curl(url, env)
        errs = scan_errors(body, surface)
        ok = (code == c["expect"]) and not errs
        if ok and c.get("contains"):
            ok = any(m.lower() in body.lower() for m in c["contains"])
        results.append({"id": c["id"], "code": code, "expect": c["expect"],
                        "errors": errs, "ok": ok})
    return results


def run_checkout(env, surface, samples):
    """Workflow tunnel : session → add cart → order (1re étape)."""
    wf = next((w for w in surface.get("workflows", []) if w["id"] == "checkout"), None)
    if not wf:
        return None
    base = env["base_url"].rstrip("/")
    lang = surface["defaults"].get("lang", "fr")
    id_product = (samples or {}).get("id_product", 1)
    jar = tempfile.mktemp(prefix="pmsite-jar-")
    try:
        _, home = curl(f"{base}/{lang}/", env, jar=jar, save_cookies=True)
        m = re.search(r'"static_token":"([a-f0-9]+)"', home)
        token = m.group(1) if m else ""
        curl(f"{base}/index.php?controller=cart&add=1&id_product={id_product}"
             f"&id_product_attribute=0&qty=1&token={token}", env, jar=jar, save_cookies=True)
        _, cart = curl(f"{base}/index.php?controller=cart&action=show", env, jar=jar, save_cookies=True)
        cart_ok = any(m in cart for m in wf.get("cart_ok_markers", []))
        ocode, order = curl(f"{base}/index.php?controller=order", env, jar=jar, save_cookies=True)
        order_ok = any(m in order for m in wf.get("order_ok_markers", []))
        errs = scan_errors(order, surface)
        ok = cart_ok and order_ok and ocode == 200 and not errs
        detail = []
        if not cart_ok:
            detail.append("panier vide")
        if not order_ok:
            detail.append("1re étape checkout absente")
        if errs:
            detail.append("erreurs:" + ",".join(errs))
        return {"id": "checkout", "code": ocode, "expect": 200,
                "errors": errs, "ok": ok, "detail": "; ".join(detail)}
    finally:
        try:
            os.unlink(jar)
        except OSError:
            pass


def report(results, baseline):
    print(f"{'CHECK':<22}{'CODE':<6}{'ATTENDU':<9}{'ÉTAT'}")
    print("-" * 60)
    n_fail = n_changed = 0
    for r in results:
        state = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]:
            n_fail += 1
        tag = ""
        if baseline is not None:
            prev = baseline.get(r["id"])
            if prev is not None and (prev.get("code") != r["code"] or prev.get("ok") != r["ok"]):
                tag = f"  ⟲ CHANGED (était code={prev.get('code')} ok={prev.get('ok')})"
                n_changed += 1
        extra = ""
        if r.get("errors"):
            extra = "  ⚠ " + ",".join(r["errors"])
        elif r.get("detail"):
            extra = "  · " + r["detail"]
        print(f"{r['id']:<22}{str(r['code']):<6}{str(r['expect']):<9}{state}{extra}{tag}")
    print("-" * 60)
    print(f"total={len(results)}  fail={n_fail}  changed={n_changed}")
    return n_fail, n_changed


def main():
    ap = argparse.ArgumentParser(description="Harnais de test / non-régression d'un site (N0+N1).")
    ap.add_argument("--manifest", required=True, help="chemin du manifeste de test du site (N1)")
    ap.add_argument("--env", required=True, help="nom de l'environnement cible (clé dans manifest.envs)")
    ap.add_argument("--full", action="store_true", help="tout le site + workflows (défaut si pas de --subset)")
    ap.add_argument("--subset", help="liste d'ids séparés par des virgules (N3)")
    ap.add_argument("--record", action="store_true", help="fige la baseline pour cet env")
    ap.add_argument("--list", action="store_true", help="liste les checks disponibles et sort")
    args = ap.parse_args()

    manifest = load_manifest(args.manifest)
    site_type = manifest.get("site_type", "prestashop")
    surface = load_surface(site_type)
    samples = manifest.get("samples", {})

    subset = None
    if args.subset:
        subset = set(x.strip() for x in args.subset.split(",") if x.strip())

    checks = build_checks(surface, manifest, subset)

    if args.list:
        print("Pages :", ", ".join(c["id"] for c in checks))
        print("Workflows :", ", ".join(w["id"] for w in surface.get("workflows", [])))
        return 0

    envs = manifest.get("envs", {})
    if args.env not in envs:
        sys.exit(f"env '{args.env}' absent du manifeste (dispo : {', '.join(envs) or '—'})")
    env = envs[args.env]

    # samples par env (ex. produit en stock différent) surchargent le global.
    samples = {**samples, **env.get("samples", {})}

    results = run_pages(checks, env, surface, samples)

    # workflows : inclus en --full, ou si nommés dans le subset
    want_checkout = (subset is None) or ("checkout" in subset)
    if want_checkout:
        co = run_checkout(env, surface, samples)
        if co:
            results.append(co)

    # baseline
    bdir = Path(args.manifest).resolve().parent / ".test-baselines"
    bfile = bdir / f"{args.env}.json"
    baseline = None
    if args.record:
        bdir.mkdir(exist_ok=True)
        snap = {r["id"]: {"code": r["code"], "ok": r["ok"]} for r in results}
        bfile.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✓ baseline enregistrée : {bfile}")
    elif bfile.exists():
        baseline = json.loads(bfile.read_text(encoding="utf-8"))

    n_fail, n_changed = report(results, baseline)
    return 1 if (n_fail or n_changed) else 0


if __name__ == "__main__":
    sys.exit(main())
