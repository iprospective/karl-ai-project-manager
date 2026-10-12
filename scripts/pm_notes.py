"""pm_notes — les notes de journée de Mathieu, lues sur le Nextcloud (RM3229).

Une note de journée dit, de sa main, ce que les traces ne sauront jamais : les horaires
réels et les clients du jour.

    2026-10-08

    9h15 - 18h15

    MatNat

    Calicote
    Audit à vérifier

C'est la source la plus directe du calcul — avant les transcripts, avant les commits.
Elle est lue en LECTURE SEULE : le partage Nextcloud l'est, et rien ici n'écrit.

Nommage observé, par ordre de fréquence :
  `AAAA-MM-JJ.md` · `AAAA-MM-JJ.txt`         — convention courante
  `AAAA-MM-JJ-<client>.md`                   — journée chez un client
  `AAAA MM JJ.txt`                           — ancienne forme, espaces
  `AAAA-MM-JJ-et-JJ.md`                      — deux journées dans une note
"""
import base64
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

#: Les identifiants ne suivent pas la convention provider : ils sont dans le `.env`
#: utilisateur sous ces noms-là. Les chercher ailleurs a coûté deux allers-retours.
CLES_ENV = ("NEXTCLOUD_URL", "NEXTCLOUD_USER", "NEXTCLOUD_APP_PASSWORD")

#: Dossiers fouillés, dans l'ordre. Le `(2)` vient de Nextcloud : le compte avait déjà
#: un dossier `Notes`, le partage a donc été renommé à l'arrivée.
RACINES_DEFAUT = ["/Notes (2)", "/Notes (2)/TODO jours", "/Notes"]

#: Une plage n'est retenue que si elle occupe TOUTE sa ligne. Les notes sont en texte
#: libre : « Pause 2h repas 12h30-14h30 » et « entre 1.5 et 3h » ressemblent à des plages
#: sans en être, et les prendre pour telles fausserait le plancher de la journée.
_HEURES_RE = re.compile(
    r"^\s*(\d{1,2})\s*[h:]\s*(\d{2})?\s*(?:-|–|—|à)\s*(\d{1,2})\s*[h:]\s*(\d{2})?\s*$")


def identifiants(chemin_env=None):
    """(url, user, mot de passe) depuis le `.env` utilisateur, ou None si incomplet."""
    p = Path(chemin_env) if chemin_env else None
    if p is None or not p.is_file():
        return None
    vals = {}
    for ligne in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^([A-Z_0-9]+)=(.*)$", ligne.strip())
        if m and m.group(1) in CLES_ENV:
            vals[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    if len(vals) != len(CLES_ENV):
        return None
    return vals["NEXTCLOUD_URL"], vals["NEXTCLOUD_USER"], vals["NEXTCLOUD_APP_PASSWORD"]


class Notes:
    """Accès en lecture au dossier de notes. Toute panne réseau rend None, jamais ne lève :
    une note illisible ne doit pas empêcher de valider une journée."""

    def __init__(self, creds, racines=None, timeout=20):
        self.url, self.user, self._pw = creds
        self.racines = list(racines or RACINES_DEFAUT)
        self.timeout = timeout
        self._index = None

    @property
    def _auth(self):
        return "Basic " + base64.b64encode(f"{self.user}:{self._pw}".encode()).decode()

    def _dav(self, chemin, methode="PROPFIND"):
        base = self.url.rstrip("/") + f"/remote.php/dav/files/{self.user}"
        entetes = {"Authorization": self._auth}
        if methode == "PROPFIND":
            entetes["Depth"] = "1"
        req = urllib.request.Request(base + urllib.parse.quote(chemin),
                                     method=methode, headers=entetes)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def index(self):
        """{jour → chemin} de toutes les notes trouvées. Construit une fois."""
        if self._index is not None:
            return self._index
        self._index = {}
        for racine in self.racines:
            corps = self._dav(racine)
            if not corps:
                continue
            for href in re.findall(r"<[dD]:href>([^<]+)</[dD]:href>", corps):
                nom = urllib.parse.unquote(href).rstrip("/").split("/")[-1]
                jour = jour_du_nom(nom)
                if jour:
                    self._index.setdefault(jour, f"{racine}/{nom}")
        return self._index

    def note(self, jour):
        """{chemin, texte, heures} de la note d'une journée, ou None."""
        chemin = self.index().get(jour)
        if not chemin:
            return None
        texte = self._dav(chemin, "GET")
        if texte is None:
            return None
        return {"chemin": chemin, "texte": texte, "heures": heures_du_texte(texte)}


def jour_du_nom(nom):
    """La journée qu'un nom de fichier désigne, ou None. Tolère les séparateurs."""
    if not re.search(r"\.(md|txt)$", nom, re.I):
        return None
    m = re.match(r"^(\d{4})[-_ ](\d{2})[-_ ](\d{2})", nom)
    if not m:
        return None
    an, mois, j = m.groups()
    if not ("01" <= mois <= "12" and "01" <= j <= "31"):
        return None
    return f"{an}-{mois}-{j}"


def heures_du_texte(texte):
    """(debut, fin) lus dans la note, ou None. SUGGESTION, jamais appliquée d'office.

    Seule une ligne qui ne contient QUE la plage est retenue. Sur quatre notes réelles,
    une règle plus permissive attrapait la pause (« Pause 2h repas 12h30-14h30 ») et une
    estimation de réunion (« entre 1.5 et 3h ») : deux faux horaires de journée.
    """
    for ligne in (texte or "").splitlines():
        m = _HEURES_RE.match(ligne)
        if not m:
            continue
        h1, m1, h2, m2 = m.groups()
        debut, fin = f"{int(h1):02d}:{m1 or '00'}", f"{int(h2):02d}:{m2 or '00'}"
        if debut < fin:
            return debut, fin
    return None
