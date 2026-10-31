# DataSyntis — Design system web (`ds-*`)

> CSS pur, sans framework, sans étape de build, **100 % auto-hébergé** (CSP `default-src 'self'`) : aucun CDN, aucune police externe.
> Fichiers :
> - [`public/css/tokens.css`](../public/css/tokens.css) : tokens (custom properties), thèmes clair et sombre
> - [`public/css/components.css`](../public/css/components.css) : composants `ds-*` et système d'icônes SVG M3
> - [`public/img/icons.svg`](../public/img/icons.svg) : sprite vectoriel de 58 icônes Material Design 3 (`<symbol id="ic-…">`, grille optique `24×24`, trait arrondi `1.85px`)
> - [`styleguide/index.html`](../styleguide/index.html) : styleguide vivant avec catalogue d'icônes interactif (`#tokens-icons`)
> - [`scripts/check-contrast.mjs`](../scripts/check-contrast.mjs) : contrôle WCAG des paires de tokens (`node web/scripts/check-contrast.mjs`, code retour 1 si une paire échoue)

Source de vérité de la marque : `application/.streamlit/config.toml` et `application/static/icon.svg`. Ce design system reprend la même palette pour que l'UI web et l'UI Streamlit restent cohérentes.

---

## 1. Principes

1. **Lisible sans réfléchir.** Chaque écran se comprend en une seconde, pour deux personas :
   - **Médecin / spécialiste RCP** : urgence, orientation pré-RCP, repères cliniques, évolution depuis la RCP précédente, avis et références.
   - **Secrétaire médicale / coordination RCP** : complétude, pièces manquantes, spécialités à convoquer, identité du patient.
2. **Sobre et rigoureux.** Fond pierre mat (`canvas`) contre l'éblouissement, cartes papier en relief, un seul accent primaire (sarcelle). Pas de ton marketing.
3. **La couleur n'est jamais seule.** Tout statut = **icône + texte + couleur** (WCAG 1.4.1). Les variations (deltas) ajoutent une flèche et une valeur signée.
4. **Le rose a un sens précis.** Il est réservé à 🚨 **Priorité haute** et aux **actions destructives**. Ailleurs, jamais.
5. **Neutralité médico-légale.** L'outil prépare la décision, il ne la prend pas. Les orientations sont formulées comme des propositions (voir § 6).
6. **Le clinicien a le dernier mot.** Toute modification manuelle est visible (✍️) et n'est jamais écrasée en silence.
7. **KISS.** Du HTML sémantique et des états natifs (`<dialog>`, `<details>`, `aria-*`, `:disabled`) avant les classes. Pas de JS requis pour le rendu, htmx pour l'interactivité.

---

## 2. Tokens

Préfixe `--ds-`. Les composants consomment **uniquement les tokens sémantiques** (`--ds-color-*`, `--ds-urgency-*`, …), jamais les primitives (`--ds-teal-600`) ni des valeurs hexadécimales en dur.

### 2.1 Thème

