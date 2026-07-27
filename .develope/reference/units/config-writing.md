> **Legacy frozen survey:** This file is version-bound historical evidence. Read .develope/reference/README.md and provenance.json; do not treat it as current DCS truth.

# Ground / ship / static unit config writing

## Ground vehicle group (mission shape)

```json
{
  "name": "Ground-1",
  "groupId": 10,
  "x": -205000,
  "y": -454000,
  "task": "Ground Nothing",
  "tasks": {},
  "units": [
    {
      "type": "T-72B",
      "unitId": 100,
      "name": "Ground-1-1",
      "x": -205000,
      "y": -454000,
      "heading": 1.57,
      "skill": "Average"
    }
  ]
}
```

Rules:

1. `type` must be a vehicle type id from [`vehicles.md`](./vehicles.md) / `data/vehicles.json`.
2. Coordinates are theatre map meters (`x` north, `y` east).
3. `heading` is radians in mission files (0 ≈ north; confirm with pydcs writers).
4. Country must own / be allowed the unit (see pydcs `countries.py` inventories).

## Ship group

```json
{
  "name": "Naval-1",
  "groupId": 20,
  "x": 0,
  "y": 0,
  "units": [
    {
      "type": "VINSON",
      "unitId": 200,
      "name": "CVN-1",
      "x": 0,
      "y": 0,
      "heading": 0,
      "skill": "Excellent"
    }
  ]
}
```

Carriers expose parking for aircraft via ship type `plane_num` / `helicopter_num` /
`parking` fields in [`ships.md`](./ships.md).

## Static object

```json
{
  "name": "Static-1",
  "type": ".Command Center",
  "unitId": 300,
  "x": -210000,
  "y": -460000,
  "heading": 0,
  "category": "Fortifications"
}
```

Static type ids often include leading dots or spaces (e.g. `.Command Center`).
Copy ids exactly from [`statics.md`](./statics.md).

## Categories (pydcs vehicles)

Artillery, Infantry, AirDefence, Fortification, Unarmed, Armor, MissilesSS,
Locomotive, Carriage.

AirDefence threat ranges in `vehicles.json` help place SAM threats realistically.
