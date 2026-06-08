#!/usr/bin/env python3
"""brevo_cleaner.py — purge des contacts SPAM (noms aléatoires) d'un compte Brevo.

Modèle de sécurité (3 conditions cumulatives pour qu'un contact soit supprimé) :
  1. NOM CHARABIA   — prénom ou nom détecté comme suite de caractères aléatoires
                      (transitions de casse, longues suites de consonnes, zéro voyelle).
  2. ABSENT DE PROD — email absent de l'allowlist construite depuis la/les base(s)
                      prod du projet (clients PrestaShop + newsletter + contacts Dolibarr…).
  3. AUCUNE COMMANDE— tous les attributs « montant commande / CA » du contact valent 0.

Un contact n'est supprimé que si (1) ET (2) ET (3). Tout le reste est conservé.

Usage :
  ./brevo_cleaner.py <env> plan   [--workdir DIR]     # dry-run : fetch + backup + analyse
  ./brevo_cleaner.py <env> apply  [--workdir DIR] --yes  # suppression effective (throttlée)

La conf d'environnement est lue dans environments/<env>.json (gitignoré).
Voir environments/*.json.example et le README.

Aucun secret n'est stocké : la clé API Brevo et les emails légitimes sont obtenus
à l'exécution via les commandes shell définies dans la conf (qui lisent elles-mêmes
les credentials depuis la prod). Le dry-run écrit toujours un backup intégral des
contacts avant toute action.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.error, urllib.request

VOWELS = set('aeiouyàâäéèêëïîôöùûüAEIOUYÀÂÄÉÈÊËÏÎÔÖÙÛÜ')
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- détecteur
def _case_switches(t):
    s = 0; prev = None
    for ch in t:
        if ch.isalpha():
            cur = ch.isupper()
            if prev is not None and cur != prev:
                s += 1
            prev = cur
    return s


def _max_cons_run(t):
    best = run = 0
    for ch in t:
        if ch.isalpha() and ch not in VOWELS:
            run += 1; best = max(best, run)
        else:
            run = 0
    return best


def _vowel_ratio(t):
    al = [c for c in t if c.isalpha()]
    return sum(1 for c in al if c in VOWELS) / len(al) if al else 1.0


def make_detector(cfg):
    min_len = cfg.get('min_token_len', 6)
    cs_thr = cfg.get('case_switches', 3)
    cr_thr = cfg.get('cons_run', 6)
    zero_vowels = cfg.get('require_zero_vowels', True)

    def tok_gib(t):
        if len(t) < min_len or not t.isalpha():
            return False
        return (_case_switches(t) >= cs_thr
                or _max_cons_run(t) >= cr_thr
                or (zero_vowels and _vowel_ratio(t) == 0.0))

    def name_gib(name):
        if not name:
            return False
        return any(tok_gib(tok) for tok in re.split(r'[\s\-]+', name.strip()))

    return name_gib


# ---------------------------------------------------------------- helpers
def run_cmd_lines(cmd):
    """Exécute une commande shell, retourne ses lignes stdout (strip, non vides)."""
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=HERE)
    if out.returncode != 0:
        sys.stderr.write(f"[WARN] commande non-zero ({out.returncode}): {cmd}\n{out.stderr[:400]}\n")
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def run_cmd_value(cmd):
    lines = run_cmd_lines(cmd)
    return lines[0] if lines else ''


def load_conf(env):
    path = os.path.join(HERE, 'environments', f'{env}.json')
    if not os.path.isfile(path):
        sys.exit(f"Conf introuvable : {path}\n(copier environments/{env}.json.example)")
    with open(path) as f:
        return json.load(f)


def brevo_request(key, path, method='GET'):
    req = urllib.request.Request('https://api.brevo.com/v3' + path, method=method,
                                 headers={'api-key': key, 'accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        return r.status, json.loads(body) if body else None


def fetch_all_contacts(key, ndjson_path):
    offset, limit, total = 0, 1000, None
    n = 0
    with open(ndjson_path, 'w') as out:
        while total is None or offset < total:
            _, d = brevo_request(key, f'/contacts?limit={limit}&offset={offset}')
            total = d['count']
            for c in d['contacts']:
                out.write(json.dumps(c) + '\n'); n += 1
            offset += limit
            sys.stderr.write(f"\rfetch {min(offset,total)}/{total}")
    sys.stderr.write("\n")
    return n, total


# ---------------------------------------------------------------- plan
def cmd_plan(env, conf, workdir):
    os.makedirs(workdir, exist_ok=True)
    name_attrs = conf['name_attrs']
    order_attrs = conf.get('order_attrs', [])
    name_gib = make_detector(conf.get('detector', {}))

    print("→ Récupération de la clé API Brevo…")
    key = run_cmd_value(conf['brevo_key_cmd'])
    if not key:
        sys.exit("Clé API Brevo vide — vérifier brevo_key_cmd.")

    print("→ Construction de l'allowlist prod…")
    allow = set()
    for cmd in conf.get('allowlist_cmds', []):
        before = len(allow)
        for e in run_cmd_lines(cmd):
            allow.add(e.strip().lower())
        print(f"    +{len(allow)-before} emails ({cmd[:60]}…)")
    print(f"    allowlist totale : {len(allow)} emails légitimes")
    with open(os.path.join(workdir, 'allowlist.txt'), 'w') as f:
        f.write('\n'.join(sorted(allow)))

    print("→ Fetch + backup des contacts Brevo…")
    ndjson = os.path.join(workdir, 'contacts_backup.ndjson')
    n, total = fetch_all_contacts(key, ndjson)
    print(f"    {n} contacts sauvegardés dans {ndjson}")

    delete, gib_inprod, gib_order = [], 0, 0
    with open(ndjson) as f:
        for line in f:
            c = json.loads(line)
            a = c.get('attributes', {})
            email = c['email'].strip().lower()
            gib = any(name_gib((a.get(k) or '').strip()) for k in name_attrs)
            if not gib:
                continue
            inprod = email in allow
            has_order = False
            for k in order_attrs:
                try:
                    if float(a.get(k) or 0) > 0:
                        has_order = True; break
                except (TypeError, ValueError):
                    pass
            if inprod:
                gib_inprod += 1; continue
            if has_order:
                gib_order += 1; continue
            names = ' '.join((a.get(k) or '') for k in name_attrs).strip()
            delete.append((c['id'], email, names, c.get('createdAt', '')[:10]))

    review = os.path.join(workdir, 'REVIEW_candidats.tsv')
    with open(review, 'w') as f:
        f.write("id\temail\tnom\tcreated\n")
        for r in sorted(delete, key=lambda x: x[3]):
            f.write('\t'.join(str(x) for x in r) + '\n')
    ids = os.path.join(workdir, 'delete_ids.txt')
    with open(ids, 'w') as f:
        for r in delete:
            f.write(f"{r[0]}\t{r[1]}\t{r[2]}\n")

    print("\n================ PLAN ================")
    print(f"  contacts total           : {total}")
    print(f"  charabia gardés (en prod): {gib_inprod}")
    print(f"  charabia gardés (commande): {gib_order}")
    print(f"  CANDIDATS SUPPRESSION    : {len(delete)}")
    print(f"  → revue : {review}")
    print(f"  → ids   : {ids}")
    print(f"  → backup: {ndjson}")
    print("Lancer `apply --yes` pour supprimer ces IDs.")


# ---------------------------------------------------------------- apply
def cmd_apply(env, conf, workdir, yes):
    ids_path = os.path.join(workdir, 'delete_ids.txt')
    if not os.path.isfile(ids_path):
        sys.exit(f"{ids_path} introuvable — lancer `plan` d'abord.")
    ids = [l.split('\t')[0].strip() for l in open(ids_path) if l.strip()]
    if not yes:
        sys.exit(f"{len(ids)} contacts à supprimer. Relancer avec --yes pour confirmer.")

    key = run_cmd_value(conf['brevo_key_cmd'])
    log_path = os.path.join(workdir, 'delete.log')
    logf = open(log_path, 'w')
    ok = notfound = err = 0
    total = len(ids)
    logf.write(f"START {total}\n"); logf.flush()
    i = 0
    while i < total:
        cid = ids[i]
        try:
            status, _ = brevo_request(key, f'/contacts/{cid}', method='DELETE')
            ok += 1; i += 1
        except urllib.error.HTTPError as e:
            if e.code == 404:
                notfound += 1; i += 1
            elif e.code == 429:
                logf.write(f"{cid}: 429 backoff\n"); logf.flush(); time.sleep(5); continue
            else:
                err += 1; logf.write(f"{cid}: HTTP {e.code}\n"); logf.flush(); i += 1
        except Exception as e:
            err += 1; logf.write(f"{cid}: EXC {e}\n"); logf.flush(); i += 1
        if i % 200 == 0:
            msg = f"progress {i}/{total} ok={ok} notfound={notfound} err={err}"
            logf.write(msg + "\n"); logf.flush(); sys.stderr.write("\r" + msg)
        time.sleep(0.11)
    logf.write(f"DONE ok={ok} notfound={notfound} err={err}\n")
    print(f"\nDONE ok={ok} notfound={notfound} err={err} (log: {log_path})")


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Purge des contacts spam (noms aléatoires) d'un compte Brevo.")
    p.add_argument('env', help="nom de l'environnement (environments/<env>.json)")
    p.add_argument('action', choices=['plan', 'apply'])
    p.add_argument('--workdir', default=None, help="dossier de travail (défaut: ./work/<env>)")
    p.add_argument('--yes', action='store_true', help="confirme la suppression (apply)")
    args = p.parse_args()
    conf = load_conf(args.env)
    workdir = args.workdir or os.path.join(HERE, 'work', args.env)
    if args.action == 'plan':
        cmd_plan(args.env, conf, workdir)
    else:
        cmd_apply(args.env, conf, workdir, args.yes)


if __name__ == '__main__':
    main()
