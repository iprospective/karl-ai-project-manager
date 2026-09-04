# Dépendances front vendorées — cockpit karl-agent (RM2522)

Première dépendance front du cockpit, jusqu'ici monofichier et sans build. Les
fichiers sont **figés ici volontairement** : pas de npm, pas de bundler, pas de CDN
(le cockpit doit fonctionner sans réseau sortant et sans étape de build).

| Fichier | Paquet npm | Version | Publié | sha256 |
|---|---|---|---|---|
| `xterm.js` | `@xterm/xterm` (`lib/xterm.js`) | 5.5.0 | 2024-04-05 | `1f991ac3b4b283ebf96e60ae23a00a52765dd3a2e46fa6fdda9f1aab032f7495` |
| `xterm.css` | `@xterm/xterm` (`css/xterm.css`) | 5.5.0 | 2024-04-05 | `ba8e6985669488981ccf40c0cefe3aba80722cb6c92de7ad628b0bd717faf2b6` |
| `addon-fit.js` | `@xterm/addon-fit` | 0.10.0 | 2024-04-05 | `bdaefa370b1bfc42ee88d46fe6072400902a4d4b2d45cd93438dda9b23c97089` |
| `addon-unicode11.js` | `@xterm/addon-unicode11` | 0.8.0 | 2024-04-05 | `b0c3be540a9984713aea996966c24ed1a639d11f60d44986b22661e3a8a148d0` |

Licences : MIT (xterm.js et ses addons).

Les trois paquets ont été publiés le même jour : les versions d'addons ci-dessus
sont celles qui accompagnent xterm 6.0.0.

## Pourquoi 5.5.0 et plus 6.0.0 ? (RM2807, 2026-08-24)

Rétrogradation délibérée : sous Firefox, l'onglet cockpit explosait en RAM
(3–12 Go, OOM) à l'attach d'une session avec le client xterm 6.0.0, alors que
l'iframe ttyd — **même renderer DOM** (`-t rendererType dom`), même flux (mesuré :
38 Ko/20 s sur la session la plus touchée), mais xterm ancien embarqué — restait
saine. Le différentiel accuse une régression mémoire du renderer 6.0.0 (pistes
amont : xtermjs#5548 layout thrashing du width cache, #5893 WidthCache/
OffscreenCanvas). Re-passage en 6.1.x envisageable quand l'amont aura corrigé —
rejouer alors le protocole RM2807 (attach d'une session à gros TUI sous Firefox,
about:processes stable) EN PLUS de celui de RM2522.

## Pourquoi pas 6.0.0 pour le bug d'accents (RM2323) ?

**Parce que monter de version ne corrige rien** — vérifié, pas supposé. Les sources
TypeScript d'origine ont été extraites des sourcemaps (`lib/xterm.js.map`,
`sourcesContent`) pour 5.4.0, 5.5.0 et 6.0.0 : la méthode `_inputEvent` est
**identique dans les trois**, commentaires compris, et le câblage des listeners
(`keydown`, `keypress`, `composition*`, `input` en capture) est inchangé.

Le correctif est donc **notre hook de saisie** (`karl-term.js`), pas la version.
(Historique : la 6.0.0 avait été retenue pour « bénéficier du reste » — c'est
précisément son rendu qui a motivé la rétrogradation ci-dessus.)

## Mise à jour

1. Télécharger le tarball npm de la version visée, en extraire les mêmes fichiers.
2. Recalculer les `sha256` et mettre ce tableau à jour.
3. **Re-vérifier `_inputEvent`** dans les sourcemaps de la nouvelle version : si
   l'amont a fini par corriger le chemin `keydown key="Process"` + `input`, notre
   hook devient inutile et doit être retiré plutôt que laissé en double.
4. Rejouer le protocole de test de RM2522 (saisie prolongée d'accents sous Firefox).
