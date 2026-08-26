-- Generated from this product resource by DCSMizzer runtime-prepare.
-- Runs only from an isolated Saved Games profile's Scripts/Hooks directory.
-- Uses the supported Sim callback surface; never enables or calls dostring_in.

local lfs = require("lfs")
local log = require("log")

local RUN_ID = @@RUN_ID@@
local MODE = @@MODE@@
local EXPECTED_VERSION = @@EXPECTED_VERSION@@
local EXPECTED_MISSION_NAME = @@EXPECTED_MISSION_NAME@@
local EXPECTED_THEATRE = @@EXPECTED_THEATRE@@
local SMOKE_SECONDS = @@SMOKE_SECONDS@@
local EXPECTED_GROUPS = @@EXPECTED_GROUPS@@
local EXPECTED_UNITS = @@EXPECTED_UNITS@@
local EXPECTED_PLAYER_SLOTS = @@EXPECTED_PLAYER_SLOTS@@
local COORDINATE_CHECKS = {
@@COORDINATE_CHECKS@@
}

local SUBSYSTEM = "DCSMIZZER_RUNTIME"
local result_directory = lfs.writedir() .. "DCSMizzer/"
local result_path = result_directory .. "runtime-result.json"
local temporary_result_path = result_directory .. "runtime-result.json.tmp"
local finished = false

