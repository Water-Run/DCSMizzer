from __future__ import annotations

import unittest

from Tools.dcsmizzer.terrain_catalog import terrain_catalog_report


class TerrainCatalogTests(unittest.TestCase):
    def test_distinguishes_product_cards_from_unique_theatres(self) -> None:
        report = terrain_catalog_report()

        self.assertEqual(report["schema"], "dcsmizzer.terrain-catalog/v1")
        self.assertEqual(report["coverage"]["official_product_cards"], 18)
        self.assertEqual(report["coverage"]["unique_mission_theatres"], 14)
        self.assertEqual(report["coverage"]["regional_entitlement_cards"], 3)
        self.assertEqual(report["coverage"]["legacy_product_cards"], 1)
        self.assertEqual(len(report["theatres"]), 14)
        self.assertEqual(
            {item["mission_theatre"] for item in report["theatres"]},
            {
                "Afghanistan",
                "Caucasus",
                "Falklands",
                "GermanyCW",
                "Iraq",
                "Kola",
                "MarianaIslands",
                "MarianaIslandsWWII",
                "Nevada",
                "Normandy",
                "PersianGulf",
                "SinaiMap",
                "Syria",
                "TheChannel",
            },
        )

    def test_exact_theatre_exposes_regional_products_without_new_id(self) -> None:
        report = terrain_catalog_report(terrain="Afghanistan")

        self.assertTrue(report["coverage"]["exact_query_usable"])
        self.assertEqual(len(report["theatres"]), 1)
        theatre = report["theatres"][0]
        self.assertEqual(theatre["mission_theatre"], "Afghanistan")
        self.assertEqual(
            {product["relationship"] for product in theatre["products"]},
            {"canonical", "regional_entitlement"},
        )
        self.assertEqual(len(theatre["products"]), 3)

    def test_product_filter_resolves_same_world_and_rejects_ambiguity(self) -> None:
        report = terrain_catalog_report(product="Iraq North")

        self.assertTrue(report["coverage"]["exact_query_usable"])
        self.assertEqual(report["theatres"][0]["mission_theatre"], "Iraq")
        self.assertEqual(
            [item["name"] for item in report["theatres"][0]["products"]],
            ["Iraq North"],
        )

        missing = terrain_catalog_report(product="North Afghanistan")
        self.assertFalse(missing["coverage"]["exact_query_usable"])
        self.assertEqual(missing["theatres"], [])

    def test_search_is_bounded_and_reports_future_regions_separately(self) -> None:
        report = terrain_catalog_report(search="a", limit=1)

        self.assertGreater(report["coverage"]["matching_theatres"], 1)
        self.assertEqual(report["coverage"]["returned_theatres"], 1)
        self.assertTrue(report["coverage"]["output_truncated"])
        self.assertEqual(
            {item["name"] for item in report["announced_regions"]},
            {"North Afghanistan", "Iraq South"},
        )

    def test_limit_is_strict(self) -> None:
        for limit in (0, 101, True):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "limit"):
                    terrain_catalog_report(limit=limit)

    def test_catalog_relationship_invariants_are_explicit(self) -> None:
        report = terrain_catalog_report(limit=100)
        products = [
            product
            for theatre in report["theatres"]
            for product in theatre["products"]
        ]

        self.assertEqual(
            len({product["slug"] for product in products}),
            len(products),
        )
        self.assertEqual(
            len({product["official_url"] for product in products}),
            len(products),
        )
        for theatre in report["theatres"]:
            with self.subTest(theatre=theatre["mission_theatre"]):
                canonical = [
                    product
                    for product in theatre["products"]
                    if product["relationship"] == "canonical"
                ]
                self.assertEqual(len(canonical), 1)
                self.assertEqual(
                    {
                        product["mission_theatre"]
                        for product in theatre["products"]
                    },
                    {theatre["mission_theatre"]},
                )


if __name__ == "__main__":
    unittest.main()
