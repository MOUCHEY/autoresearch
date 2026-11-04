# Revue de littérature — QuantLab V1

> **Statut des références.** Le réseau de l'environnement de développement bloquait les
> bases académiques (arXiv, SSRN, Crossref). Deux niveaux de vérification sont donc indiqués :
>
> - ✅ **vérifiée** : titre, auteurs, revue, volume et pages confirmés par recherche web pendant
>   la construction du labo (novembre 2026) ;
> - 📚 **citée de mémoire** : référence classique de la discipline. Elle est très probablement
>   exacte, mais **à vérifier** (titre, année, pages) avant d'en citer un résultat chiffré.
>
> Aucun résultat chiffré n'est attribué à un article si je n'en suis pas sûr. Les « résultats »
> ci-dessous résument les conclusions principales, pas des chiffres précis. Ne cite jamais un
> article à partir de ce résumé : lis l'article.

## Comment lire cette revue

Pour chaque publication :

- **Affirmation** : ce que l'article conclut.
- **Limites** : pourquoi on ne peut pas transposer directement le résultat à XAUUSD M5.
- **Pour le labo** : l'hypothèse falsifiable qu'on en tire, ou la méthode qu'on adopte.

Une hypothèse n'est jamais « vraie parce qu'un article l'a publiée ». Les publications
souffrent elles aussi de data snooping et de biais de publication (Harvey, Liu & Zhu 2016).

---

## A. Momentum et continuation

### Gao, Han, Li & Zhou (2018) — *Market intraday momentum* ✅
*Journal of Financial Economics* 129(2), 394–414. DOI 10.1016/j.jfineco.2018.05.009
- **Affirmation** : sur l'ETF S&P 500 (1993–2013), le rendement de la première demi-heure prédit
  celui de la dernière demi-heure. La prévisibilité est **plus forte les jours de forte
  volatilité**, de fort volume, de récession et de publications macro majeures.
- **Limites** : actions américaines, horizon « début de séance → fin de séance ». L'or au comptant
  se négocie presque 24 h/24 : il n'y a pas d'ouverture ni de clôture naturelles comparables.
- **Pour le labo** : c'est l'inspiration de **H-A2** (E02) : « la continuation est plus forte en
  volatilité élevée ». Notre transposition (cassure M5 + filtre de volatilité relative) est une
  *analogie*, pas une réplication.

### Elaut, Frömmel & Lampaert (2018) — *Intraday momentum in FX markets: Disentangling informed trading from liquidity provision* ✅
*Journal of Financial Markets* 37, 35–51. DOI 10.1016/j.finmar.2016.09.002
- **Affirmation** : momentum intrajournalier sur le marché des changes (RUB/USD). L'effet dépend
  de la concentration des échanges liée aux horaires de marché et s'accentue en période de crise.
- **Limites** : une seule paire, émergente, sur une période particulière.
- **Pour le labo** : l'effet, s'il existe, est probablement **conditionnel à la session et au
  régime**. D'où l'analyse par session et par tercile de volatilité dans chaque expérience.

### Moskowitz, Ooi & Pedersen (2012) — *Time series momentum* 📚
*Journal of Financial Economics* 104(2), 228–250.
- **Affirmation** : le rendement passé sur environ 12 mois d'un contrat à terme prédit son
  rendement futur (actions, devises, matières premières, obligations).
- **Limites** : horizon mensuel. Rien ne garantit que le phénomène existe à 5 minutes.
- **Pour le labo** : la « persistance des mouvements » est une hypothèse documentée à basse
  fréquence. À haute fréquence, elle reste **à démontrer**.

### Brock, Lakonishok & LeBaron (1992) — *Simple technical trading rules and the stochastic properties of stock returns* 📚
*Journal of Finance* 47(5), 1731–1764.
- **Affirmation** : des règles de moyennes mobiles et de cassure de range sur le Dow Jones
  semblaient prédictives. Les auteurs les comparent à des modèles nuls simulés par bootstrap.
- **Limites** : pas de coûts de transaction ; univers de règles choisi a posteriori (voir STW 1999).
- **Pour le labo** : méthode adoptée. On compare chaque stratégie à un **modèle nul simulé**
  (nos « entrées aléatoires »).

### Marshall, Cahan & Cahan (2008) — *Does intraday technical analysis in the U.S. equity market have value?* ✅
*Journal of Empirical Finance* 15(2), 199–210. DOI 10.1016/j.jempfin.2006.05.003
- **Affirmation** : sur des données à 5 minutes (SPY), aucune des quelque 7 800 règles techniques
  testées n'est significative une fois le data snooping pris en compte, et cela **avant coûts**.
- **Limites** : actions américaines, période courte (2002–2003 selon les résumés disponibles).
- **Pour le labo** : **prior sceptique**. L'hypothèse par défaut est qu'une règle technique
  intrajournalière simple n'a pas d'avantage net.

## B. Retour à la moyenne

### Lo & MacKinlay (1988) — *Stock market prices do not follow random walks: Evidence from a simple specification test* 📚
*Review of Financial Studies* 1(1), 41–66.
- **Affirmation** : le **test du ratio de variance** rejette la marche aléatoire pour des
  rendements hebdomadaires d'actions américaines.
