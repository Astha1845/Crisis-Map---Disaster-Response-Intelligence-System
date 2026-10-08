"""Shared helpers: outlier capping transformer and Apriori rule mining.

The Winsorizer is part of the saved sklearn pipelines, so this module must be
importable both at training time (train.py) and at serving time (app.py).
"""
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


class Winsorizer(BaseEstimator, TransformerMixin):
    """Caps each numeric column at the given lower/upper percentiles (learned on train data)."""

    def __init__(self, lower=1, upper=99):
        self.lower = lower
        self.upper = upper

    def fit(self, X, y=None):
        X = np.asarray(X, dtype=float)
        self.low_ = np.nanpercentile(X, self.lower, axis=0)
        self.high_ = np.nanpercentile(X, self.upper, axis=0)
        return self

    def transform(self, X):
        # NaNs are preserved here and handled by the imputer that follows.
        return np.clip(np.asarray(X, dtype=float), self.low_, self.high_)

    def get_feature_names_out(self, input_features=None):
        return np.asarray(input_features, dtype=object)


# --------------------------------------------------------------------------- #
# Apriori
# --------------------------------------------------------------------------- #
def _own_apriori(onehot: pd.DataFrame, min_support: float, max_len: int):
    """Level-wise Apriori. Returns {tuple(column_indices): support}."""
    matrix = onehot.to_numpy(dtype=bool)
    n_items = matrix.shape[1]
    freq = {}
    current = []
    for i in range(n_items):
        s = matrix[:, i].mean()
        if s >= min_support:
            freq[(i,)] = float(s)
            current.append((i,))
    k = 2
    while current and k <= max_len:
        candidates = set()
        for a, b in combinations(current, 2):
            union = tuple(sorted(set(a) | set(b)))
            if len(union) == k and all(sub in freq for sub in combinations(union, k - 1)):
                candidates.add(union)
        nxt = []
        for cand in candidates:
            s = matrix[:, list(cand)].all(axis=1).mean()
            if s >= min_support:
                freq[cand] = float(s)
                nxt.append(cand)
        current = nxt
        k += 1
    return freq


def _own_rules(onehot, min_support, min_confidence, max_len):
    cols = list(onehot.columns)
    freq = _own_apriori(onehot, min_support, max_len)
    rows = []
    for itemset, sup in freq.items():
        if len(itemset) < 2:
            continue
        for c in itemset:
            ant = tuple(i for i in itemset if i != c)
            conf = sup / freq[ant]
            lift = conf / freq[(c,)]
            if conf >= min_confidence:
                rows.append({
                    "antecedents": [cols[i] for i in ant],
                    "consequents": [cols[c]],
                    "support": sup,
                    "confidence": conf,
                    "lift": lift,
                })
    return pd.DataFrame(rows)


def _mlxtend_rules(onehot, min_support, min_confidence, max_len):
    from mlxtend.frequent_patterns import apriori, association_rules

    itemsets = apriori(onehot, min_support=min_support, use_colnames=True, max_len=max_len)
    try:
        rules = association_rules(itemsets, num_itemsets=len(onehot),
                                  metric="confidence", min_threshold=min_confidence)
    except TypeError:  # older mlxtend releases have no num_itemsets argument
        rules = association_rules(itemsets, metric="confidence", min_threshold=min_confidence)
    rules = rules[rules["consequents"].apply(len) == 1]
    return pd.DataFrame({
        "antecedents": rules["antecedents"].apply(sorted),
        "consequents": rules["consequents"].apply(sorted),
        "support": rules["support"],
        "confidence": rules["confidence"],
        "lift": rules["lift"],
    }).reset_index(drop=True)


def mine_rules(onehot: pd.DataFrame, min_support=0.05, min_confidence=0.6, max_len=3):
    """Mine association rules with mlxtend when available, else a built-in Apriori.

    Returns (rules_dataframe, engine_name).
    """
    try:
        return _mlxtend_rules(onehot, min_support, min_confidence, max_len), "mlxtend"
    except Exception:  # mlxtend missing or API mismatch -> same algorithm, built in
        return _own_rules(onehot, min_support, min_confidence, max_len), "built-in apriori"
