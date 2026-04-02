from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.sample_data import ensure_dataset


def _normalize(values: np.ndarray) -> np.ndarray:
    values = values.astype("float32")
    minimum = float(values.min())
    maximum = float(values.max())
    if maximum - minimum < 1e-8:
        return np.zeros_like(values, dtype="float32")
    return (values - minimum) / (maximum - minimum)


def _prefix_score(query_text: str, titles: pd.Series, brands: pd.Series) -> np.ndarray:
    query_tokens = query_text.lower().split()
    scores = []
    for title, brand in zip(titles.str.lower(), brands.str.lower()):
        combined = f"{brand} {title}"
        match_count = sum(1 for token in query_tokens if combined.startswith(token) or token in combined[: len(token) + 8])
        scores.append(float(match_count))
    return np.array(scores, dtype="float32")


def _apply_filters(products: pd.DataFrame, category_filter: str, price_range: str) -> pd.Series:
    mask = pd.Series([True] * len(products))
    if category_filter:
        mask &= products["category"] == category_filter
    if price_range:
        lower, upper = price_range.split(":")
        mask &= products["price"].between(float(lower), float(upper))
    return mask


def run_pipeline(base_dir: str | Path) -> dict:
    base_path = Path(base_dir)
    dataset = ensure_dataset(base_path)
    products = pd.read_csv(dataset["products_path"])
    scenarios = pd.read_csv(dataset["scenarios_path"]).fillna("")

    corpus = (products["title"] + " " + products["description"] + " " + products["brand"] + " " + products["category"]).tolist()
    vectorizer = TfidfVectorizer(ngram_range=(1, 2))
    lexical_matrix = vectorizer.fit_transform(corpus)
    semantic_projection = TruncatedSVD(n_components=5, random_state=42)
    dense_matrix = semantic_projection.fit_transform(lexical_matrix)

    scenario_results = []
    success_flags = []

    for _, scenario in scenarios.iterrows():
        query_text = scenario["query_text"]
        query_vector = vectorizer.transform([query_text])
        lexical_scores = cosine_similarity(query_vector, lexical_matrix).reshape(-1)
        semantic_query = semantic_projection.transform(query_vector)
        semantic_scores = cosine_similarity(semantic_query, dense_matrix).reshape(-1)
        autocomplete_scores = _prefix_score(query_text, products["title"], products["brand"])

        lexical_component = _normalize(lexical_scores)
        semantic_component = _normalize(semantic_scores)
        autocomplete_component = _normalize(autocomplete_scores)
        popularity_component = _normalize(products["popularity_score"].to_numpy(dtype="float32"))
        inventory_component = _normalize(products["inventory_score"].to_numpy(dtype="float32"))
        promoted_component = products["is_promoted"].to_numpy(dtype="float32")

        if scenario["search_mode"] == "autocomplete":
            final_scores = (
                0.55 * autocomplete_component
                + 0.25 * lexical_component
                + 0.15 * popularity_component
                + 0.05 * promoted_component
            )
        elif scenario["search_mode"] == "filtered_search":
            final_scores = (
                0.55 * lexical_component
                + 0.20 * popularity_component
                + 0.15 * inventory_component
                + 0.10 * promoted_component
            )
        else:
            final_scores = (
                0.40 * lexical_component
                + 0.30 * semantic_component
                + 0.20 * popularity_component
                + 0.10 * inventory_component
            )

        filter_mask = _apply_filters(products, scenario["category_filter"], scenario["price_range"])
        masked_scores = np.where(filter_mask.to_numpy(), final_scores, -1.0)
        ranked = products.copy()
        ranked["final_score"] = np.round(masked_scores, 4)
        ranked = ranked.sort_values(by="final_score", ascending=False).reset_index(drop=True)

        top_sku = ranked.loc[0, "sku"]
        is_success = top_sku == scenario["expected_sku"]
        success_flags.append(is_success)

        scenario_results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "query_text": query_text,
                "search_mode": scenario["search_mode"],
                "expected_sku": scenario["expected_sku"],
                "top_sku": top_sku,
                "top_score": float(ranked.loc[0, "final_score"]),
                "category_filter": scenario["category_filter"],
                "price_range": scenario["price_range"],
            }
        )

    result_df = pd.DataFrame(scenario_results)
    success_rate = float(np.mean(success_flags))

    processed_dir = base_path / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    results_path = processed_dir / "product_discovery_results.csv"
    report_path = processed_dir / "product_discovery_report.json"

    result_df.to_csv(results_path, index=False)

    summary = {
        "dataset_source": "product_discovery_elasticsearch_sample",
        "product_count": int(len(products)),
        "scenario_count": int(len(scenarios)),
        "success_rate_at_1": round(success_rate, 4),
        "results_artifact": str(results_path),
        "report_artifact": str(report_path),
        "settings_artifact": dataset["settings_path"],
        "mappings_artifact": dataset["mappings_path"],
        "query_examples_artifact": dataset["queries_path"],
    }
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