- **Pour le labo** : outil de diagnostic **avant** toute stratégie. Un ratio de variance
  inférieur à 1 signale un retour à la moyenne ; supérieur à 1, de la persistance. C'est la
  prochaine expérience proposée (`variance_ratio_diagnostic`).

### Roll (1984) — *A simple implicit measure of the effective bid-ask spread in an efficient market* 📚
*Journal of Finance* 39(4), 1127–1139.
- **Affirmation** : le rebond bid-ask crée une **autocorrélation négative mécanique** des
  variations de prix, d'où un estimateur du spread : s = 2·√(−cov).
- **Pour le labo** : **piège majeur** pour la famille B. Un « retour à la moyenne » mesuré sur
  des prix de transaction (bid ou ask) peut n'être qu'un artefact du spread. On travaille donc
  en prix médian et on exécute au bid/ask simulé.

## C. Microstructure, sessions, spread

### Andersen & Bollerslev (1997) — *Intraday periodicity and volatility persistence in financial markets* 📚
*Journal of Empirical Finance* 4(2–3), 115–158.
- **Affirmation** : la volatilité intrajournalière suit un profil horaire marqué (devises,
  S&P 500). Il faut retirer cette périodicité pour étudier la dynamique de la volatilité.
- **Pour le labo** : un filtre « ATR élevé » sur M5 sélectionne surtout... **des heures**
  (Londres, New York). Notre variable `vol_regime` compare la volatilité du dernier jour à celle
  des 20 derniers jours pour réduire ce biais. La saisonnalité est aussi modélisée dans le jeu démo.

### Cai, Cheung & Wong (2001) — *What moves the gold market?* ✅
*Journal of Futures Markets* 21(3), 257–278.
- **Affirmation** : sur les futures or du COMEX, la saisonnalité intrajournalière pèse fortement
  sur la volatilité. Parmi 23 annonces macro américaines, l'emploi, le PIB, le CPI et le revenu
  personnel ont le plus d'effet. Après filtrage de la saisonnalité, la volatilité présente une
  mémoire longue.
- **Limites** : futures et non spot, données anciennes.
- **Pour le labo** : les **publications macro** sont un régime à part entière. V2 : ajouter un
  calendrier économique et tester séparément les fenêtres d'annonces.

### Evans & Lyons (2002) — *Order flow and exchange rate dynamics* 📚
*Journal of Political Economy* 110(1), 170–180.
- **Affirmation** : le flux d'ordres interbancaire signé explique une grande partie des
  variations quotidiennes des taux de change.
- **Limites** : il faut des **données d'ordres signés** (acheteur ou vendeur initiateur).
- **Pour le labo** : **aucune variable d'order flow en V1**. Le « tick volume » d'un fichier OHLC
  compte des mises à jour de prix, pas des ordres signés. Prétendre reconstruire l'order flow à
  partir de barres OHLC serait faux. Voir aussi Kyle (1985, *Econometrica* 53(6)) 📚 et Easley,
  López de Prado & O'Hara (2012, *Review of Financial Studies* 25(5), VPIN) 📚, dont la mesure
  est contestée par Andersen & Bondarenko (2014, *Journal of Financial Markets* 17) 📚.

### Corwin & Schultz (2012) — *A simple way to estimate bid-ask spreads from daily high and low prices* 📚
*Journal of Finance* 67(2), 719–760.
- **Pour le labo** : estimateur de spread de secours quand le fichier ne contient pas de spread
  (export HistData par exemple).

## D. Volatilité et gestion du risque

### Moreira & Muir (2017) — *Volatility-managed portfolios* 📚
*Journal of Finance* 72(4), 1611–1644.
- **Affirmation** : réduire l'exposition quand la volatilité récente est haute améliore le
  Sharpe de nombreux facteurs, car la volatilité ne prédit pas proportionnellement les rendements.

### Cederburg, O'Doherty, Wang & Yan (2020) — *On the performance of volatility-managed portfolios* ✅
*Journal of Financial Economics* 138(1), 95–117. DOI 10.1016/j.jfineco.2020.04.015
- **Affirmation** : sur 103 stratégies actions, les versions gérées par la volatilité ne battent
  pas systématiquement les versions non gérées **hors échantillon**. Les alphas des régressions de
  « spanning » ne sont pas exploitables en temps réel.
- **Pour le labo** : un résultat qui semble solide en échantillon peut disparaître hors
  échantillon, ce que notre contrôle positif a illustré concrètement (voir `report.md`, §6.2).
  La taille de position normalisée par la volatilité (V1.1) est un **outil de gestion du
  risque**, pas une source d'avantage supposée.

### Faits stylisés — Mandelbrot (1963) 📚, Engle (1982) 📚, Bollerslev (1986) 📚, Cont (2001) 📚
*Journal of Business* 36(4) ; *Econometrica* 50(4) ; *Journal of Econometrics* 31(3) ;
*Quantitative Finance* 1(2).
- **Affirmation** : queues épaisses, volatilité en grappes (ARCH/GARCH), quasi-absence
  d'autocorrélation linéaire des rendements (sauf aux très petites échelles).
