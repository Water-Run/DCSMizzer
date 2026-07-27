"""Versioned DCS terrain product and mission-theatre identity catalog."""

from __future__ import annotations

from typing import Any


_SURVEY_BASIS = "2026-07-30"
_DCS_VERSION_BASIS = "2.9.28.26385"
_STEAM_BUILD_BASIS = "24431605"

_PRODUCTS: tuple[dict[str, str], ...] = (
    {
        "name": "Marianas WWII",
        "slug": "marianas_wwii_terrain",
        "mission_theatre": "MarianaIslandsWWII",
        "relationship": "canonical",
    },
    {
        "name": "Cold War Germany",
        "slug": "cold_war_germany_terrain",
        "mission_theatre": "GermanyCW",
        "relationship": "canonical",
    },
    {
        "name": "Afghanistan",
        "slug": "afghanistan_terrain",
        "mission_theatre": "Afghanistan",
        "relationship": "canonical",
    },
    {
        "name": "East Afghanistan",
        "slug": "east_afghanistan_terrain",
        "mission_theatre": "Afghanistan",
        "relationship": "regional_entitlement",
    },
    {
        "name": "Iraq",
        "slug": "iraq_terrain",
        "mission_theatre": "Iraq",
        "relationship": "canonical",
    },
    {
        "name": "Iraq North",
        "slug": "iraq_north_terrain",
        "mission_theatre": "Iraq",
        "relationship": "regional_entitlement",
    },
    {
        "name": "Kola",
        "slug": "kola_terrain",
        "mission_theatre": "Kola",
        "relationship": "canonical",
    },
    {
        "name": "Southwest Afghanistan",
        "slug": "southwest_afghanistan_terrain",
        "mission_theatre": "Afghanistan",
        "relationship": "regional_entitlement",
    },
    {
        "name": "Sinai",
        "slug": "sinai_terrain",
        "mission_theatre": "SinaiMap",
        "relationship": "canonical",
    },
    {
        "name": "Normandy 2.0",
        "slug": "normandy_2.0_terrain",
        "mission_theatre": "Normandy",
        "relationship": "canonical",
    },
    {
        "name": "Caucasus",
        "slug": "caucasus_terrain",
        "mission_theatre": "Caucasus",
        "relationship": "canonical",
    },
    {
        "name": "South Atlantic",
        "slug": "south_atlantic_terrain",
        "mission_theatre": "Falklands",
        "relationship": "canonical",
    },
    {
        "name": "Marianas",
        "slug": "marianas_terrain",
        "mission_theatre": "MarianaIslands",
        "relationship": "canonical",
    },
    {
        "name": "Syria",
        "slug": "syria_terrain",
        "mission_theatre": "Syria",
        "relationship": "canonical",
    },
    {
        "name": "The Channel",
        "slug": "the_channel_terrain",
        "mission_theatre": "TheChannel",
        "relationship": "canonical",
    },
    {
        "name": "Persian Gulf",
        "slug": "persiangulf_terrain",
        "mission_theatre": "PersianGulf",
        "relationship": "canonical",
    },
    {
        "name": "Normandy 1944",
        "slug": "normandy_terrain",
        "mission_theatre": "Normandy",
        "relationship": "legacy_product",
    },
    {
        "name": "Nevada Test and Training Range",
        "slug": "nttr_terrain",
        "mission_theatre": "Nevada",
        "relationship": "canonical",
    },
)

_DISPLAY_NAMES = {
    "Afghanistan": "Afghanistan",
    "Caucasus": "Caucasus",
    "Falklands": "South Atlantic",
    "GermanyCW": "Cold War Germany",
    "Iraq": "Iraq",
    "Kola": "Kola",
    "MarianaIslands": "Marianas",
    "MarianaIslandsWWII": "Marianas WWII",
    "Nevada": "Nevada Test and Training Range",
    "Normandy": "Normandy 2.0",
    "PersianGulf": "Persian Gulf",
    "SinaiMap": "Sinai",
    "Syria": "Syria",
    "TheChannel": "The Channel",
}

_ANNOUNCED_REGIONS = (
    {
        "name": "North Afghanistan",
        "mission_theatre": "Afghanistan",
        "status_at_survey": "in_development_not_current_product_card",
        "source": "https://www.digitalcombatsimulator.com/en/news/2026-05-16/",
    },
    {
        "name": "Iraq South",
        "mission_theatre": "Iraq",
        "status_at_survey": "in_development_not_current_product_card",
        "source": "https://www.digitalcombatsimulator.com/en/news/2026-05-16/",
    },
)


