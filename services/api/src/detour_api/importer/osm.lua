-- osm2pgsql flex style for the region import (Phase 2). Replaces the spike S2 style.
--
-- This file only collects candidates and builds geometries; it decides nothing. The selection rule
-- (ADR 003 and ADR 011) is applied in Python (detour_api/importer/selection.py), where it is
-- tested and where excluded objects are counted. Keep the candidate test below in step with the
-- osmium tags-filter expression in pipeline.py.
--
-- Output (schema "staging"):
--   osm_object   every candidate with the tags the importer reads and a geometry
--   osm_boundary administrative boundaries of level 4 and 6 (destination "areas")

local object_table = osm2pgsql.define_table({
    name = 'osm_object',
    schema = 'staging',
    ids = { type = 'any', id_column = 'osm_id', type_column = 'osm_type' },
    columns = {
        { column = 'tags', type = 'jsonb', not_null = true },
        { column = 'geom', type = 'geometry', projection = 4326 },
    },
})

local boundary_table = osm2pgsql.define_table({
    name = 'osm_boundary',
    schema = 'staging',
    ids = { type = 'relation', id_column = 'osm_id' },
    columns = {
        { column = 'tags', type = 'jsonb', not_null = true },
        { column = 'geom', type = 'multipolygon', projection = 4326, not_null = true },
    },
})

-- Tags copied out. opening_hours is deliberately absent: it is out of scope (ADR 003).
local KEYS = {
    ['name'] = true, ['int_name'] = true, ['amenity'] = true, ['tourism'] = true,
    ['historic'] = true, ['memorial'] = true, ['memorial:type'] = true, ['cuisine'] = true,
    ['wikidata'] = true, ['wikipedia'] = true, ['heritage'] = true, ['website'] = true,
    ['contact:website'] = true, ['ISO3166-2'] = true, ['admin_level'] = true,
    ['boundary'] = true,
    -- Names for the multilingual name resolver (ADR 025).
    ['official_name'] = true, ['short_name'] = true, ['alt_name'] = true, ['old_name'] = true,
    ['brand'] = true, ['brand:wikidata'] = true,
}
local PREFIXES = { 'name:', 'diet:', 'addr:', 'official_name:', 'short_name:', 'brand:' }

local function keep_tags(tags)
    local out = {}
    for k, v in pairs(tags) do
        if KEYS[k] then
            out[k] = v
        else
            for _, prefix in ipairs(PREFIXES) do
                if k:sub(1, #prefix) == prefix then
                    out[k] = v
                    break
                end
            end
        end
    end
    return out
end

local TOURISM = {
    attraction = true, museum = true, gallery = true, viewpoint = true,
    zoo = true, theme_park = true, aquarium = true,
}
local FOOD = { restaurant = true, cafe = true }

local function is_candidate(tags)
    if tags.amenity and FOOD[tags.amenity] then return true end
    if tags.tourism and TOURISM[tags.tourism] then return true end
    if tags.historic then return true end
    return false
end

function osm2pgsql.process_node(object)
    if not is_candidate(object.tags) then return end
    object_table:insert({ tags = keep_tags(object.tags), geom = object:as_point() })
end

function osm2pgsql.process_way(object)
    if not is_candidate(object.tags) then return end
    local geom
    if object.is_closed then
        geom = object:as_polygon()
    else
        geom = object:as_linestring()
    end
    object_table:insert({ tags = keep_tags(object.tags), geom = geom })
end

function osm2pgsql.process_relation(object)
    local t = object.tags.type
    if t ~= 'multipolygon' and t ~= 'boundary' then return end

    if object.tags.boundary == 'administrative'
        and (object.tags.admin_level == '4' or object.tags.admin_level == '6')
        and object.tags.name then
        local geom = object:as_multipolygon()
        if geom ~= nil and not geom:is_null() then
            boundary_table:insert({ tags = keep_tags(object.tags), geom = geom })
        end
    end

    if t == 'multipolygon' and is_candidate(object.tags) then
        local geom = object:as_multipolygon()
        if geom == nil or geom:is_null() then
            object_table:insert({ tags = keep_tags(object.tags) })
        else
            object_table:insert({ tags = keep_tags(object.tags), geom = geom })
        end
    end
end
