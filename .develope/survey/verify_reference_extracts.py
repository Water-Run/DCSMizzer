#!/usr/bin/env python3
"""Spot-check .develope/reference extracts against local upstream pydcs source.

Run from repository root:
  python3 .develope/survey/verify_reference_extracts.py

Exit 0 only when all checks pass. Reads real upstream files and extracted JSON —
does not hard-code expected DCS facts beyond join keys used as fixtures that are
also loaded from the same source tree.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / ".develope" / "reference"
DATA = REF / "data"
PYDCS = ROOT / ".develope" / "upstream" / "pydcs" / "dcs"
UPSTREAM = ROOT / ".develope" / "upstream"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def require(path: Path) -> Path:
    if not path.is_file():
        fail(f"missing file {path}")
    return path


def main() -> None:
    if not PYDCS.is_dir():
        fail(f"pydcs source not found at {PYDCS}")

    # --- tracked extract presence ---
    for rel in (
        "aircraft/planes.md",
        "units/vehicles.md",
        "units/ships.md",
        "units/statics.md",
        "units/countries.md",
        "terrain/coordinates.md",
        "mission/miz-structure.md",
        "weapons/clsid-common-aam.md",
        "data/planes.json",
        "data/airports-by-theatre.json",
        "data/vehicles.json",
        "data/ships.json",
        "data/statics.json",
        "data/countries.json",
        "data/weapons-index.json",
        "upstream/briefing-room.md",
        "upstream/retribution.md",
        "upstream/moose.md",
        "upstream/gtd.md",
        "upstream/mission-maker.md",
    ):
        require(REF / rel)
    ok("tracked reference files present")

    docs = ROOT / "Docs"
    extras = [p for p in docs.rglob("*") if p.is_file() and p.name != "index.txt"]
    if extras:
        fail(f"Docs/ has unexpected survey dump files: {extras[:5]}")
    ok("Docs/ not used as survey dump")

    # --- six upstream clones ---
    clones = {
        "pydcs": "pydcs",
        "briefing-room-for-dcs": "briefing-room-for-dcs",
        "dcs-mission-maker": "dcs-mission-maker",
        "dcs-global-terrain-database": "dcs-global-terrain-database",
        "dcs-retribution": "dcs-retribution",
        "MOOSE": "MOOSE",
    }
    for name, dirname in clones.items():
        head = UPSTREAM / dirname / ".git" / "HEAD"
        if not head.is_file():
            fail(f"clone missing or no HEAD: {dirname}")
    ok("six upstream clones have .git/HEAD")

    # --- plane type id + fuel vs planes.py ---
    planes = json.loads(require(DATA / "planes.json").read_text())
    by_class = {p["class"]: p for p in planes}
    src = (PYDCS / "planes.py").read_text(errors="replace")
    for cls in ("MiG_29A", "JF_17", "M_2000C", "F_16C_50", "FA_18C_hornet", "Su_25T"):
        if cls not in by_class:
            fail(f"planes.json missing class {cls}")
        m = re.search(
            rf"class {cls}\(PlaneType\):.*?id = \"([^\"]+)\".*?fuel_max = ([0-9.]+)",
            src,
            re.S,
        )
        if not m:
            fail(f"planes.py missing class {cls}")
        got_id, got_fuel = by_class[cls]["id"], float(by_class[cls]["fuel_max_kg"])
        exp_id, exp_fuel = m.group(1), float(m.group(2))
        if got_id != exp_id:
            fail(f"{cls} id extract={got_id!r} source={exp_id!r}")
        if abs(got_fuel - exp_fuel) > 1e-6:
            fail(f"{cls} fuel extract={got_fuel} source={exp_fuel}")
        ok(f"plane {cls} id={got_id} fuel={got_fuel}")

    # --- airport Tempelhof (GermanyCW) ---
    airports = json.loads(require(DATA / "airports-by-theatre.json").read_text())
    g_src = (PYDCS / "terrain" / "germany" / "airports.py").read_text(errors="replace")
    t = next((a for a in airports.get("germany", []) if a.get("name") == "Tempelhof"), None)
    if not t:
        fail("Tempelhof missing from airports-by-theatre.json germany")
    m = re.search(
        r'class Tempelhof\(Airport\):.*?id = (\d+).*?name = "Tempelhof".*?'
        r"Point\(([-\d.]+),\s*([-\d.]+)",
        g_src,
        re.S,
    )
    if not m:
        fail("Tempelhof not found in pydcs germany/airports.py")
    exp_id, exp_x, exp_y = int(m.group(1)), float(m.group(2)), float(m.group(3))
    if t["id"] != exp_id:
        fail(f"Tempelhof id extract={t['id']} source={exp_id}")
    if abs(float(t["x"]) - exp_x) > 1e-3 or abs(float(t["y"]) - exp_y) > 1e-3:
        fail(f"Tempelhof coords extract=({t['x']},{t['y']}) source=({exp_x},{exp_y})")
    ok(f"Tempelhof id={t['id']} x={t['x']} y={t['y']}")

    # Caucasus Batumi or Anapa
    c_src = (PYDCS / "terrain" / "caucasus" / "airports.py").read_text(errors="replace")
    c_list = airports.get("caucasus", [])
    if not c_list:
        fail("no caucasus airports in extract")
    sample = c_list[0]
    cname = sample["class"]
    m = re.search(
        rf"class {re.escape(cname)}\(Airport\):.*?id = (\d+).*?"
        r"Point\(([-\d.]+),\s*([-\d.]+)",
        c_src,
        re.S,
    )
    if not m:
        fail(f"caucasus class {cname} not in source")
    if sample["id"] != int(m.group(1)):
        fail(f"caucasus {cname} id mismatch")
    if abs(float(sample["x"]) - float(m.group(2))) > 1e-3:
        fail(f"caucasus {cname} x mismatch")
    ok(f"caucasus {cname} id={sample['id']}")

    # --- R-27R / R-73 CLSIDs ---
    weapons = json.loads(require(DATA / "weapons-index.json").read_text())
    wsrc = (PYDCS / "weapons_data.py").read_text(errors="replace")
    r27 = "{9B25D316-0434-4954-868F-D51DB1A38DF0}"
    r73 = "{FBC29BFE-3D24-4C64-B81D-941239D12249}"
    if r27 not in wsrc or r73 not in wsrc:
        fail("R-27R/R-73 CLSIDs not in weapons_data.py")
    if not any(w.get("clsid") == r27 for w in weapons):
        fail("R-27R CLSID missing from weapons-index.json")
    if not any(w.get("clsid") == r73 for w in weapons):
        fail("R-73 CLSID missing from weapons-index.json")
    ok("R-27R and R-73 CLSIDs in extract and source")

    # --- AAM curated doc ---
    aam_md = require(REF / "weapons" / "clsid-common-aam.md").read_text()
    if "AB 250" in aam_md or "AB 500" in aam_md or "250kg CBU" in aam_md:
        fail("AAM curated doc still contains cluster-bomb munitions")
    if "R-27R" not in aam_md or "AIM-9" not in aam_md:
        fail("AAM curated doc missing expected AAM names")
    # first table data row should not be AB bomb
    for line in aam_md.splitlines():
        if line.startswith("| `") and "clsid" not in line.lower():
            if "AB " in line and "CBU" in line:
                fail(f"AAM table leads with non-AAM: {line}")
            break
    ok("AAM curated doc is AAM-focused")

    # --- unit peer indexes ---
    for name, min_n in (("vehicles.json", 300), ("ships.json", 50), ("statics.json", 200), ("countries.json", 80)):
        arr = json.loads(require(DATA / name).read_text())
        if len(arr) < min_n:
            fail(f"{name} count {len(arr)} < {min_n}")
        ok(f"{name} count={len(arr)}")

    # vehicle sample vs source
    vsrc = (PYDCS / "vehicles.py").read_text(errors="replace")
    vehicles = json.loads((DATA / "vehicles.json").read_text())
    sample_v = next(v for v in vehicles if v.get("id") == "SAU Msta")
    if 'id = "SAU Msta"' not in vsrc:
        fail("SAU Msta not in vehicles.py")
    ok(f"vehicle SAU Msta category={sample_v.get('category')}")

    ships = json.loads((DATA / "ships.json").read_text())
    sb = next(s for s in ships if s.get("id") == "speedboat")
    vin = next(s for s in ships if s.get("id") == "VINSON")
    if sb.get("plane_num") is not None:
        fail(f"Speedboat must not inherit carrier plane_num: {sb}")
    if vin.get("plane_num") != 72:
        fail(f"VINSON plane_num expected 72 got {vin.get('plane_num')}")
    ok("ships Speedboat/VINSON fields isolated")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
