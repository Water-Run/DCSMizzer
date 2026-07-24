# dcs-mission-maker — extract

Source: `dcs-mission-maker`

## Purpose

TypeScript library for constructing `.miz` ZIP contents with **Zod validation** and
`js-2-lua` serialization. Exposes `ME_DB` cherry-picked ME database facts.

## Mission stubs (waypoint templates)

Under `mission-stubs/coalition/country/plane/group/`:

| file | type | action |
|------|------|--------|
| takeoff-from-runway | TakeOff | From Runway |
| takeoff-from-parking-hot | TakeOffParkingHot | From Parking Area Hot |
| takeoff-from-ramp | TakeOffParking | From Parking Area |
| turning-point | Turning Point | Turning Point |
| fly-over-point | Turning Point | Fly Over Point |
| landing-autopark / landing-fixed-park | Land | Landing |

See also [`../mission/waypoints.md`](../mission/waypoints.md).

## ME_DB

- Planes indexed: **99** type strings  
  ([`../data/mission-maker-me-db-planes.json`](../data/mission-maker-me-db-planes.json))
- Callnames: **134**  
  ([`../data/mission-maker-callnames.json`](../data/mission-maker-callnames.json))

Sample plane keys: `A-10A`, `A-10C`, `A-10C II`, `A-20G`, `A-50`, `AV-8B N/A`, `An-26B`, `An-30M`, `B-17G`, `B-1B`, `B-52H`, `Bf 109 K-4`…

## Coordinate schema comments

From `files/mission.ts`: **x → north**, **z → east** in some schema descriptions;
mission unit fields still commonly use `x`/`y` with y=east. Align with
[`../terrain/coordinates.md`](../terrain/coordinates.md).

## Agent takeaway

Use for **schema discipline** and waypoint stubs; use pydcs for full unit/weapon fidelity.
