# QuantLab — suivi et relais entre sessions

## RELAIS — 2026-11-17 13:40 (session Mac, reprise du labo cloud)

- **Fait** : étape 1, commit `4b929df`, avec artefacts dans `runs/<data_hash>/` et garde du test final sur une période réelle déjà vue ; 19/19 tests ; `verify_lock` intact, empreinte évaluateur `14a493d542ad`. Mois test 2024-01 validé : 30 268 M1, clôtures 2 002–2 079, spread médian 0,32 USD, 0 barre OHLC incohérente ; le trou du 15/01 correspond au jour férié MLK, les rendements extrêmes aux annonces NFP du 05/01 et CPI du 11/01.
- **En cours** : `caffeinate -i .venv/bin/python -u data_loader.py fetch --start 2023-01-01 --end 2026-10-31 > data/fetch.log`, lancé à 13 h 38. Mesuré : 12,9 s par fichier (latence du serveur, pas de 429), 2 346 fichiers, soit environ 8,4 h ; fin vers 22 h. Si c'est interrompu, relancer la même commande : le cache mensuel `data/dukascopy/XAUUSD/` est sauté.
- **Prochaine action** : `tail data/fetch.log` (46 mois, aucun 429 ni ConnectionError) ; `python data_loader.py check`, en commentant chaque avertissement ; `data.mode: real` puis **commit AVANT** `python experiment_runner.py --auto 2`.
- **Analyse étape 3** : lire `results.csv` et `runs/<hash_réel>/*/summary.json` (checks, by_fold, by_session, by_vol_tercile, by_direction, stress, Monte Carlo), comparer à la démo (`636e8307230d031c`), puis faire valider le verdict par un validateur indépendant (N2). Ensuite `report.md` (nouvelle section « Données réelles »), `research_memory.md` (ajout), `python figures.py`, commit et push.
- **Décisions** : clone dans `~/autoresearch-quantlab` (`~/autoresearch` est le dépôt de Karpathy, laissé intact). Le dépôt GitHub est PUBLIC (fork) : les commits utilisent l'adresse noreply de GitHub, réglée localement.
- **Interdits** : voir `tasks/consignes-jeunathan.md` (pas de `--final-test` sans accord, pas de modification de l'évaluateur, pas de S3 payant, pas de pull request).