| Mécanisme | Effet |
| :--- | :--- |
| défaut | thème clair |
| `<html data-theme="dark">` | sombre forcé |
| `<html data-theme="light">` | clair forcé (ignore l'OS) |
| sans attribut + OS en sombre | sombre (`prefers-color-scheme`) |

Le bloc sombre est **dupliqué volontairement** (attribut + media query) pour rester compatible avec les navigateurs hospitaliers anciens (pas de `light-dark()`). Gardez les deux blocs synchronisés.

### 2.2 Couleurs (contrastes calculés selon WCAG 2.x)

Texte : ≥ 4.5:1 (AA). Composants d'interface, bordures de champs, anneau de focus : ≥ 3:1.

| Rôle | Token | Clair | Sombre | Contraste (clair / sombre) |
| :--- | :--- | :--- | :--- | :--- |
| Fond de travail | `--ds-color-canvas` | `#E6ECF0` | `#0F172A` | — |
| Carte (surface) | `--ds-color-surface` | `#FBFDFF` | `#162032` | — |
| Zone en retrait | `--ds-color-surface-sunken` | `#F1F5F9` | `#111A2B` | — |
| Texte | `--ds-color-text` | `#2A3647` | `#E2E8F0` | 11.99 / 13.24 sur surface |
| Texte secondaire | `--ds-color-text-muted` | `#4A5A70` | `#A3B1C4` | 6.89 / 7.49 sur surface, 5.90 / 8.20 sur canvas |
| Texte discret | `--ds-color-text-subtle` | `#5F6E82` | `#8D9BB0` | 5.10 / 5.79 |
| Bordure de champ | `--ds-color-border-strong` | `#7A8799` | `#64748B` | 3.58 / 3.43 (UI) |
| Primaire (sarcelle) | `--ds-color-primary` | `#467E79` | `#72A8A2` | texte du bouton : 4.65 (blanc) / 7.03 (`#0B1120`) |
| Lien, onglet actif | `--ds-color-primary-text` | `#3A6B66` | `#88BDB7` | 5.93 / 7.78 sur surface, 5.07 / 8.51 sur canvas |
| Anneau de focus | `--ds-color-focus` | `#3B6E9C` | `#7FB2F0` | 4.52 / 8.10 sur canvas (UI) |
| Succès / conformité (sauge) | `--ds-color-success-fg` / `-bg` | `#2E544A` / `#E6F1EE` | `#BFE3D6` / `#16362E` | 7.32 / 9.48 |
| Attention (ambre) | `--ds-color-warning-fg` / `-bg` | `#7C4718` / `#FBF0E4` | `#FCD9A8` / `#43290F` | 6.74 / 10.00 |
| Danger (rose) | `--ds-color-danger` | `#B83B5E` | `#E11D48` | texte blanc : 5.49 / 4.70 |
| Danger, badge | `--ds-color-danger-fg` / `-bg` | `#882644` / `#F9E8EC` | `#FECDD6` / `#4A1424` | 7.39 / 10.53 |
| Info (bleu clinique) | `--ds-color-info-fg` / `-bg` | `#234B6E` / `#E3EFF8` | `#DBEAFE` / `#1E3A5F` | 7.80 / 9.43 |
| Neutre | `--ds-color-neutral-fg` / `-bg` | `#3D4A5C` / `#E2E8EE` | `#CBD5E1` / `#273449` | 7.29 / 8.45 |
| 🧭 Adaptation suggérée | `--ds-orientation-adapt-fg` / `-bg` | `#2C5753` / `#E2EFED` | `#BCE0DB` / `#173A37` | 6.86 / 8.74 |
| ✍️ Modifié manuellement | `--ds-manual-fg` / `-bg` | `#6E4F12` / `#FAF3E0` | `#F5DFA6` / `#3D3010` | 6.80 / 9.82 |
| Spécialité requise | `--ds-specialty-fg` / `-bg` | `#3B475C` / `#EAEFF5` | `#D3DCE8` / `#2A3548` | 8.10 / 8.92 |
| Domaine Oncologie | `--ds-domain-onco-fg` / `-bg` | `#1F5470` / `#E1EEF5` | `#BFE0F0` / `#123247` | 6.93 / 9.62 |
| Domaine SMA | `--ds-domain-sma-fg` / `-bg` | `#56427A` / `#EFEAF6` | `#DCD0F0` / `#2E2447` | 7.24 / 9.81 |
| Barre latérale | `--ds-sidebar-bg` / `-text` | `#2B3748` / `#E8EEF3` | `#0B1120` / `#E2E8F0` | 10.30 / 15.27 |
| En-tête de tableau | `--ds-table-header-bg` / `-text` | `#2B3748` / `#F1F5F9` | `#0B1120` / `#F8FAFC` | 11.00 / 18.00 |

Alias cliniques :

| Sémantique | Tokens | Correspond à |
| :--- | :--- | :--- |
| Urgence haute 🚨 | `--ds-urgency-high*` | danger (rose) |
| Urgence modérée 🟠 | `--ds-urgency-medium*` | warning (ambre) |
| Urgence standard 🟢 | `--ds-urgency-low*` | success (sauge) |
| Non évaluée ⚪ | `--ds-urgency-none*` | neutral |
| Conforme au référentiel ✅ | `--ds-orientation-standard*` | success |
| Adaptation suggérée 🧭 | `--ds-orientation-adapt*` | **sarcelle primaire (neutre)** |
| À discuter / en attente ⏳ | `--ds-orientation-pending*` | neutral |

### 2.3 Typographie

Pile système `--ds-font-sans` (system-ui, Segoe UI, Roboto, Noto Sans, Liberation Sans… + polices emoji). Mono : `--ds-font-mono`.

| Token | Taille | Usage |
| :--- | :--- | :--- |
| `--ds-text-xs` | 12 px | méta, horodatages (jamais pour du texte courant) |
| `--ds-text-sm` | 13 px | tableaux denses, badges, boutons |
| `--ds-text-md` | 15 px | corps de texte |
| `--ds-text-lg` | 17 px | titres de section ou de carte |
| `--ds-text-xl` | 20 px | titres h2 |
| `--ds-text-2xl` | 24 px | titre de page, nom du patient |
| `--ds-text-3xl` | 30 px | valeur des KPI |

Graisses : 400 / 500 / 600 / 700. Chiffres tabulaires (`font-variant-numeric: tabular-nums`) pour les tableaux, les KPI et les deltas.

### 2.4 Espacement, rayons, ombres, couches, mouvement

- **Espacement** (grille de 4 px) : `--ds-space-1` (4 px) → `--ds-space-12` (48 px).
- **Rayons** : `sm` 4 px · `md` 6 px (boutons, champs) · `lg` 8 px (cartes) · `xl` 12 px (modales) · `pill` (badges).
- **Ombres** : `sm` (cartes) · `md` (survol, carte synoptique) · `lg` (modale, tiroir, toast).
- **Z-index** : sticky 10 · sidebar 20 · topbar 30 · bannière de file 40 · tiroir 50 · modale 60 · toast 70.
- **Mouvement** : 120 / 200 / 320 ms, courbe `--ds-ease`. Avec `prefers-reduced-motion: reduce`, les durées passent à 0 ; spinners ralentis, shimmer et points de saisie arrêtés.

---

## 3. Composants

Nommage BEM : `.ds-bloc`, `.ds-bloc__element`, `.ds-bloc--variante`. L'état passe d'abord par les attributs natifs ou ARIA.

| Composant | Classes | État / notes |
| :--- | :--- | :--- |
| Shell | `ds-shell`, `ds-sidebar`, `ds-brand`, `ds-nav__link`, `ds-main`, `ds-topbar`, `ds-workspace`, `ds-skip-link` | `aria-current="page"` sur le lien actif. Sous 64 rem, la sidebar passe au-dessus du contenu. |
| Bannière de file | `ds-queue-banner` (`--idle`, `--success`, `--error`, `--offline`), `__msg`, `__progress`, `__action` | `role="status" aria-live="polite" aria-atomic="true"`, cible SSE (`sse-swap`). Une seule ligne. |
| Tiroir | `<dialog class="ds-drawer">`, `__header`, `__body`, `__footer`, `ds-job` | Ouverture par `showModal()` ; fermeture avec `<form method="dialog">` ou Échap. |
| Boutons | `ds-btn` + `--primary`, `--secondary`, `--ghost`, `--danger-soft`, `--danger` ; `--sm`, `--lg`, `--icon`, `--block` | Chargement : `aria-busy="true"` + `disabled` (ou classe `htmx-request`). Bouton icône seul : `aria-label` obligatoire. |
| Badges | `ds-badge` + `--urgency-{high,medium,low,none}`, `--complete`, `--incomplete`, `--orientation-{standard,adapt,pending}`, `--specialty`, `--domain-{onco,sma}`, `--manual`, `--success`, `--warning`, `--danger`, `--info`, `--neutral` ; `--sm`, `--outline` ; `ds-badge-list` | Emoji dans `<span class="ds-icon" aria-hidden="true">`, libellé ≤ 24 caractères. |
| Cartes | `ds-card`, `__header`, `__title`, `__body`, `__footer`, `--interactive`, `--flush` | Cartes de même hauteur dans une grille ; actions alignées dans le footer. |
| KPI | `ds-kpi-grid`, `ds-kpi` (`--danger`, `--warning`, `--success`, `--info`), `__label`, `__value`, `__meta` | Un KPI cliquable est un `<a>` qui mène à la vue filtrée. |
| Synoptique | `ds-synoptic` (sticky), `--static`, `__row`, `__label`, `ds-markers` (`dl`), `dd.is-missing` | Ligne 1 : priorité, complétude, orientation. Ligne 2 : spécialités requises. Ligne 3 : repères cliniques et deltas. |
| Delta | `ds-delta--better`, `--worse`, `--stable`, `--new` | Flèche (sens) + valeur signée + date de référence. Une aggravation est en **ambre**, pas en rose. |
| Patient | `ds-patient-header`, `ds-patient-grid`, `ds-patient-card` (`--urgent`) | — |
| Tableau | `ds-table-wrap`, `ds-table` (`--dense`, `--comfortable`), `ds-sort`, `tr.is-urgent`, `ds-table__primary-link`, `__num`, `__actions` | Tri via `<th aria-sort>` + `<button class="ds-sort">`. En-tête sticky. `<caption>` (au besoin `ds-sr-only`). |
| Barre d'outils | `ds-toolbar`, `ds-segmented` | Contrôle segmenté = vrais boutons radio. |
| Formulaires | `ds-field`, `ds-label`, `ds-hint`, `ds-error-text`, `ds-input`, `ds-select`, `ds-textarea`, `ds-check`, `ds-toggle` | Erreur : `aria-invalid="true"` + `aria-describedby` qui pointe vers `ds-error-text`. Interrupteur : `<input type="checkbox" role="switch" class="ds-toggle">`. |
| Zone de dépôt | `ds-dropzone` (`.is-dragover`), `ds-file-list` | `<label>` qui englobe un `<input type="file" multiple accept="application/pdf" class="ds-sr-only">` : utilisable au clavier sans JS. |
| Rubrique éditable | `<details class="ds-section">` (`--manual`, `.is-editing`), `__title`, `__summary`, `__body`, `__actions`, `__duration`, `__provenance` | Repliée par défaut, conclusion dans le `summary`. Rubrique modifiée : `--manual` + badge `ds-badge--manual` + provenance (qui, quand). |
| Alertes | `ds-alert` (`--success`, `--warning`, `--danger`, `--guidance`), `__icon`, `__title` | `role="alert"` uniquement pour un danger bloquant ; sinon `role="note"` ou aucun rôle. |
| Toasts | `ds-toast-region` (`role="status" aria-live="polite"`), `ds-toast` (`--success`, `--warning`, `--danger`) | Bouton de fermeture avec `aria-label`. Une erreur ne disparaît jamais toute seule. |
| Onglets | `ds-tabs[role=tablist]`, `ds-tab[role=tab][aria-selected]`, `ds-tabpanel[role=tabpanel]` | Flèches ←/→ et *roving tabindex*. Onglets par liens : `aria-current="page"`. |
| Frise | `ds-timeline`, `__item`, `__link` (`aria-current="step"`), `__marker--{high,medium,low}`, `__date`, `__meta` | Le marqueur contient un glyphe, le méta un libellé. |
| Avis experts | `<details class="ds-opinion">`, `ds-refs`, `ds-ref__source`, `ds-ref__quote`, `ds-disclaimer` | Un accordéon par spécialité, trié par pertinence puis urgence. |
| Chat | `ds-chat`, `__log` (`aria-live="polite"`), `__msg--user`, `__msg--assistant`, `__bubble`, `__typing`, `__composer` | Les sources sont affichées sous la bulle de l'assistant. |
| Progression | `ds-progress` (`<progress>`, `--success`, `--danger`), `ds-progress-label`, `ds-stepper`, `ds-step--{done,active,error}` | `aria-label` avec le pourcentage ; `aria-current="step"` sur l'étape active. |
| Modale | `<dialog class="ds-modal">` (`--danger`, `--lg`), `__header`, `__body`, `__footer` | Focus initial sur **Annuler** (`autofocus`). `aria-labelledby` et `aria-describedby`. |
| Chargement / vide | `ds-skeleton` (`--title`, `--block`, `--w-60`, `--w-80`), `ds-empty` | Conteneur en chargement : `aria-busy="true"`. Un état vide propose toujours l'action suivante. |
| Vue scindée | `ds-split` (`--40-60`), `ds-split__pane` (`--sticky`), `ds-pdf-frame` | Une seule colonne sous 75 rem. PDF servi par la même origine (CSP). |
| Utilitaires | `ds-stack` (`--sm`, `--lg`), `ds-cluster`, `ds-grid`, `ds-sr-only`, `ds-muted`, `ds-small`, `ds-mono`, `ds-nowrap` | — |

### Actions destructives

| Étape | Classe | `data-testid` | Aspect |
| :--- | :--- | :--- | :--- |
| Déclencheur (ouvre la confirmation) | `ds-btn--danger-soft` | `btn_del_<objet>_<id>` | contour et texte roses |
| Confirmation irréversible (dans `<dialog class="ds-modal ds-modal--danger">`) | `ds-btn--danger` | `btn_danger_<action>` | rose plein |

Le dialogue contient une `ds-alert--danger` qui décrit ce qui sera perdu, avec un libellé explicite : « Supprimer définitivement », pas « OK ».

### `data-testid`

Convention en snake_case ou kebab-case, stable et sans donnée patient : `kpi-priority-high`, `worklist-row-<id>`, `badge-orientation-adapt`, `section-<clé>`, `btn_edit_section_<clé>`, `btn_del_…`, `btn_danger_…`, `queue-banner`, `queue-drawer`.

---

## 4. À faire / à éviter

| ✅ À faire | ❌ À éviter |
| :--- | :--- |
| `🧭 Adaptation suggérée` en sarcelle neutre | orientation en rouge ou en rose, ou « Non conforme » |
| `🚨 Priorité haute` en rose, avec contour | du rose pour un lien, un onglet ou un KPI non urgent |
| icône + texte + couleur | pastille de couleur seule ou texte coloré seul |
| libellé ≤ 24 caractères, détail en infobulle ou dans le panneau | une phrase entière dans un badge |
| « Non renseigné » en italique discret | « Not documented in record », « null », « N/A » |
| spécialités au nom court (`🧠 Neurologie`) | « Expert neurologue », 🕵️ |
| validation ✓ en sauge | ✓ sur fond rouge ou rose |
| confirmation en deux temps (`btn_del_` → `btn_danger_`) | suppression en un clic |
| tokens sémantiques | hexadécimal en dur dans un template |
| polices système, assets sous `/public` | Google Fonts, CDN, icônes distantes |

---

## 5. Checklist accessibilité (WCAG 2.2 AA)

- [ ] Contrastes : `node web/scripts/check-contrast.mjs` passe (texte ≥ 4.5:1, UI ≥ 3:1) dans les deux thèmes.
- [ ] `:focus-visible` toujours visible (anneau `--ds-color-focus` 2 px, décalé) ; ne jamais faire `outline: none` sans le remplacer.
- [ ] Lien d'évitement `ds-skip-link` vers `<main id="main">`.
- [ ] Landmarks : `<aside>` ou `<nav>` avec `aria-label`, `<header>`, `<main>` ; une seule hiérarchie de titres par page.
- [ ] Statuts : jamais par la couleur seule ; emoji décoratif en `aria-hidden="true"` à côté d'un texte lisible.
- [ ] Bannière de file : `role="status"` + `aria-live="polite"`. Pas de `assertive` hors erreur bloquante.
- [ ] Dialogues natifs (`<dialog>` + `showModal()`) : piège du focus, Échap et retour du focus gérés par le navigateur.
- [ ] Onglets : rôles ARIA, `aria-selected`, flèches clavier.
- [ ] Tableaux : `<caption>`, `<th scope>`, tri annoncé par `aria-sort`.
- [ ] Formulaires : chaque champ a un `<label>` ; erreurs reliées par `aria-describedby` + `aria-invalid`.
- [ ] Boutons icône seuls : `aria-label` qui nomme l'objet (« Supprimer le dossier de … »).
- [ ] Cibles cliquables ≥ 24 × 24 px (boutons `--sm` à 30 px).
- [ ] Mise en page lisible à 200 % de zoom et à 320 px de large (pas de scroll horizontal hors tableaux).
- [ ] `prefers-reduced-motion` respecté.
- [ ] `lang="fr"` sur `<html>`.

---

## 6. Règles de formulation médico-légale

DataSyntis est un **outil d'aide à la préparation** de la RCP. La décision appartient à la RCP. Le vocabulaire doit refléter ce positionnement non prescriptif.

| Contexte | Formulation recommandée | À proscrire |
| :--- | :--- | :--- |
| Orientation alignée sur le référentiel | ✅ Conforme au référentiel | « Traitement validé », « Décision » |
| Écart possible au référentiel | 🧭 Adaptation suggérée · « à discuter en RCP » | « Non conforme », « Hors recommandations », « Erreur », rouge |
| Informations insuffisantes | ⏳ À discuter en RCP · ⚠️ Données insuffisantes | « Impossible », « Refusé » |
| Proposition d'un expert IA | « Proposition 1 — Discuter… », « Envisager… » | « Prescrire », « Il faut », « Le patient doit » |
| Urgence | 🚨 Priorité haute · « à présenter en premier » | « Urgence vitale » (qualification clinique réservée au médecin) |
| Pièce manquante | ⚠️ 2 pièces manquantes (liste factuelle) | « Dossier invalide » |
| Pied d'avis | « Proposition d'aide à la préparation de la RCP générée localement. La décision thérapeutique appartient à la RCP. » | — |
| Modification humaine | ✍️ Modifié manuellement · « Modifié par Dr X le JJ/MM/AAAA à HH:MM » | modification silencieuse |

Autres règles :

- Toujours **citer la source** (référentiel + section, document + page) sous une proposition (`ds-refs`).
- Dates au format français `JJ/MM/AAAA`, décimales avec virgule (`12,4 s`), unités cliniques avec une espace insécable (`412 U/mL`).
- Aucun nom de patient réel dans le styleguide, les tests ou les captures. Utiliser des noms fictifs explicites (`FICTIVE`, `EXEMPLE`, `MODÈLE`) et des IPP `…-FICTIF`.