- **Pour le labo** : le jeu démo reproduit ces propriétés **sans** prévisibilité des rendements.
  Les erreurs-types « naïves » (iid) sont trompeuses avec des queues épaisses, d'où le bootstrap.

## E. Machine learning (famille D — pas encore testée)

- **Gu, Kelly & Xiu (2020)**, *Empirical asset pricing via machine learning*, *Review of Financial
  Studies* 33(5), 2223–2273 📚. Arbres et réseaux de neurones dominent en prévision mensuelle de
  rendements d'actions. Le contexte est transversal et mensuel, très loin de M5.
- **Krauss, Do & Huck (2017)**, *European Journal of Operational Research* 259(2), 689–702 📚.
  Random Forest, gradient boosting et réseaux profonds en arbitrage statistique sur le S&P 500 ;
  les rendements déclinent dans le temps et les coûts pèsent lourd.
- **López de Prado (2018)**, *Advances in Financial Machine Learning*, Wiley 📚. Labels à barrières,
  **purge et embargo**, validation croisée combinatoire. C'est la référence méthodologique
  adoptée pour la V2 ML.
- **Bergmeir & Benítez (2012)**, *Information Sciences* 191, 192–213 📚. Validation croisée et
  séries temporelles.
- **Pour le labo** : on n'ajoute du ML que si les diagnostics (ratio de variance, effets de
  session) montrent une structure. Un modèle complexe sur un signal nul ne fait qu'apprendre le bruit.

## F. Méthodologie : data snooping, tests multiples, sur-ajustement

| Référence | Statut | Ce qu'on en tire (implémenté dans `evaluation.py`) |
|---|---|---|
| White (2000), *A reality check for data snooping*, *Econometrica* 68(5), 1097–1126 | 📚 | Tester le **meilleur** de N essais exige de corriger pour N |
| Sullivan, Timmermann & White (1999), *Journal of Finance* 54(5), 1647–1691 | 📚 | Les règles de BLL (1992) perdent leur significativité une fois le snooping corrigé |
| Hansen (2005), test SPA, *Journal of Business & Economic Statistics* 23(4), 365–380 | 📚 | Version plus puissante du *reality check* (V2) |
| Harvey, Liu & Zhu (2016), *Review of Financial Studies* 29(1), 5–68 | 📚 | Avec des centaines de facteurs testés, un t > 2 ne suffit plus (seuil proposé ≈ 3) |
| Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*, *Journal of Portfolio Management* 40(5), 94–107 | ✅ | **Deflated Sharpe Ratio** : Sharpe corrigé du nombre d'essais, de l'asymétrie et de l'aplatissement |
| Bailey, Borwein, López de Prado & Zhu (2014), *Notices of the AMS* 61(5), 458–471 | 📚 | Le sur-ajustement de backtest est quasi garanti quand on teste beaucoup de configurations |
| Lo (2002), *The statistics of Sharpe ratios*, *Financial Analysts Journal* 58(4), 36–52 | 📚 | Le Sharpe annualisé par √q est biaisé si les rendements sont autocorrélés |
| Politis & Romano (1994), *The stationary bootstrap*, *JASA* 89(428), 1303–1313 | 📚 | Intervalles de confiance robustes à la dépendance |
| Holm (1979), *Scandinavian Journal of Statistics* 6(2), 65–70 | 📚 | Correction séquentielle des tests multiples |
| Aronson (2006), *Evidence-Based Technical Analysis*, Wiley | 📚 | Lecture recommandée pour débuter : biais de data mining expliqué aux praticiens |

---

## Banque d'hypothèses (état au 2026-11-04)

| ID | Famille | Hypothèse falsifiable | Source | Expérience | Statut |
|---|---|---|---|---|---|
| H-A1 | A | Cassure Donchian 20 barres, détention 1 h : espérance nette > 0 | BLL 1992 (scepticisme : MCC 2008) | E01 | Rejetée **sur données DÉMO** — à tester sur données réelles |
| H-A2 | A | Même cassure, volatilité relative haute : espérance nette > référence | Gao et al. 2018 (analogie) | E02 | Rejetée **sur DÉMO** — à tester sur données réelles |
| H-A3 | A | Même cassure, volatilité basse (« compression ») : espérance nette > référence | Folklore praticien (aucune source académique) | E03 | Rejetée **sur DÉMO** — à tester sur données réelles |
| H-B1 | B | Ratio de variance M5 < 1 (retour à la moyenne) dans au moins un régime | Lo & MacKinlay 1988 | — | À coder (diagnostic) |
| H-C1 | C | Rendement moyen et volatilité diffèrent selon l'heure UTC ; le spread varie à l'inverse de la liquidité | Andersen & Bollerslev 1997 ; Cai et al. 2001 | — | À coder (diagnostic) |
| H-C2 | C | La volatilité post-annonce macro US persiste plus d'une heure | Cai et al. 2001 | — | Requiert un calendrier économique |
| H-D1 | D | Une régression logistique sur variables causales bat la classe majoritaire hors échantillon | López de Prado 2018 (protocole) | — | Après H-B1 / H-C1 |
