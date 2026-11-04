# Archive — run officiel V1.0 (remplacé par V1.1)

Ce run (commit `f70c965`, évaluateur `b11733ddb055`) est conservé pour la traçabilité.

**Pourquoi il a été remplacé :** le Risk Manager a constaté que le dimensionnement
« 0,25 % du capital par ATR M5 » donnait un levier effectif d'environ 3,6× pour des trades
tenus 12 barres. Le risque réel par trade était environ √12 ≈ 3,5 fois plus grand
qu'annoncé, d'où un drawdown de −92 % sur E01. La V1.1 dimensionne par ATR × √hold et
ajoute des scénarios Monte Carlo de séries de pertes.

**Ce qui ne change pas :** la métrique principale (espérance nette en bps par trade), les
trades, les tests statistiques et les décisions sont identiques, car ils ne dépendent pas
de la taille des positions. Le même ensemble pré-enregistré E01–E03 (+ sensibilité E04) a
été rejoué à l'identique en V1.1 : ce ne sont donc pas de nouveaux essais.
