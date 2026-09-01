#!/usr/bin/env python3
"""Test de connexion Redmine — vérifie URL, API key, projets accessibles.

Usage :
    ./scripts/redmine-test.py
    ./scripts/redmine-test.py --project mathematicians-db
    ./scripts/redmine-test.py --issue 42
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request


def load_env():
    """Charge .env du repo (un cran au-dessus de scripts/) si non déjà défini."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def get_json(url, key, path, params=None):
    qs = f"key={key}"
    if params:
        qs += "&" + "&".join(f"{k}={v}" for k, v in params.items())
    full = f"{url.rstrip('/')}{path}?{qs}"
    req = request.Request(full, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def step(label):
    print(f"→ {label:<40}", end=" ", flush=True)


def ok(msg=""):
    print(f"OK{(' — ' + msg) if msg else ''}")


def fail(msg):
    print(f"ÉCHEC — {msg}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="Slug du projet Redmine à vérifier")
    ap.add_argument("--issue", type=int, help="ID d'un ticket à fetcher")
    args = ap.parse_args()

    load_env()

    url = os.environ.get("REDMINE_URL")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")

    if not url:
        fail("$REDMINE_URL non défini (vérifier .env)")
    if not key:
        fail("$REDMINE_API_KEY non défini (vérifier .env)")

    print(f"Redmine: {url}\n")

    # 1. User courant
    step("/users/current.json")
    try:
        data = get_json(url, key, "/users/current.json")
        u = data.get("user", {})
        ok(f"connecté en tant que {u.get('login')} ({u.get('firstname', '')} {u.get('lastname', '')})")
    except error.HTTPError as e:
        fail(f"HTTP {e.code} {e.reason} — clé API invalide ?")
    except Exception as e:
        fail(str(e))

    # 2. Liste de projets
    step("/projects.json")
    try:
        data = get_json(url, key, "/projects.json", {"limit": 25})
        projs = data.get("projects", [])
        ok(f"{len(projs)} projet(s) accessible(s)")
        for p in projs[:25]:
            print(f"    - {p.get('identifier'):<30} {p.get('name', '')}")
    except Exception as e:
        fail(str(e))

    # 3. Projet spécifique
    if args.project:
        print()
        step(f"/projects/{args.project}.json")
        try:
            data = get_json(url, key, f"/projects/{args.project}.json")
            p = data.get("project", {})
            ok(f"« {p.get('name')} » (id interne={p.get('id')})")
        except error.HTTPError as e:
            if e.code == 404:
                fail(f"projet « {args.project} » introuvable ou non accessible")
            fail(f"HTTP {e.code} {e.reason}")
        except Exception as e:
            fail(str(e))

    # 4. Issue spécifique
    if args.issue:
        print()
        step(f"/issues/{args.issue}.json")
        try:
            data = get_json(url, key, f"/issues/{args.issue}.json",
                            {"include": "journals,attachments,relations"})
            i = data.get("issue", {})
            ok(f"#{i.get('id')} ({i.get('status', {}).get('name')})")
            print(f"    Projet     : {i.get('project', {}).get('name')} ({i.get('project', {}).get('id')})")
            print(f"    Tracker    : {i.get('tracker', {}).get('name')}")
            print(f"    Priorité   : {i.get('priority', {}).get('name')}")
            print(f"    Sujet      : {i.get('subject')}")
            assignee = i.get("assigned_to")
            if assignee:
                print(f"    Assignée à : {assignee.get('name')} (id={assignee.get('id')})")
            else:
                print("    Assignée à : (personne)")
            print(f"    Créée le   : {i.get('created_on')}")
            print(f"    MàJ le     : {i.get('updated_on')}")
        except error.HTTPError as e:
            if e.code == 404:
                fail(f"ticket #{args.issue} introuvable")
            fail(f"HTTP {e.code} {e.reason}")
        except Exception as e:
            fail(str(e))

    print("\n✓ Connexion Redmine OK")


if __name__ == "__main__":
    main()
