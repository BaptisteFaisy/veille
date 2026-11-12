# Veille — Trous documentés (GAP)

> *Ce document liste les manques de QNX SDP 8.0 que Veille exploite, avec leur ancrage documentaire. Comme pour Tamis, chaque affirmation est à vérifier page à page dans le SDP installé avant d'être gravée (section 13 du cahier des charges).*

---

## M1 — Aucun framework d'alarme médicale

**Trou.** QNX SDP 8.0 ne fournit ni priorités d'alarme IEC 60601-1-8, ni profils sonores, ni verrouillage/acquittement d'alarme médicale. Tout est à implémenter à la main.

**Ancrage.** Inventaire QNX SDP 8.0 (bibliothèques fournies : `libscreen`, `io-audio`, `io-pkt`, resource managers, mais rien de spécifique aux alarmes médicales).

**Ce que Veille apporte.** Un framework qui implémente les priorités (haute/moyenne/basse/technique), les profils sonores (pulses/pauses), le verrouillage et l'acquittement, avec bornes configurables.

---

## M2 — La latence de bout en bout n'est pas prouvée

**Trou.** Le System Profiler QNX (Momentics) mesure des échantillons de latence, mais n'explore pas les états de défaillance et ne certifie pas de borne pire-cas. Il dit « voilà ce qui s'est passé », pas « voilà ce qui ne peut pas se dépasser ».

**Ancrage.** Documentation System Profiler / `tracelogger` : outils de mesure et de visualisation, pas de preuve de borne.

**Ce que Veille apporte.** `veille_proof_explore` : exploration exhaustive de tous les états de défaillance, avec verdict `PROOF_COMPLETE` (borne tenue partout) ou `PROOF_COUNTEREXAMPLE` (contre-exemple rejouable).

---

## M3 — Pas d'exploration exhaustive d'états

**Trou.** Rien dans QNX SDP n'énumère les combinaisons de défaillances (capteur × bus × priorité × alarme × étage) pour vérifier une propriété temporelle dans chaque cas.

**Ancrage.** Inventaire : pas d'outil de model-checking ou d'exploration d'états fourni.

**Ce que Veille apporte.** Un modèle d'automate fini + DFS exhaustif (300 états en S, ~18432 en C), avec élagage des combinaisons impossibles.

---

## M4 — IEC 60601-1-8 non outillé

**Trou.** La norme impose des caractéristiques d'alarme (délais de déclenchement, priorités, profils sonores, verrouillage, acquittement, alarmes techniques). QNX ne fournit ni support natif, ni test de conformité.

**Ancrage.** Norme externe (IEC 60601-1-8) ; inventaire QNX : pas de brique « alarme médicale ».

**Ce que Veille apporte.** Implémentation des priorités/profils/acquittement + vérification de conformité par exploration (P1, P2, P3).

---

## M5 — Pas de certificat de latence exploitable en IEC 62304

**Trou.** Aucun générateur de rapport d'audit horodaté et empreinté (SHA-256) pour les exigences temporelles d'alarme. L'intégrateur rédige son dossier à la main.

**Ancrage.** Inventaire : `secpol` a `secpolmonitor` pour les événements de politique, mais rien pour les alarmes médicales.

**Ce que Veille apporte.** `veille_report_markdown` : certificat d'audit avec config (empreinte), méthode (exploration exhaustive), résultat (borne tenue / contre-exemple), version, horodatage — directement exploitable dans un dossier IEC 62304.

---

## M6 — La défaillance de capteur ne déclenche pas d'alarme technique bornée

**Trou.** Sur un moniteur classique, un capteur mort = silence (pas d'échantillon → pas d'alarme). IEC 60601-1-8 exige une **alarme technique** (défaillance du système) dans un délai borné.

**Ancrage.** IEC 60601-1-8 §alarmes techniques ; microkernel QNX : `CHANNEL` disconnect notifie la mort d'un pair, mais rien n'en fait une alarme technique bornée par défaut.

**Ce que Veille apporte.** `veille_state_chain_broken` détecte la panne d'un étage critique → verdict `VEILLE_TECHNICAL_ALARM` avec borne `B_tech = 50 ms`. Sur cible, le `CHANNEL` disconnect déclenche l'alarme technique.

---

## Synthèse

| Trou | Catégorie | Preuve que Veille apporte |
|---|---|---|
| M1 framework d'alarme | Fonctionnel | priorités/profils/acquittement implémentés |
| M2 latence non prouvée | Temporel | exploration exhaustive + verdict PROOF_COMPLETE |
| M3 pas d'exploration d'états | Méthode | automate fini + DFS, 300→18432 états |
| M4 IEC 60601-1-8 non outillé | Conformité | propriétés P1/P2/P3 vérifiées |
| M5 pas de certificat IEC 62304 | Audit | rapport Markdown empreinté SHA-256 |
| M6 capteur mort = silence | Sûreté | alarme technique bornée (`chain_broken`) |

**Point commun avec les projets frères.** Ambre exploite l'absence de preuve de durabilité du crash (UN R160) ; Relais exploite l'absence de failover à latence bornée outillé (UN R79) ; Tamis exploite l'absence d'analyse statique des politiques de sécurité. **Veille exploite l'absence de preuve de latence d'alarme médicale (IEC 60601-1-8 / IEC 62304).** Même méthode (preuve par exploration exhaustive + jumeau de vérification), domaine différent (médical).

---

*GAP.md v0.1 — à compléter après lecture page à page du SDP installé.*
