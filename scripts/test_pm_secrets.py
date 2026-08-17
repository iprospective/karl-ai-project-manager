#!/usr/bin/env python3
"""Tests offline de pm_secrets — abstraction de vault (L0/RM2681).

Lancer : python3 scripts/test_pm_secrets.py
Couvre : parse_uri (trois formes + #champ + erreurs), extract_field (parité avec
le comportement historique de vault-agentd), capabilities, fabrique + point
d'extension, et le contrat d'erreurs via un backend factice. Aucun réseau, aucun
appel à `bw`, aucun vault déverrouillé nécessaire.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_secrets", str(_HERE / "pm_secrets.py"))
pm_secrets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_secrets)


# ── parse_uri ────────────────────────────────────────────────────────────────
def test_parse_uri_forme_slug():
    ref = pm_secrets.parse_uri("secret://vw-ipro/iprospective-agents/prod-db")
    assert ref.instance == "vw-ipro", ref
    assert ref.path == ("iprospective-agents", "prod-db"), ref
    assert ref.item == "prod-db" and ref.field is None, ref


def test_parse_uri_forme_courte():
    ref = pm_secrets.parse_uri("secret:calicote-agents/prod-db")
    assert ref.instance is None, ref
    assert ref.path == ("calicote-agents", "prod-db"), ref


def test_parse_uri_legacy_vaultwarden():
    ref = pm_secrets.parse_uri("vaultwarden://iprospective/calicote-agents/prod-db")
    assert ref.instance is None, ref                      # instance implicite = défaut
    assert ref.path == ("iprospective", "calicote-agents", "prod-db"), ref
    assert ref.item == "prod-db" and ref.scheme == "vaultwarden", ref


def test_parse_uri_champ_dans_uri():
    for uri, want in [
        ("secret://vw-ipro/coll/item#username", "username"),
        ("secret:coll/item#notes", "notes"),
        ("vaultwarden://o/c/i#password", "password"),
    ]:
        assert pm_secrets.parse_uri(uri).field == want, uri
    # `#` vide → pas de champ (et pas d'erreur)
    assert pm_secrets.parse_uri("secret:coll/item#").field is None


def test_parse_uri_profondeur_libre():
    """KeePass imbrique des groupes : le chemin n'est pas limité à 3 segments."""
    ref = pm_secrets.parse_uri("secret://kdbx-perso/clients/acme/prod/db-root")
    assert ref.path == ("clients", "acme", "prod", "db-root"), ref
    assert ref.item == "db-root", ref


def test_parse_uri_erreurs():
    cas = [
        "",                                   # vide
        "   ",                                # blanc
        "vaultwarden://org/item",             # legacy à 2 segments
        "vaultwarden://o/c/i/extra",          # legacy à 4 segments
        "secret://slug",                      # slug sans chemin
        "secret:",                            # rien après le scheme
        "keepass://fichier/item",             # scheme non reconnu à ce stade
        "https://example.org/x",              # pas un URI de secret
    ]
    for uri in cas:
        try:
            pm_secrets.parse_uri(uri)
        except pm_secrets.UriError:
            continue
        raise AssertionError(f"aurait dû lever UriError : {uri!r}")


# ── extract_field — parité avec le comportement historique ───────────────────
ITEM = {
    "id": "uuid-1",
    "name": "prod-db",
    "notes": "note libre",
    "login": {"password": "s3cr3t", "username": "dbuser",
              "uris": [{"uri": "https://db.example.org"}]},
    "fields": [{"name": "port", "value": "5432"}],
}


def test_extract_field_canoniques():
    assert pm_secrets.extract_field(ITEM, "password") == "s3cr3t"
    assert pm_secrets.extract_field(ITEM, "username") == "dbuser"
    assert pm_secrets.extract_field(ITEM, "notes") == "note libre"
    assert pm_secrets.extract_field(ITEM, "uri") == "https://db.example.org"
    assert pm_secrets.extract_field(ITEM, "port") == "5432"          # champ custom


def test_extract_field_defauts_historiques():
    # Sans champ demandé : le mot de passe s'il existe…
    assert pm_secrets.extract_field(ITEM, None) == "s3cr3t"
    # …sinon le JSON complet de l'item (comportement d'origine).
    sans_pwd = {"id": "u2", "name": "note-seule", "notes": "juste une note"}
    out = pm_secrets.extract_field(sans_pwd, None)
    assert out.startswith("{") and "juste une note" in out, out
    # Champ inconnu → chaîne vide, jamais d'exception.
    assert pm_secrets.extract_field(ITEM, "inexistant") == ""
    # Item sans login → chaînes vides sur les champs de login.
    assert pm_secrets.extract_field(sans_pwd, "password") == ""
    assert pm_secrets.extract_field(sans_pwd, "uri") == ""


# ── capabilities & fabrique ──────────────────────────────────────────────────
def test_vaultwarden_capabilities():
    b = pm_secrets.get_backend("vaultwarden", name="vw-ipro", session_getter=lambda: None)
    assert b.caps.needs_unlock and b.caps.listable and b.caps.hierarchical
    assert not b.caps.writable, "lecture seule en V1 (CDC RM2662)"


def test_vaultwarden_status_et_verrou():
    verrouille = pm_secrets.get_backend("vaultwarden", name="vw",
                                        session_getter=lambda: None)
    assert verrouille.status() == "locked"
    try:
        verrouille.resolve(("org", "coll", "item"), "password")
    except pm_secrets.LockedError as e:
        assert e.code == "locked" and "vw" in str(e), e
    else:
        raise AssertionError("résoudre sur un vault verrouillé doit lever LockedError")

    ouvert = pm_secrets.get_backend("vaultwarden", name="vw",
                                    session_getter=lambda: "token")
    assert ouvert.status() == "unlocked"


