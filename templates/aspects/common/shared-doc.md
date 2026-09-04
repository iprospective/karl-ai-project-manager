---
schema_version: 1.0.0
aspect: {{slug}}
title: "{{title}}"
status: draft          # draft | active | stable
wiki_sync: true
rm_ticket: {{rm_ticket}}
related_tickets:
  - {{rm_ticket}}      # ticket porteur ; ajouter ici chaque ticket que cet aspect dessert
---

# {{title}}

> **Aspect projet** — doc partagée par plusieurs tickets. Slug **stable, sans RM-id**
> (il devient l'URL de la page wiki : un rename la casse). Cet aspect **survit** à la
> fermeture du ticket porteur.
>
> Convention : [ticket-doc-convention.md](ticket-doc-convention.md) (RM1856).

## 1. Objet & principe directeur

<!-- Pourquoi cet aspect existe. Rappel du principe : FACTORISER, PAS DUPLIQUER —
     le contexte partagé vit ici UNE fois et les N tickets le référencent, au lieu
     d'être recopié dans chaque description. -->

## 2. État de l'existant

<!-- Ce qui est déjà là (briques livrées, mesures, contraintes vérifiées). Dater les
     mesures : un constat est daté, il se rejoue avant d'en refaire un lot. -->

## 3. Décisions de conception

<!-- Une décision par sous-section : ce qui est retenu, les options écartées, et
     POURQUOI. C'est la partie qu'on relira dans six mois. -->

## 4. Liaison ticket ↔ aspect

<!-- Maintenu par pm-task-doc (RM1890) :
     - aspect → tickets : `related_tickets[]` du frontmatter ci-dessus ;
     - ticket → aspect  : référence « Doc partagée : docs/<slug>.md » en description. -->

| Ticket | Rôle vis-à-vis de cet aspect |
|---|---|
| RM{{rm_ticket}} | ticket porteur |

## 5. Découpage

<!-- Les lots / sous-tickets, avec difficulté et chiffrage. Créés APRÈS validation. -->

| Lot | Contenu | Diff. | Tokens |
|---|---|---|---|
|  |  |  |  |

## 6. Risques et réversibilité

<!-- Ce qui peut mal tourner, et la parade. Une parade vérifiable vaut mieux qu'une
     intention. -->

## 7. Critères d'acceptation

- [ ] 

---
*Aspect {{slug}} — {{author}}, {{date}}.*
