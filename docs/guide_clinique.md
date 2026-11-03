# 🩺 MedDataSyntis — Guide à l'usage des Cliniciens

Bienvenue dans le guide d'utilisation de **MedDataSyntis**. Cet espace est conçu pour vous aider à comprendre comment notre solution d'intelligence artificielle locale vous accompagne dans la préparation et la tenue des **Réunions de Concertation Pluridisciplinaire (RCP)** (oncologie digestive, amyotrophie spinale, etc.).

---

## 🌟 La Vision MedDataSyntis

La préparation d'une RCP est chronophage et exigeante. **MedDataSyntis** a été créé en étroite collaboration avec des professionnels de santé pour automatiser les tâches administratives et de synthèse complexes, vous permettant de vous concentrer sur votre cœur de métier : **la décision thérapeutique**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      Le Flux de Travail MedDataSyntis                  │
├────────────────────────────────────────────────────────────────────────┤
│  [1] Dépôt PDF ──► [2] Analyse & OCR ──► [3] Triage ──► [4] Aide TNCD  │
│    (Dossiers)       (Pièces manquantes)  (Priorisation) (Décisions)    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 💡 Fonctionnalités Clés pour le Praticien

### 1. Synthèse Automatisée du Dossier Patient
Dès que les documents médicaux (comptes-rendus d'anatomopathologie, d'imagerie, de chirurgie) sont importés, MedDataSyntis en extrait les informations cruciales :
* **Identité et Contexte général** (Âge, antécédents, état général OMS/ECOG).
* **Données Oncologiques** (Localisation tumorale, type histologique, classification TNM/pTNM).
* **Marqueurs Biologiques** et examens d'imagerie clés (TDM, IRM, TEP-scan).

### 2. Détection Préventive des Dossiers Incomplets (Missing Records)
Pour éviter de reporter l'examen d'un patient lors de la réunion par manque d'informations :
* L'IA analyse la présence de toutes les pièces requises selon le type de pathologie suspecté.
* Une **alerte visuelle immédiate** est émise si un document ou une donnée obligatoire (ex. taille tumorale, statut de la biopsie) fait défaut.

### 3. Triage et Priorisation des Dossiers
Les réunions RCP disposent d'un temps limité. MedDataSyntis analyse la complexité clinique intrinsèque de chaque cas et propose :
* Un **ordre de passage optimisé** afin de traiter en priorité les cas hautement urgents ou complexes nécessitant un débat approfondi.
* Un gain de temps sur les dossiers standards dont la prise en charge est balisée.

### 4. Alignement Scientifique : Le Référentiel TNCD
MedDataSyntis intègre nativement le **Thésaurus National de Cancérologie Digestive (TNCD)**, la référence scientifique officielle en France :
* L'IA interroge en temps réel le référentiel TNCD en fonction des caractéristiques du patient.
* Elle vous suggère des propositions de schémas thérapeutiques (chirurgie première, chimiothérapie péri-opératoire, radio-chimiothérapie) conformes aux recommandations à jour, servant de garde-fou clinique.

---

## 🔒 Confidentialité & Sécurité des Données (Souveraineté Totale)

> [!CAUTION] **Zéro Cloud — Zéro Fuite de Données**
> Les données de vos patients ne quittent **jamais** l'établissement de santé. MedDataSyntis est une solution **local-first** :
> * Aucun appel à des serveurs tiers ou des API publiques (type OpenAI, Google ou Anthropic).
> * Les modèles de traitement du langage (LLM) s'exécutent **localement** sur l'infrastructure sécurisée de l'hôpital.
> * Conformité totale avec le **RGPD** et les exigences de l'**Hébergement de Données de Santé (HDS)**.

---

## 🖥️ Navigation dans la Nouvelle Interface Web Material Design 3 (`web/`)

