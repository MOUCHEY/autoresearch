"""
model.py — Les modèles de prédiction.

Tous les modèles suivent l'interface scikit-learn : `fit(X, y)` puis `predict(X)`.
Chaque modèle est un "Pipeline" : les étapes de prétraitement (remplacer les
valeurs manquantes, normaliser) sont APPRISES SUR L'ENTRAÎNEMENT SEULEMENT,
puis appliquées telles quelles à la validation et au test. C'est ce qui évite
les fuites d'information.

Modèles disponibles :
  mean                    : prédit toujours la moyenne de l'entraînement (référence)
  linear                  : régression linéaire (moindres carrés)
  random_forest           : forêt aléatoire (Breiman 2001)
  random_forest_tuned     : forêt + réglage par validation croisée INTERNE
  hist_gradient_boosting  : gradient boosting par histogrammes
"""

from __future__ import annotations

import numpy as np
from sklearn.base import clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV, GroupKFold, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def build_model(name: str, params: dict, seed: int, n_jobs: int = 1):
    """Fabrique un modèle neuf (non entraîné) à partir de son nom et de ses paramètres."""
    params = dict(params or {})
    if name == "mean":
        return DummyRegressor(strategy="mean")
    if name == "linear":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LinearRegression()),
        ])
    if name == "random_forest":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(random_state=seed, n_jobs=n_jobs, **params)),
        ])
    if name == "random_forest_tuned":
        grid = {f"model__{k}": v for k, v in params["grid"].items()}
        base = Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(n_estimators=params.get("n_estimators", 300),
                                            random_state=seed, n_jobs=n_jobs)),
        ])
        return TunedModel(base, grid, params.get("inner_folds", 3), seed)
    if name == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(random_state=seed, **params)
    raise ValueError(f"Modèle inconnu : {name}")


class TunedModel:
    """Réglage d'hyperparamètres par validation croisée INTERNE à l'entraînement.

    Les ensembles de validation et de test ne sont jamais vus pendant le
    réglage. Si des groupes (échafaudages) sont fournis, les plis internes
    respectent ces groupes (GroupKFold), pour rester cohérents avec le split.
    """

    def __init__(self, base, grid: dict, folds: int, seed: int):
        self.base, self.grid, self.folds, self.seed = base, grid, folds, seed
        self.search_ = None

    def fit(self, X, y, groups=None):
        if groups is not None:
            # Les échafaudages sont mélangés avant d'être répartis en plis, sinon
            # GroupKFold ferait toujours les mêmes plis quel que soit la graine.
            uniq = np.unique(groups)
            perm = dict(zip(uniq, np.random.default_rng(self.seed).permutation(len(uniq))))
            groups = np.array([perm[g] for g in groups])
            cv = GroupKFold(n_splits=self.folds)
        else:
            cv = KFold(n_splits=self.folds, shuffle=True, random_state=self.seed)
        self.search_ = GridSearchCV(clone(self.base), self.grid, cv=cv,
                                    scoring="neg_root_mean_squared_error", refit=True)
        self.search_.fit(X, y, groups=groups)
        return self

    def predict(self, X):
        return self.search_.predict(X)

    @property
    def best_params_(self):
        return {k.replace("model__", ""): v for k, v in self.search_.best_params_.items()}


def fit_model(model, X, y, groups=None):
    """Entraîne le modèle. Seul `TunedModel` utilise les groupes."""
    if isinstance(model, TunedModel):
        return model.fit(X, y, groups=groups)
    return model.fit(X, y)


def per_tree_std(model, X) -> np.ndarray | None:
    """Pour une forêt aléatoire : écart-type des prédictions des arbres.
    C'est une mesure (imparfaite) d'incertitude : si les arbres ne sont pas
    d'accord entre eux, la prédiction est moins fiable. Renvoie None sinon."""
    est = model.search_.best_estimator_ if isinstance(model, TunedModel) else model
    if not isinstance(est, Pipeline) or not isinstance(est[-1], RandomForestRegressor):
        return None
    Xt = est[:-1].transform(X)
    preds = np.stack([t.predict(Xt) for t in est[-1].estimators_])
    return preds.std(axis=0)