def terrain_catalog_report(
    *,
    terrain: str | None = None,
    product: str | None = None,
    search: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return a bounded snapshot that never equates products with worlds."""

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    if terrain is not None and product is not None:
        raise ValueError("terrain and product filters are mutually exclusive")
    if (terrain is not None or product is not None) and search is not None:
        raise ValueError("exact filters and search are mutually exclusive")

    selected_products = list(_PRODUCTS)
    exact_requested = terrain is not None or product is not None
    if terrain is not None:
        folded = terrain.casefold()
        selected_products = [
            item
            for item in _PRODUCTS
            if folded
            in {
                item["mission_theatre"].casefold(),
                _DISPLAY_NAMES[item["mission_theatre"]].casefold(),
            }
        ]
    elif product is not None:
        folded = product.casefold()
        selected_products = [
            item
            for item in _PRODUCTS
            if folded in {item["name"].casefold(), item["slug"].casefold()}
        ]

    grouped: dict[str, list[dict[str, str]]] = {}
    for item in selected_products:
        grouped.setdefault(item["mission_theatre"], []).append(item)
    records = [
        {
            "mission_theatre": mission_theatre,
            "display_name": _DISPLAY_NAMES[mission_theatre],
            "products": [
                {
                    **item,
                    "official_url": (
                        "https://www.digitalcombatsimulator.com/en/products/"
                        f"terrains/{item['slug']}/"
                    ),
                }
                for item in sorted(
                    products,
                    key=lambda product_record: (
                        product_record["relationship"] != "canonical",
                        product_record["name"].casefold(),
                    ),
                )
            ],
        }
        for mission_theatre, products in sorted(grouped.items())
    ]
    if search is not None:
        folded = search.casefold()
        records = [
            record
            for record in records
            if folded in record["mission_theatre"].casefold()
            or folded in record["display_name"].casefold()
            or any(
                folded in product_record["name"].casefold()
                or folded in product_record["slug"].casefold()
                for product_record in record["products"]
            )
        ]
    matching = len(records)
    returned = records[:limit]

    unique_theatres = {item["mission_theatre"] for item in _PRODUCTS}
    return {
        "schema": "dcsmizzer.terrain-catalog/v1",
        "authority": (
            "dated_official_product_catalog_snapshot_plus_locally_verified_"
            "mission_theatre_identities"
        ),
        "survey_basis": _SURVEY_BASIS,
        "dcs_identity_evidence": {
            "product_version": _DCS_VERSION_BASIS,
            "steam_build_id": _STEAM_BUILD_BASIS,
            "method": (
                "parsed official installed MIZ mission.theatre values and "
                "literal Mission Editor generator constants"
            ),
        },
        "dcs_started": False,
        "filters": {
            "terrain": terrain,
            "product": product,
            "search": search,
            "limit": limit,
        },
        "coverage": {
            "official_product_cards": len(_PRODUCTS),
            "unique_mission_theatres": len(unique_theatres),
            "regional_entitlement_cards": sum(
                item["relationship"] == "regional_entitlement"
                for item in _PRODUCTS
            ),
            "legacy_product_cards": sum(
                item["relationship"] == "legacy_product" for item in _PRODUCTS
            ),
            "matching_theatres": matching,
            "returned_theatres": len(returned),
            "output_truncated": len(returned) < matching,
            "exact_query_usable": (
                len(returned) == 1 and matching == 1 if exact_requested else None
            ),
        },
        "theatres": returned,
        "announced_regions": list(_ANNOUNCED_REGIONS),
        "sources": [
            {
                "kind": "official_product_catalog",
                "url": (
                    "https://www.digitalcombatsimulator.com/en/products/"
                    "terrains/?SHOWALL_1=1"
                ),
                "accessed": _SURVEY_BASIS,
            },
            {
                "kind": "official_region_status",
                "url": (
                    "https://www.digitalcombatsimulator.com/en/news/2026-05-16/"
                ),
                "accessed": _SURVEY_BASIS,
            },
        ],
        "limitations": [
            "Product cards, regional entitlements, and unique mission worlds "
            "are separate counts; regional products do not create a new "
            "mission.theatre identifier.",
            "This is a dated survey snapshot, not a live web query. Recheck "
            "official sources when current product availability matters.",
            "A catalogued theatre identity proves no terrain height, surface, "
            "road, scenery-object, airport-footprint, placement, ownership, "
            "or runtime compatibility.",
            "No DCS, Mission Editor, or upstream code was executed.",
        ],
    }