local function json_string(value)
    local result = { '"' }
    for index = 1, #value do
        local byte = string.byte(value, index)
        if byte == 34 then
            result[#result + 1] = '\\"'
        elseif byte == 92 then
            result[#result + 1] = '\\\\'
        elseif byte == 8 then
            result[#result + 1] = '\\b'
        elseif byte == 9 then
            result[#result + 1] = '\\t'
        elseif byte == 10 then
            result[#result + 1] = '\\n'
        elseif byte == 12 then
            result[#result + 1] = '\\f'
        elseif byte == 13 then
            result[#result + 1] = '\\r'
        elseif byte < 32 then
            result[#result + 1] = string.format('\\u%04x', byte)
        else
            result[#result + 1] = string.char(byte)
        end
    end
    result[#result + 1] = '"'
    return table.concat(result)
end

local function json_number(value)
    if type(value) ~= "number" or value ~= value
       or value == math.huge or value == -math.huge then
        error("runtime result contains a non-finite number")
    end
    return string.format("%.17g", value)
end

local function json_array(values)
    return { __dcsmizzer_array = true, values = values }
end

local function encode_json(value, state, depth)
    state.nodes = state.nodes + 1
    if state.nodes > 50000 then
        error("runtime result exceeds the node limit")
    end
    if depth > 32 then
        error("runtime result exceeds the depth limit")
    end
    local kind = type(value)
    if kind == "nil" then
        return "null"
    elseif kind == "boolean" then
        return tostring(value)
    elseif kind == "number" then
        return json_number(value)
    elseif kind == "string" then
        return json_string(value)
    elseif kind ~= "table" then
        error("runtime result contains an unsupported value type")
    end
    if state.active[value] then
        error("runtime result contains a cycle")
    end
    state.active[value] = true
    local rendered
    if value.__dcsmizzer_array == true then
        local parts = {}
        for index, item in ipairs(value.values) do
            parts[index] = encode_json(item, state, depth + 1)
        end
        rendered = "[" .. table.concat(parts, ",") .. "]"
    else
        local keys = {}
        for key in pairs(value) do
            if type(key) ~= "string" then
                error("runtime result object contains a non-string key")
            end
            keys[#keys + 1] = key
        end
        table.sort(keys)
        local parts = {}
        for index, key in ipairs(keys) do
            parts[index] = json_string(key) .. ":"
                .. encode_json(value[key], state, depth + 1)
        end
        rendered = "{" .. table.concat(parts, ",") .. "}"
    end
    state.active[value] = nil
    return rendered
end

local function utc_now()
    return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

local function runtime_version()
    local ok, value = pcall(function()
        return Export.LoGetVersionInfo()
    end)
    if not ok or type(value) ~= "table"
       or type(value.ProductVersion) ~= "table" then
        return nil
    end
    local parts = {}
    for index = 1, 4 do
        local component = value.ProductVersion[index]
        if type(component) ~= "number" then
            return nil
        end
        parts[index] = tostring(component)
    end
    return table.concat(parts, ".")
end

local function write_result(value)
    lfs.mkdir(result_directory)
    local payload = encode_json(value, { nodes = 0, active = {} }, 0)
    if #payload > 2097152 then
        error("runtime result exceeds the byte limit")
    end
    local handle, open_error = io.open(temporary_result_path, "wb")
    if not handle then
        error("cannot open the bounded runtime result: " .. tostring(open_error))
    end
    -- DCS currently writes the bytes but returns nil from file:write in this
    -- hook environment.  Treat an actual Lua error as failure instead of
    -- assuming the stock Lua return convention is preserved.
    local write_ok, write_error = pcall(function()
        handle:write(payload .. "\n")
        handle:flush()
    end)
    local close_ok, close_error = pcall(function()
        handle:close()
    end)
    if not write_ok then
        error("cannot write the bounded runtime result: " .. tostring(write_error))
    end
    if not close_ok then
        error("cannot close the bounded runtime result: " .. tostring(close_error))
    end
    os.remove(result_path)
    local renamed, rename_error = os.rename(temporary_result_path, result_path)
    if not renamed then
        error("cannot publish the bounded runtime result: " .. tostring(rename_error))
    end
end

local function base_result(status)
    return {
        schema = "dcsmizzer.runtime-result/v1",
        run_id = RUN_ID,
        mode = MODE,
        status = status,
        created_utc = utc_now(),
        dcs = {
            expected_product_version = EXPECTED_VERSION,
            runtime_product_version = runtime_version(),
            runtime_identity_attested = true,
        },
    }
end

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

local function safe_exit()
    local ok, failure = pcall(function()
        Sim.exitProcess()
    end)
    if not ok then
        log.write(SUBSYSTEM, log.ERROR,
            "Sim.exitProcess failed: " .. tostring(failure))
    end
end

local function run_registry_probe()
    local result = base_result("error")
    local ok, failure = pcall(function()
        local me_db = require("me_db_api")
        if not me_db.isInitialized() then
            me_db.create()
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
            for _, unit in pairs(aircraft or {}) do
                if unit.HumanCockpit then
                    flyable_aircraft = flyable_aircraft + 1
                end
                task_capability_edges = task_capability_edges
                    + count_pairs(unit.Tasks)
                if type(unit.Pylons) == "table" then
                    aircraft_with_pylons = aircraft_with_pylons + 1
                    for _, pylon in pairs(unit.Pylons) do
                        pylon_stations = pylon_stations + 1
                        for _, launcher in pairs(pylon.Launchers or {}) do
                            pylon_launcher_edges = pylon_launcher_edges + 1
                            if type(launcher.CLSID) == "string" then
                                launcher_clsids[launcher.CLSID] = true
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
        result.status = "ok"
        result.registry = {
            initialized = true,
            aggregate_only = true,
            counts = counts,
        }
    end)
    if not ok then
        result.failure = {
            class = "registry_probe_failed",
            error_type = type(failure),
            message = string.sub(tostring(failure), 1, 512),
        }
    end
    write_result(result)
    log.write(SUBSYSTEM, result.status == "ok" and log.INFO or log.ERROR,
        "registry probe status=" .. result.status .. " run_id=" .. RUN_ID)
end

local events = {}
local simulation_started_real_time = nil

local function add_event(name)
    events[#events + 1] = { name = name, utc = utc_now() }
end

local function count_mission_entities(mission)
    local groups = 0
    local units = 0
    local coalition = mission and mission.coalition or {}
    for _, side in pairs(coalition or {}) do
        for _, country in pairs((side and side.country) or {}) do
            for _, category_name in ipairs({
                "plane", "helicopter", "vehicle", "ship", "static"
            }) do
                local category = country[category_name]
                for _, group in pairs((category and category.group) or {}) do
                    groups = groups + 1
                    units = units + count_pairs(group.units)
                end
            end
        end
    end
    return groups, units
end

local function path_name(value)
    if type(value) ~= "string" then
        return nil
    end
    return string.match(value, "([^/\\]+)$") or value
end

local function coordinate_results()
    local results = {}
    for index, item in ipairs(COORDINATE_CHECKS) do
        local record = {
            label = item.label,
            latitude = item.latitude,
            longitude = item.longitude,
            expected_x = item.expected_x,
            expected_y = item.expected_y,
            tolerance_m = item.tolerance_m,
            passed = false,
        }
        local ok, point = pcall(function()
            return Export.LoGeoCoordinatesToLoCoordinates(
                item.longitude, item.latitude
            )
        end)
        if ok and type(point) == "table"
           and type(point.x) == "number" and type(point.z) == "number" then
            record.runtime_x = point.x
            record.runtime_y = point.z
            record.error_m = math.sqrt(
                (point.x - item.expected_x) ^ 2
                + (point.z - item.expected_y) ^ 2
            )
            record.passed = record.error_m <= item.tolerance_m
        else
            record.failure = string.sub(tostring(point), 1, 256)
        end
        results[index] = record
    end
    return results
end

local function finish_mission_smoke()
    if finished then
        return
    end
    finished = true
    add_event("smoke_interval_complete")
    local result = base_result("ok")
    local mission = Sim.getCurrentMission()
    local groups, units = count_mission_entities(mission)
    local mission_name = Sim.getMissionName()
    local mission_filename = Sim.getMissionFilename()
    local available_coalitions = Sim.getAvailableCoalitions() or {}
    local slot_count = 0
    for coalition_id in pairs(available_coalitions) do
        slot_count = slot_count + count_pairs(
            Sim.getAvailableSlots(coalition_id) or {}
        )
    end
    local elapsed = Sim.getRealTime() - simulation_started_real_time
    local checks = coordinate_results()
    local coordinate_checks_passed = true
    for _, check in ipairs(checks) do
        if not check.passed then
            coordinate_checks_passed = false
        end
    end
    result.events = json_array(events)
    result.mission = {
        expected_name = EXPECTED_MISSION_NAME,
        runtime_name = mission_name,
        runtime_filename = mission_filename,
        runtime_filename_name = path_name(mission_filename),
        expected_theatre = EXPECTED_THEATRE,
        expected_groups = EXPECTED_GROUPS,
        expected_units = EXPECTED_UNITS,
        expected_player_slots = EXPECTED_PLAYER_SLOTS,
        runtime_theatre = mission and mission.theatre or nil,
        groups = groups,
        units = units,
        available_slots = slot_count,
        result_blue = Sim.getMissionResult("blue"),
        result_red = Sim.getMissionResult("red"),
    }
    result.smoke = {
        required_seconds = SMOKE_SECONDS,
        observed_seconds = elapsed,
        interval_completed = elapsed >= SMOKE_SECONDS,
    }
    result.coordinate_checks = json_array(checks)
    result.coordinate_checks_passed = coordinate_checks_passed
    if result.mission.runtime_theatre ~= EXPECTED_THEATRE
       or result.mission.runtime_filename_name ~= EXPECTED_MISSION_NAME
       or result.mission.groups ~= EXPECTED_GROUPS
       or result.mission.units ~= EXPECTED_UNITS
       or (EXPECTED_PLAYER_SLOTS > 0 and result.mission.available_slots < 1)
       or not result.smoke.interval_completed
       or not coordinate_checks_passed then
        result.status = "failed"
    end
    write_result(result)
    log.write(SUBSYSTEM, result.status == "ok" and log.INFO or log.ERROR,
        "mission smoke status=" .. result.status .. " run_id=" .. RUN_ID)
    safe_exit()
end

local callbacks = {}
function callbacks.onMissionLoadBegin()
    add_event("mission_load_begin")
end
function callbacks.onMissionLoadEnd()
    add_event("mission_load_end")
end
function callbacks.onSimulationStart()
    add_event("simulation_start")
    simulation_started_real_time = Sim.getRealTime()
end
function callbacks.onSimulationStop()
    add_event("simulation_stop")
end
function callbacks.onSimulationFrame()
    if simulation_started_real_time ~= nil and not finished
       and Sim.getRealTime() - simulation_started_real_time >= SMOKE_SECONDS then
        local ok, failure = pcall(finish_mission_smoke)
        if not ok then
            local result = base_result("error")
            result.events = json_array(events)
            result.failure = {
                class = "mission_smoke_hook_failed",
                error_type = type(failure),
                message = string.sub(tostring(failure), 1, 512),
            }
            local result_ok, result_failure = pcall(write_result, result)
            log.write(SUBSYSTEM, log.ERROR,
                "mission smoke hook failed run_id=" .. RUN_ID
                .. " error=" .. tostring(failure)
                .. (result_ok and "" or
                    " result_error=" .. tostring(result_failure)))
            safe_exit()
        end
    end
end

local registry_exit_callbacks = {}
function registry_exit_callbacks.onSimulationFrame()
    safe_exit()
end

if MODE == "registry-probe" then
    local ok, failure = pcall(run_registry_probe)
    if not ok then
        log.write(SUBSYSTEM, log.ERROR,
            "registry hook failed before result: " .. tostring(failure))
        safe_exit()
    else
        -- exitProcess is not reliably acted upon while hooks themselves are
        -- still loading.  Ask from the first supported simulation callback.
        Sim.setUserCallbacks(registry_exit_callbacks)
    end
elseif MODE == "mission-smoke" then
    Sim.setUserCallbacks(callbacks)
    log.write(SUBSYSTEM, log.INFO,
        "mission smoke hook armed run_id=" .. RUN_ID)
else
    log.write(SUBSYSTEM, log.ERROR, "unsupported runtime mode")
    safe_exit()
end
