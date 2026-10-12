#!/usr/bin/env python3
"""Tests RM3440 — karl-mail-send : corps markdown → HTML, pièces jointes.

Hors ligne : aucun envoi SMTP, aucun vault (--dry-run), core PM jetable (test_support).
Couvre le convertisseur markdown intégré de pm_markdown (utilisé quand python-markdown
est absent), la structure MIME produite, l'encodage des noms de fichiers accentués, les
refus (pièce absente, total trop lourd, options exclusives) et la non-régression de
l'appel texte brut historique.

Lancer : python3 scripts/test_karl_mail_send.py
"""
import importlib.util
import subprocess
import sys
import tempfile
import types
from email import message_from_bytes, policy
from pathlib import Path

from test_support import hermetic_core, subprocess_env

hermetic_core()
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_markdown  # noqa: E402

spec = importlib.util.spec_from_file_location("kms", HERE / "karl-mail-send.py")
K = importlib.util.module_from_spec(spec)
sys.modules["kms"] = K
spec.loader.exec_module(K)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# ── 1. convertisseur intégré (sans python-markdown) ──────────────────────────
B = pm_markdown.builtin_to_html
REPORT = """# Rapport

Texte avec **gras**, *italique*, `code` et [un lien](https://x.fr).
Deuxième ligne du même paragraphe.

| Réf. | Produit | Prix |
|---|---|---:|
| P-1 | Platoir | 12,50 € |
| P-2 | Règle | 30,00 € |

- point A
- point B
  - sous-point
1. étape un
2. étape deux

> une citation

---

```
brut **pas gras**
```
"""
h = B(REPORT)
check("titre rendu", "<h1>Rapport</h1>" in h)
check("tableau rendu en <table> avec en-tête et lignes",
      "<table>" in h and h.count("<tr>") == 3 and "<th>Réf.</th>" in h and "|---" not in h)
check("alignement à droite d'une colonne (---:)", '<td align="right">12,50 €</td>' in h)
check("gras, italique, code, lien", all(x in h for x in (
    "<strong>gras</strong>", "<em>italique</em>", "<code>code</code>", '<a href="https://x.fr">un lien</a>')))
check("retour à la ligne conservé dans un paragraphe (comme nl2br)", "<br />\nDeuxième ligne" in h)
check("liste à puces + sous-liste imbriquée", "<ul>" in h and h.count("<ul>") == 2 and "<li>sous-point</li>" in h)
check("liste numérotée", "<ol>" in h and "<li>étape un</li>" in h)
check("citation", "<blockquote>" in h and "une citation" in h)
check("règle horizontale", "<hr />" in h)
check("bloc de code non interprété", "<pre><code>brut **pas gras**</code></pre>" in h)
check("italique sans faux positif dans un mot (snake_case)", "<em>" not in B("une_variable_ici"))
check("rien à rendre ⇒ chaîne vide", pm_markdown.to_html("  \n ") == "")

# to_html sans python-markdown ⇒ le convertisseur intégré
saved = sys.modules.get("markdown")
sys.modules["markdown"] = None          # force l'ImportError
try:
    check("to_html bascule sur le convertisseur intégré sans python-markdown",
          pm_markdown.to_html(REPORT) == h)
finally:
    if saved is None:
        del sys.modules["markdown"]
    else:
        sys.modules["markdown"] = saved

# ── 2. rendu email complet ───────────────────────────────────────────────────
page = K.render_markdown_email(REPORT, "Rapport <client>")
check("page email : tableaux stylés en ligne", "<table style=" in page and "<td style=" in page)
check("page email : titre échappé", "<title>Rapport &lt;client&gt;</title>" in page)
check("page email : aucun HTML brut ne traverse",
      "<script>" not in K.render_markdown_email("<script>x</script>", "t"))

# ── 3. pièces jointes ────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="rm3440-"))
csv = tmp / "écarts été.csv"
csv.write_text("ref;prix\nP-1;12,5\n", encoding="utf-8")
pdf = tmp / "rapport.pdf"
pdf.write_bytes(b"%PDF-1.4 test")
inconnu = tmp / "donnees.zzz"
inconnu.write_bytes(b"\x00\x01")

