from __future__ import annotations

import unittest
from pathlib import Path

from src.modeling import run_pipeline


class ProductDiscoveryElasticsearchTestCase(unittest.TestCase):
    def test_pipeline_contract(self) -> None:
        result = run_pipeline(Path(__file__).resolve().parents[1])

        self.assertEqual(result["dataset_source"], "product_discovery_elasticsearch_sample")
        self.assertEqual(result["product_count"], 8)
        self.assertEqual(result["scenario_count"], 4)
        self.assertGreaterEqual(result["success_rate_at_1"], 0.75)


if __name__ == "__main__":
    unittest.main()
