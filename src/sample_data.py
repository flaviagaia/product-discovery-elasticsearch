from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd


PRODUCTS = [
    ("SKU-1001", "Sony Noise Cancelling Headphones", "Wireless over-ear headphones with adaptive noise cancelling and premium sound.", "sony", "audio", 349.0, 4.8, 0.91, 0.82, 1),
    ("SKU-1002", "Bose Quiet Wireless Headphones", "Bluetooth headphones with immersive sound and all-day comfort.", "bose", "audio", 329.0, 4.7, 0.89, 0.76, 1),
    ("SKU-1003", "Logitech MX Keys Keyboard", "Wireless keyboard for office productivity and multi-device pairing.", "logitech", "computer_accessories", 119.0, 4.9, 0.88, 0.73, 1),
    ("SKU-1004", "Razer Gaming Mechanical Keyboard", "RGB mechanical keyboard for gaming setups with tactile switches.", "razer", "computer_accessories", 169.0, 4.6, 0.84, 0.81, 1),
    ("SKU-1005", "Apple Watch SE", "Smartwatch with fitness tracking, GPS and health monitoring.", "apple", "wearables", 249.0, 4.8, 0.95, 0.64, 1),
    ("SKU-1006", "Garmin Forerunner 255", "Running watch with GPS, advanced training metrics and recovery insights.", "garmin", "wearables", 299.0, 4.7, 0.86, 0.77, 1),
    ("SKU-1007", "Dyson Cordless Vacuum", "Cordless vacuum cleaner with strong suction and lightweight design.", "dyson", "home_appliances", 399.0, 4.7, 0.83, 0.58, 0),
    ("SKU-1008", "Shark Cordless Vacuum", "Vacuum cleaner with auto-empty docking system and floor detection.", "shark", "home_appliances", 379.0, 4.5, 0.81, 0.72, 1),
]

SEARCH_SCENARIOS = [
    ("S-1001", "sony head", "autocomplete", "", "", "SKU-1001"),
    ("S-1002", "wireless keyboard", "filtered_search", "computer_accessories", "", "SKU-1003"),
    ("S-1003", "running gps watch", "hybrid_search", "wearables", "", "SKU-1006"),
    ("S-1004", "cordless vacuum", "filtered_search", "home_appliances", "350:450", "SKU-1007"),
]


INDEX_SETTINGS = {
    "settings": {
        "analysis": {
            "tokenizer": {
                "autocomplete_tokenizer": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 20,
                    "token_chars": ["letter", "digit"]
                }
            },
            "analyzer": {
                "product_text_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"]
                },
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "autocomplete_tokenizer",
                    "filter": ["lowercase", "asciifolding"]
                }
            },
            "normalizer": {
                "lowercase_normalizer": {
                    "type": "custom",
                    "filter": ["lowercase", "asciifolding"]
                }
            }
        }
    }
}


INDEX_MAPPINGS = {
    "mappings": {
        "properties": {
            "sku": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "product_text_analyzer",
                "fields": {
                    "autocomplete": {"type": "text", "analyzer": "autocomplete_analyzer", "search_analyzer": "product_text_analyzer"},
                    "raw": {"type": "keyword", "ignore_above": 256}
                }
            },
            "description": {"type": "text", "analyzer": "product_text_analyzer"},
            "brand": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "category": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "price": {"type": "scaled_float", "scaling_factor": 100},
            "rating": {"type": "float"},
            "popularity_score": {"type": "float"},
            "inventory_score": {"type": "float"},
            "is_promoted": {"type": "boolean"},
            "embedding": {"type": "dense_vector", "dims": 5, "similarity": "cosine"}
        }
    }
}


QUERY_EXAMPLES = {
    "autocomplete": {
        "description": "Prefix-oriented discovery query.",
        "example": {
            "multi_match": {
                "query": "sony head",
                "fields": ["title.autocomplete^3", "title^2", "brand^2"]
            }
        }
    },
    "filtered_search": {
        "description": "Lexical query with category and price filters.",
        "example": {
            "bool": {
                "must": [{"match": {"title": "wireless keyboard"}}],
                "filter": [{"term": {"category": "computer_accessories"}}]
            }
        }
    },
    "hybrid_search": {
        "description": "Lexical plus vector search using dense_vector and RRF-style fusion.",
        "example": {
            "retrievers": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": {"match": {"title": "running gps watch"}}}},
                        {"knn": {"field": "embedding", "k": 10, "num_candidates": 25}}
                    ]
                }
            }
        }
    }
}


def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", suffix=".csv", delete=False, dir=path.parent, encoding="utf-8") as tmp_file:
        temp_path = Path(tmp_file.name)
    try:
        df.to_csv(temp_path, index=False)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", suffix=".json", delete=False, dir=path.parent, encoding="utf-8") as tmp_file:
        temp_path = Path(tmp_file.name)
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def ensure_dataset(base_dir: str | Path) -> dict[str, str]:
    base_path = Path(base_dir)

    products_path = base_path / "data" / "raw" / "product_catalog.csv"
    scenarios_path = base_path / "data" / "raw" / "search_scenarios.csv"
    settings_path = base_path / "index_configs" / "products_index_settings.json"
    mappings_path = base_path / "index_configs" / "products_index_mappings.json"
    queries_path = base_path / "search_examples" / "query_examples.json"

    products_df = pd.DataFrame(
        PRODUCTS,
        columns=[
            "sku",
            "title",
            "description",
            "brand",
            "category",
            "price",
            "rating",
            "popularity_score",
            "inventory_score",
            "is_promoted",
        ],
    )
    scenarios_df = pd.DataFrame(
        SEARCH_SCENARIOS,
        columns=["scenario_id", "query_text", "search_mode", "category_filter", "price_range", "expected_sku"],
    )

    _atomic_write_csv(products_df, products_path)
    _atomic_write_csv(scenarios_df, scenarios_path)
    _atomic_write_json(INDEX_SETTINGS, settings_path)
    _atomic_write_json(INDEX_MAPPINGS, mappings_path)
    _atomic_write_json(QUERY_EXAMPLES, queries_path)

    return {
        "products_path": str(products_path),
        "scenarios_path": str(scenarios_path),
        "settings_path": str(settings_path),
        "mappings_path": str(mappings_path),
        "queries_path": str(queries_path),
    }
