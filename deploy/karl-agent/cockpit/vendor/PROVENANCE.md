# Dépendances front vendorées — cockpit karl-agent (RM2522)

Première dépendance front du cockpit, jusqu'ici monofichier et sans build. Les
fichiers sont **figés ici volontairement** : pas de npm, pas de bundler, pas de CDN
(le cockpit doit fonctionner sans réseau sortant et sans étape de build).

| Fichier | Paquet npm | Version | Publié | sha256 |
|---|---|---|---|---|
| `xterm.js` | `@xterm/xterm` (`lib/xterm.js`) | 6.0.0 | 2025-12-22 | `14903579ff54664cd72f8e8699e6961a6272c21863ec1c3b118cdc8af5d4a972` |
| `xterm.css` | `@xterm/xterm` (`css/xterm.css`) | 6.0.0 | 2025-12-22 | `854a7c0fb70e8b1a083c16797ab827299fb18744f5ad34f227b48337e33293c6` |
| `addon-fit.js` | `@xterm/addon-fit` | 0.11.0 | 2025-12-22 | `ba3ea256ce0620a0992a197d6c9baea64823fc93d8da07a9e366ca9943c18527` |
| `addon-unicode11.js` | `@xterm/addon-unicode11` | 0.9.0 | 2025-12-22 | `72353b5178e1a7382716df1cfedf8ab070eea655d38995bb9f4f284fe56e2f2b` |

Licences : MIT (xterm.js et ses addons).

Les trois paquets ont été publiés le même jour : les versions d'addons ci-dessus
sont celles qui accompagnent xterm 6.0.0.

## Pourquoi 6.0.0 alors que le bug d'accents (RM2323) est dans 5.4.0 ?

**Parce que monter de version ne corrige rien** — vérifié, pas supposé. Les sources
TypeScript d'origine ont été extraites des sourcemaps (`lib/xterm.js.map`,
`sourcesContent`) pour 5.4.0, 5.5.0 et 6.0.0 : la méthode `_inputEvent` est
**identique dans les trois**, commentaires compris, et le câblage des listeners
(`keydown`, `keypress`, `composition*`, `input` en capture) est inchangé.

Le correctif est donc **notre hook de saisie** (`karl-term.js`), pas la version.
6.0.0 est retenue simplement parce que, à défaut de corriger ce point, autant
bénéficier du reste (rendu, corrections diverses).

## Mise à jour

1. Télécharger le tarball npm de la version visée, en extraire les mêmes fichiers.
2. Recalculer les `sha256` et mettre ce tableau à jour.
3. **Re-vérifier `_inputEvent`** dans les sourcemaps de la nouvelle version : si
   l'amont a fini par corriger le chemin `keydown key="Process"` + `input`, notre
   hook devient inutile et doit être retiré plutôt que laissé en double.
4. Rejouer le protocole de test de RM2522 (saisie prolongée d'accents sous Firefox).
