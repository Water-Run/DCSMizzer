-- Development-only DCS runtime registry aggregate probe.
--
-- Deploy only into an isolated Saved Games profile's Scripts/Hooks directory.
-- It invokes the same me_db_api.create() path used by Mission Editor, emits
-- aggregate counts to dcs.log, and does not copy unit or weapon definitions.

local log = require("log")

local function count_pairs(value)
    local count = 0
    if type(value) ~= "table" then
        return count
    end
    for _ in pairs(value) do
        count = count + 1
    end
    return count
end

local function emit(status, fields)
    local parts = {"REGISTRY", "status=" .. status}
    if fields then
        local names = {}
        for name in pairs(fields) do
            table.insert(names, name)
        end
        table.sort(names)
        for _, name in ipairs(names) do
            table.insert(parts, name .. "=" .. tostring(fields[name]))
        end
    end
    log.write("DCSMIZZER_SURVEY", log.INFO, table.concat(parts, "|"))
end

local ok_require, me_db = pcall(require, "me_db_api")
if not ok_require then
    emit("require_failed", {error_type = type(me_db)})
    return
end

local ok_create, create_error = pcall(function()
    if not me_db.isInitialized() then
        me_db.create()
    end
end)
if not ok_create then
    emit("create_failed", {error_type = type(create_error)})
    return
end

local db = me_db.db
local counts = {
    countries = count_pairs(db.Countries),
    unit_types = count_pairs(me_db.unit_by_type),
    weapons_by_clsid = count_pairs(me_db.weapon_by_CLSID),
    task_definitions = count_pairs(db.Units.Planes.Tasks),
}

local categories = {
    planes = db.Units.Planes.Plane,
    helicopters = db.Units.Helicopters.Helicopter,
    ships = db.Units.Ships.Ship,
    cars = db.Units.Cars.Car,
    ground_objects = db.Units.GroundObjects.GroundObject,
    fortifications = db.Units.Fortifications.Fortification,
    heliports = db.Units.Heliports.Heliport,
    grass_airfields = db.Units.GrassAirfields.GrassAirfield,
    warehouses = db.Units.Warehouses.Warehouse,
    cargos = db.Units.Cargos.Cargo,
    effects = db.Units.Effects.Effect,
    lta_vehicles = db.Units.LTAvehicles.LTAvehicle,
    animals = db.Units.Animals.Animal,
    personnel = db.Units.Personnel.Personnel,
    ad_equipments = db.Units.ADEquipments.ADEquipment,
    wwii_structures = db.Units.WWIIstructures.WWIIstructure,
}
for name, values in pairs(categories) do
    counts[name] = count_pairs(values)
end

local launcher_clsids = {}
local pylon_stations = 0
local pylon_launcher_edges = 0
local aircraft_with_pylons = 0
local task_capability_edges = 0
local flyable_aircraft = 0

local function inspect_aircraft(aircraft)
    for _, unit in pairs(aircraft) do
        if unit.HumanCockpit then
            flyable_aircraft = flyable_aircraft + 1
        end
        if type(unit.Tasks) == "table" then
            task_capability_edges =
                task_capability_edges + count_pairs(unit.Tasks)
        end
        if type(unit.Pylons) == "table" then
            aircraft_with_pylons = aircraft_with_pylons + 1
            for _, pylon in pairs(unit.Pylons) do
                pylon_stations = pylon_stations + 1
                if type(pylon.Launchers) == "table" then
                    for _, launcher in pairs(pylon.Launchers) do
                        pylon_launcher_edges = pylon_launcher_edges + 1
                        if type(launcher.CLSID) == "string" then
                            launcher_clsids[launcher.CLSID] = true
                        end
                    end
                end
            end
        end
    end
end

inspect_aircraft(db.Units.Planes.Plane)
inspect_aircraft(db.Units.Helicopters.Helicopter)

local unknown_launcher_clsids = 0
for clsid in pairs(launcher_clsids) do
    if me_db.weapon_by_CLSID[clsid] == nil then
        unknown_launcher_clsids = unknown_launcher_clsids + 1
    end
end

counts.aircraft_with_pylons = aircraft_with_pylons
counts.flyable_aircraft = flyable_aircraft
counts.pylon_stations = pylon_stations
counts.pylon_launcher_edges = pylon_launcher_edges
counts.unique_launcher_clsids = count_pairs(launcher_clsids)
counts.unknown_launcher_clsids = unknown_launcher_clsids
counts.task_capability_edges = task_capability_edges

emit("ok", counts)