atts = K.load_attachments([str(csv), str(pdf), str(inconnu)])
check("types devinés depuis l'extension",
      [(a[2], a[3]) for a in atts] == [("text", "csv"), ("application", "pdf"), ("application", "octet-stream")],
      str([(a[2], a[3]) for a in atts]))


def refus(fn):
    try:
        fn()
    except SystemExit:
        return True
    return False


check("pièce jointe absente ⇒ refus avant envoi", refus(lambda: K.load_attachments([str(tmp / "absent.pdf")])))
check("total trop lourd ⇒ refus avant envoi", refus(lambda: K.load_attachments([str(pdf)], max_mb=0.000001)))

args = types.SimpleNamespace(subject="Sujet", rm_id=None, to=["a@b.fr"], cc=[], reply_to=None,
                             in_reply_to=None, from_name="Karl")

# non-régression : texte brut seul
m0 = K.build_message(args, "Bonjour\n", "karl@iprospective.fr")
check("texte brut seul : pas de multipart (comportement historique)",
      not m0.is_multipart() and m0.get_content_type() == "text/plain")

# texte + HTML + pièces jointes
m = K.build_message(args, REPORT, "karl@iprospective.fr", page, atts)
back = message_from_bytes(m.as_bytes(), policy=policy.default)   # aller-retour réseau
check("structure multipart/mixed", back.get_content_type() == "multipart/mixed")
alt = next(back.iter_parts())
check("1re partie = multipart/alternative (texte + HTML)",
      alt.get_content_type() == "multipart/alternative"
      and [p.get_content_type() for p in alt.iter_parts()] == ["text/plain", "text/html"])
pj = list(back.iter_attachments())
check("3 pièces jointes après aller-retour", len(pj) == 3)
check("nom de fichier accentué préservé (RFC 2231)", pj[0].get_filename() == "écarts été.csv", pj[0].get_filename())
check("contenu binaire intact", pj[1].get_payload(decode=True) == b"%PDF-1.4 test")
check("structure MIME lisible pour --dry-run",
      "multipart/mixed" in K.mime_structure(m) and "« rapport.pdf »" in K.mime_structure(m))

# ── 4. ligne de commande (--dry-run, sans vault) ─────────────────────────────
md = tmp / "rapport.md"
md.write_text(REPORT, encoding="utf-8")
env = subprocess_env(PM_MAIL_SIGNATURE="")


def run(*a):
    return subprocess.run([sys.executable, str(HERE / "karl-mail-send.py"), "--to", "a@b.fr",
                           "--subject", "S", "--dry-run", *a], capture_output=True, text=True, env=env)


r = run("--markdown", str(md), "--attach", str(csv))
check("--markdown + --attach en dry-run : OK", r.returncode == 0, r.stderr[-300:])
check("dry-run : structure MIME et pièce jointe annoncées",
      "structure MIME" in r.stdout and "text/html" in r.stdout and "écarts été.csv" in r.stdout, r.stdout[-400:])
check("dry-run avec pièce jointe : pas de base64 déversé", "Content-Transfer-Encoding: base64" not in r.stdout)
r = run("--markdown", str(md), "--body", "x")
check("--markdown et --body exclusifs", r.returncode == 2 and "exclusif" in r.stderr)
r = run()
check("ni --body ni --markdown ⇒ erreur d'usage", r.returncode == 2)
r = run("--body", "Bonjour")
check("appel texte brut historique inchangé",
      r.returncode == 0 and "RFC822 message" in r.stdout and "multipart" not in r.stdout, r.stderr[-300:])
r = run("--body", "x", "--attach", str(tmp / "absent.pdf"))
check("pièce jointe absente en ligne de commande ⇒ échec", r.returncode != 0 and "introuvable" in r.stderr)

if fails:
    print(f"\n✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("\nOK")
