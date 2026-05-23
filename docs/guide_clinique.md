# 🩺 Oncoflow — Guide à l'usage des Cliniciens

Bienvenue dans le guide d'utilisation d'**Oncoflow**. Cet espace est conçu pour vous aider à comprendre comment notre solution d'intelligence artificielle locale vous accompagne dans la préparation et la tenue des **Réunions de Concertation Pluridisciplinaire (RCP)** en oncologie digestive.

---

## 🌟 La Vision Oncoflow

La préparation d'une RCP est chronophage et exigeante. **Oncoflow** a été créé en étroite collaboration avec des professionnels de santé pour automatiser les tâches administratives et de synthèse complexes, vous permettant de vous concentrer sur votre cœur de métier : **la décision thérapeutique**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Le Flux de Travail Oncoflow                     │
├────────────────────────────────────────────────────────────────────────┤
│  [1] Dépôt PDF ──► [2] Analyse & OCR ──► [3] Triage ──► [4] Aide TNCD  │
│    (Dossiers)       (Pièces manquantes)  (Priorisation) (Décisions)    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 💡 Fonctionnalités Clés pour le Praticien

### 1. Synthèse Automatisée du Dossier Patient
Dès que les documents médicaux (comptes-rendus d'anatomopathologie, d'imagerie, de chirurgie) sont importés, Oncoflow en extrait les informations cruciales :
* **Identité et Contexte général** (Âge, antécédents, état général OMS/ECOG).
* **Données Oncologiques** (Localisation tumorale, type histologique, classification TNM/pTNM).
* **Marqueurs Biologiques** et examens d'imagerie clés (TDM, IRM, TEP-scan).

### 2. Détection Préventive des Dossiers Incomplets (Missing Records)
Pour éviter de reporter l'examen d'un patient lors de la réunion par manque d'informations :
* L'IA analyse la présence de toutes les pièces requises selon le type de pathologie suspecté.
* Une **alerte visuelle immédiate** est émise si un document ou une donnée obligatoire (ex. taille tumorale, statut de la biopsie) fait défaut.

### 3. Triage et Priorisation des Dossiers
Les réunions RCP disposent d'un temps limité. Oncoflow analyse la complexité clinique intrinsèque de chaque cas et propose :
* Un **ordre de passage optimisé** afin de traiter en priorité les cas hautement urgents ou complexes nécessitant un débat approfondi.
* Un gain de temps sur les dossiers standards dont la prise en charge est balisée.

### 4. Alignement Scientifique : Le Référentiel TNCD
Oncoflow intègre nativement le **Thésaurus National de Cancérologie Digestive (TNCD)**, la référence scientifique officielle en France :
* L'IA interroge en temps réel le référentiel TNCD en fonction des caractéristiques du patient.
* Elle vous suggère des propositions de schémas thérapeutiques (chirurgie première, chimiothérapie péri-opératoire, radio-chimiothérapie) conformes aux recommandations à jour, servant de garde-fou clinique.

---

## 🔒 Confidentialité & Sécurité des Données (Souveraineté Totale)

> [!CAUTION] **Zéro Cloud — Zéro Fuite de Données**
> Les données de vos patients ne quittent **jamais** l'établissement de santé. Oncoflow est une solution **local-first** :
> * Aucun appel à des serveurs tiers ou des API publiques (type OpenAI, Google ou Anthropic).
> * Les modèles de traitement du langage (LLM) s'exécutent **localement** sur l'infrastructure sécurisée de l'hôpital.
> * Conformité totale avec le **RGPD** et les exigences de l'**Hébergement de Données de Santé (HDS)**.

---

## 🖥️ Navigation dans l'Interface Streamlit

L'interface est structurée pour être simple et intuitive, accessible depuis n'importe quel navigateur interne à l'hôpital.

### 📇 1. Liste RCP (Cards)
* **Votre tableau de bord central** : affiche tous les patients programmés pour la prochaine RCP.
* Chaque patient est présenté sous forme de carte résumée indiquant son niveau d'urgence, son statut d'exhaustivité (complet/incomplet) et la synthèse de sa situation.

### 📇 2. Fiche RCP (Datas)
* Vue détaillée d'un patient sélectionné.
* Présentation claire de la **frise chronologique** des soins, des antécédents, et du rapport d'anomalie.
* Permet d'interroger directement l'assistant IA sur un point précis du dossier ou sur une recommandation TNCD liée au cas.

### 🚀 3. Charger le/les fichier(s) (Upload)
* Espace de dépôt sécurisé par glisser-déposer.
* Glissez simplement le dossier patient sous format PDF (scanné ou numérique). L'OCR local s'occupe de le déchiffrer instantanément.

### 🤖 4. Agents and Ressources
* Vue transparente sur l'activité des "agents" IA spécialisés à l'œuvre. Vous pouvez voir quel agent (le "Docteur virtuel" ou le "Spécialiste TNCD") a extrait et validé les données.

---

## 🧑‍⚕️ Vos Retours sont Précieux

Oncoflow est un projet open-source évolutif. Si vous remarquez des écarts dans les résumés ou si vous souhaitez suggérer l'ajout d'un nouveau référentiel clinique, vous pouvez soumettre un signalement directement via l'onglet **Bug reports (Reports)** dans l'interface, ou vous rapprocher de votre équipe informatique hospitalière.