La nouvelle interface web **DataSyntis Material Design 3** a été pensée pour offrir une lisibilité hospitalière immédiate (zéro éblouissement en salle de projection grâce aux thèmes **Auto / Clair / Sombre**, conformité accessibilité **WCAG 2.2 AA**, et ergonomie adaptée aussi bien aux grands écrans de RCP qu'aux tablettes et mobiles).

### 📋 1. Worklist RCP (`/worklist`)
* **Indicateurs clés (KPI) cliquables** : visualisez en un coup d'œil le nombre de dossiers structurés, les cas en **Priorité haute**, les **Dossiers incomplets** et les **Adaptations suggérées**. Cliquez sur un KPI pour filtrer instantanément la liste.
* **Vue Tableau dense ou Grille de cartes** :
  * Tri multi-colonnes (Priorité, Patient, Complétude, Orientation pré-RCP, Spécialités requises, Dernière RCP).
  * **Double-clic** sur n'importe quelle ligne pour ouvrir directement le dossier longitudinal du patient.
  * **Menu d'actions rapides (`...`)** sur chaque patient pour ouvrir le dossier, consulter directement les avis pré-RCP, importer une nouvelle pièce PDF ou signaler une anomalie.

### 🗓️ 2. Ordre du Jour de la Prochaine Séance RCP (`/agenda`)
* **Programmation en 1 clic (`Programmer une nouvelle réunion`)** : choisissez la date de la réunion RCP, le mode d'organisation, les spécialistes présents et les dossiers inscrits.
* **2 stratégies d'organisation automatique** :
  * **Regroupement par spécialité & urgence** : regroupe les dossiers mobilisant les mêmes spécialistes dans des créneaux contigus afin de minimiser le temps de présence requis de chaque praticien, tout en plaçant les urgences en tête de chaque groupe.
  * **Urgence clinique stricte** : classe tous les dossiers par niveau de priorité décroissant.
* **Suivi du quorum et filtre visuel par spécialité** :
  * Visualisez les créneaux de passage de chaque expert (`Dossiers #1 à #3`) et les éventuelles alertes de quorum si un spécialiste requis est absent.
  * Mettez en évidence en temps réel tous les dossiers d'une spécialité (via le sélecteur ou en cliquant sur un badge de spécialité) et réordonnez/épinglez manuellement n'importe quel dossier.
* **Conduite de la séance RCP** : cliquez sur **`Ouvrir le 1er dossier (#1)`** pour démarrer la séance et passer d'un patient au suivant grâce à la barre de navigation **`← Dossier précédent` / `Dossier suivant →`**.

### 📁 3. Dossier Patient Longitudinal (`/patients/:id`)
* **Carte synoptique unifiée & Frise chronologique RCP** :
  * Bandeau supérieur regroupant l'identité, l'urgence, la complétude (avec infobulle des pièces manquantes), l'orientation pré-RCP et les spécialités requises.
  * **Repères cliniques longitudinaux** toujours visibles avec calcul automatique des variations (**deltas** : ex. évolution du CA 19-9 en oncologie ou des scores moteurs HFMSE / CHOP-INTEND / RULM en SMA).
  * **Frise chronologique RCP repliable** permettant de naviguer entre toutes les séances passées du patient ou d'ajouter une pièce pour la **`Prochaine séance`**.
* **Vue scindée (Liseuse PDF + Synthèse structurée)** :
  * **À gauche** : liseuse PDF native extensible en un clic (`Agrandir le PDF`).
  * **À droite — Onglet `Données cliniques`** : rubriques cliniques regroupées par pôles, **repliées par défaut** avec leur conclusion visible dès le titre (`Tout déplier / Tout replier`).
  * **Édition manuelle préservée (`✍️ Modifié manuellement`)** : chaque rubrique peut être corrigée manuellement par le clinicien ; toute modification humaine est tracée et **protégée contre l'écrasement** lors des relances IA ultérieures.
  * **À droite — Onglet `Avis & Orientation pré-RCP`** :
    * **Liste interactive des éléments manquants** : masquez ou restaurez individuellement les éléments signalés par l'IA une fois vérifiés par le secrétariat.
    * **Proposition d'orientation pré-RCP & Avis par spécialité** : propositions argumentées et sourcées avec liens directs vers la page exacte du référentiel PDF (**TNCD** ou **PNDS**) ou du compte rendu patient.
* **Tiroir latéral Assistant IA (`Co-Pilot Side Sheet`)** :
  * Accessible à tout moment via le bouton flottant **`Assistant IA`** en bas à droite sans masquer la lecture du dossier.
  * Permet de choisir la **spécialité médicale consultée**, le périmètre (**Tout le suivi longitudinal** ou **Séance courante**), et d'insérer des **questions cliniques suggérées** via le bouton partagé.

### 📚 4. Référentiels (`/guidelines`), Experts IA (`/agents`) & Supervision
* **Référentiels (`/guidelines`)** : consultation en plein écran des thésaurus scientifiques (**TNCD** en oncologie digestive, **PNDS** en SMA) accompagnée de l'Assistant IA documentaire sourcé.
* **Catalogue des Experts IA (`/agents`)** : transparence complète sur les instructions système, les prompts d'extraction par rubrique et les référentiels rattachés à chaque agent.
* **Import PDF par lot (`/ingest`)** : dépôt glisser-déposer de plusieurs comptes rendus PDF avec rattachement automatique ou manuel au patient et suivi d'avancement en direct.
* **Supervision de la file GPU (`/admin/queue`) & Signalements (`/feedback`)** : suivi temps réel (SSE) des analyses en cours, relance des tâches en échec, libération des verrous GPU et remontée d'anomalies cliniques ou d'interface.

---

## 🖥️ Navigation dans l'Interface Historique Streamlit (`application/app-ui.py`)

L'interface est structurée pour être simple et intuitive, accessible depuis n'importe quel navigateur interne à l'hôpital.

### 📇 1. Dossiers Patients (Cards)
* **Votre tableau de bord central** : structuré en deux sections complémentaires :
  * **📁 Dossiers Patients (en haut)** : affiche une carte par patient, synthétisée à partir de sa **dernière fiche RCP analysée** (urgence, statut d'exhaustivité, intervention conseillée, experts pertinents et nombre total de RCP du patient).
  * **📄 Dernières RCP scannées (en dessous)** : présente les dernières fiches RCP individuelles par ordre chronologique de numérisation/import.

### 📝 2. Dossier Patient (Datas)
* Vue détaillée unifiée du **Dossier Patient**, organisée en **3 onglets principaux** en haut de page :
  * **👤 Données patient** : affiche le bandeau d'identité administrative du patient ainsi que la **dernière fiche RCP analysée** (PDF à gauche et onglets *Données Cliniques*, *Assistant IA sur la fiche* et *Aperçu du document* à droite).
  * **🕰️ Historique des fiches RCP** : permet de remonter dans le temps sur toutes les fiches RCP du patient via un sélecteur chronologique, avec la même vue détaillée par fiche (PDF + *Données Cliniques*, *Assistant IA sur la fiche* isolé sur la fiche courante, et *Aperçu du document*).
  * **💬 Assistant IA sur le dossier** : onglet de chat interrogeant l'agent expert sur **l'intégralité du dossier patient** (toutes ses fiches RCP passées et présentes, l'historique complet des informations IA extraites via le tool `get_patient_ai_history`, et les référentiels TNCD).
  * **🔄 Relance IA (Rerun) fiche par fiche** : la relance de l'analyse IA (`🔄 Relancer cette RCP`, `:material/robot: AI exec` par rubrique, ou `:repeat: AI process` en Power mode) est sélectionnable et exécutée **exclusivement RCP par RCP** (jamais sur l'ensemble du dossier simultanément).

### 🚀 3. Charger le/les fichier(s) (Upload)
* Espace de dépôt sécurisé supportant l'import **unitaire ou par lot (batch)** de plusieurs fiches PDF RCP.
* **Association à un patient** :
  * **Mode Automatique (par défaut)** : lance l'indexation RAG et l'extraction administrative par l'IA (`Prénom`, `Nom`, `Date de naissance`) pour créer automatiquement le patient ou rattacher la fiche à un dossier patient existant.
  * **Association manuelle** : permet de sélectionner un patient existant (globalement pour le lot ou fichier par fichier avant de lancer l'import).

### 🤖 4. Agents and Ressources
* Vue transparente sur l'activité des "agents" IA spécialisés à l'œuvre. Vous pouvez voir quel agent (le "Docteur virtuel" ou le "Spécialiste TNCD") a extrait et validé les données.

---

## 🧑‍⚕️ Vos Retours sont Précieux

MedDataSyntis est un projet open-source évolutif. Si vous remarquez des écarts dans les résumés ou si vous souhaitez suggérer l'ajout d'un nouveau référentiel clinique, vous pouvez soumettre un signalement directement via l'onglet **Bug reports (Reports)** dans l'interface, ou vous rapprocher de votre équipe informatique hospitalière.
