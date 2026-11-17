# Consignes de Jeunathan pour QuantLab

Écrites ici pour ne jamais dépendre d'une seule conversation. On ajoute, on n'efface pas.

## 2026-11-17 — reprise du labo sur l'iMac (après la session cloud)

- **Pédagogie** : je débute en programmation scientifique. À chaque étape importante, expliquer
  ce qu'on cherche, pourquoi c'est pertinent, comment marche le code, ce que les résultats
  permettent réellement de conclure, et ce que je dois apprendre pour refaire l'expérience seul.
- **Recherche et paper trading uniquement** : aucun ordre réel, aucune connexion à un compte de courtage.
- **Aucune donnée payante sans mon accord** (dont l'accès S3 « Requester Pays » de Dukascopy).
  Sur un 429 : ne pas insister, ne pas changer d'identité (User-Agent), passer à l'export MT5.
- **Évaluateur** : ne jamais modifier `evaluation.py` ni `backtest.py` pour améliorer un score. Si un
  changement y semble nécessaire : s'arrêter et me demander. Tout `--relock` est justifié par écrit
  et validé par moi.
- **Test final** : jamais `--final-test` sans mon accord explicite, et seulement pour une
  expérience `ACCEPT_CANDIDATE`.
- **Pré-enregistrement** : ne modifier ni les hypothèses ni les paramètres de E01–E03 ; elles ont
  été écrites avant d'avoir vu un seul vrai prix.
- **Budget** : 10 expériences par jeu de données ; chaque essai compte dans les corrections pour
  tests multiples.
- Ne jamais présenter un résultat DÉMO comme réel. Ne pas confondre corrélation et causalité.
  Aucune publication ni aucun résultat inventé.
- Les données ne sont jamais commitées (`data/` est dans `.gitignore`).
- Commits fréquents, messages clairs ; push sur `quantlab-v1` ; **pas de pull request** sauf demande.
- **Étape 4** (diagnostics sans stratégie, puissance du labo, machine learning) : seulement après le
  test sur données réelles, et en me demandant avant. Le ML uniquement si les diagnostics montrent
  une structure exploitable.