def test_vaultwarden_unlock_refuse():
    """Le mot de passe maître ne passe jamais par un agent (tripwire 11)."""
    b = pm_secrets.get_backend("vaultwarden", name="vw", session_getter=lambda: None)
    try:
        b.unlock(session="peu importe")
    except pm_secrets.UnsupportedError as e:
        assert "unlock-vault.sh" in str(e), e
    else:
        raise AssertionError("unlock() doit renvoyer vers unlock-vault.sh")


def test_fabrique_type_inconnu():
    try:
        pm_secrets.get_backend("lastpass", name="lp")
    except pm_secrets.UnsupportedError as e:
        assert "lastpass" in str(e) and "vaultwarden" in str(e), e
    else:
        raise AssertionError("un type inconnu doit lever UnsupportedError")


def test_point_extension_register_backend():
    """Le contrat que L3a (KeePass) consommera : s'enregistrer sans toucher aux appelants."""
    class FakeBackend(pm_secrets.SecretBackend):
        type = "fake-test"

        @property
        def caps(self):
            return pm_secrets.Capabilities(needs_unlock=False, listable=False)

        def status(self):
            return "unlocked"

        def resolve(self, path, field=None):
            if path[-1] == "absent":
                raise pm_secrets.NotFoundError("item absent", backend=self.name)
            return f"{'/'.join(path)}:{field or 'password'}"

    try:
        pm_secrets.register_backend(FakeBackend)
        b = pm_secrets.get_backend("fake-test", name="fk")
        assert b.resolve(("grp", "item"), "username") == "grp/item:username"
        assert not b.caps.needs_unlock
        # Non listable : dégradation explicite, pas un plantage.
        try:
            b.list()
        except pm_secrets.UnsupportedError as e:
            assert e.code == "unsupported", e
        else:
            raise AssertionError("list() doit lever UnsupportedError si non listable")
        # Erreur normalisée remontée telle quelle.
        try:
            b.resolve(("grp", "absent"))
        except pm_secrets.NotFoundError as e:
            assert e.code == "not_found", e
        else:
            raise AssertionError("un item absent doit lever NotFoundError")
    finally:
        pm_secrets.BACKENDS.pop("fake-test", None)


def test_hierarchie_des_erreurs():
    """Un appelant peut attraper SecretError et lire `code` sans connaître les types."""
    for cls, code in [(pm_secrets.LockedError, "locked"),
                      (pm_secrets.UnreachableError, "unreachable"),
                      (pm_secrets.NotFoundError, "not_found"),
                      (pm_secrets.DeniedError, "denied"),
                      (pm_secrets.UriError, "bad_uri"),
                      (pm_secrets.UnsupportedError, "unsupported")]:
        e = cls("msg", backend="b")
        assert isinstance(e, pm_secrets.SecretError) and e.code == code, cls
        assert str(e) == "[b] msg", str(e)


# ── Identifiants par instance et par dev (RM2682/L1) ─────────────────────────
ENV_DEV = {
    "SECRET__vw-ipro__CLIENTID": "id-ipro",
    "SECRET__vw-ipro__CLIENTSECRET": "secret-ipro",
    "SECRET__kdbx-perso__FILE": "/home/dev/vaults/ipro.kdbx",
    "SECRET__vw-clientx__TOKEN": "tok-x",
    "SECRET__vw-ipro__VIDE": "",              # déclarée vide → ignorée
    "BW_CLIENTID": "legacy-id",
    "BW_CLIENTSECRET": "legacy-secret",
    "VAULT_URL": "https://vault.example",
    "AUTRE_VAR": "sans rapport",
}


def test_creds_par_slug():
    c = pm_secrets.creds_for("vw-ipro", env=ENV_DEV, legacy=False)
    assert c == {"CLIENTID": "id-ipro", "CLIENTSECRET": "secret-ipro"}, c
    assert pm_secrets.creds_for("kdbx-perso", env=ENV_DEV, legacy=False) == {
        "FILE": "/home/dev/vaults/ipro.kdbx"}


def test_creds_isolees_par_instance():
    """Les identifiants d'un vault ne fuient pas vers un autre."""
    x = pm_secrets.creds_for("vw-clientx", env=ENV_DEV, legacy=False)
    assert x == {"TOKEN": "tok-x"}, x
    assert "TOKEN" not in pm_secrets.creds_for("vw-ipro", env=ENV_DEV, legacy=False)


def test_creds_repli_legacy():
    """Tant qu'un dev n'a pas nommé ses clés par slug, l'existant continue."""
    c = pm_secrets.creds_for("vw-autre", env=ENV_DEV)           # aucune clé par slug
    assert c == {"CLIENTID": "legacy-id", "CLIENTSECRET": "legacy-secret",
                 "URL": "https://vault.example"}, c
    # Les clés par slug l'emportent sur le repli.
    c2 = pm_secrets.creds_for("vw-ipro", env=ENV_DEV)
    assert c2["CLIENTID"] == "id-ipro" and c2["URL"] == "https://vault.example", c2


def test_creds_keys_ne_rend_que_des_noms():
    """Un diagnostic peut afficher les clés — jamais les valeurs (tripwire 11)."""
    keys = pm_secrets.creds_keys("vw-ipro", env=ENV_DEV, legacy=False)
    assert keys == ["CLIENTID", "CLIENTSECRET"], keys
    for valeur in ("id-ipro", "secret-ipro", "tok-x", "legacy-id"):
        assert valeur not in keys


CASES = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    fails = 0
    for fn in CASES:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            fails += 1; print(f"  ✗ {fn.__name__} — {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  ✗ {fn.__name__} — ERREUR {type(e).__name__}: {e}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} ok")
    sys.exit(1 if fails else 0)
