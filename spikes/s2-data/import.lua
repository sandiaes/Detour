-- Spike S2 (throwaway): osm2pgsql flex import of the objects Detour cares about.
-- The class lists below must match the osmium filter in run.sh.
-- v2: applies the ADR 003 selection rule and counts what it excludes.

local poi = osm2pgsql.define_table({
    name = 'poi',
    ids = { type = 'any', id_column = 'osm_id', type_column = 'osm_type' },
    columns = {
        { column = 'class', type = 'text', not_null = true },
        { column = 'subclass', type = 'text' },
        { column = 'name', type = 'text' },
        { column = 'name_en', type = 'text' },
        { column = 'name_latin', type = 'text' },
        { column = 'opening_hours', type = 'text' },
        { column = 'cuisine', type = 'text' },
        { column = 'wikidata', type = 'text' },
        { column = 'website', type = 'text' },
        { column = 'geom', type = 'point', projection = 4326, not_null = true },
    },
})

-- Objects the selection rule leaves out, counted in the `excluded` table (no geometry).
local excluded = osm2pgsql.define_table({
    name = 'excluded',
    ids = { type = 'any', id_column = 'osm_id', type_column = 'osm_type' },
    columns = { { column = 'subclass', type = 'text', not_null = true } },
})

local EXCLUDED_HISTORIC = {
    wayside_shrine = true, wayside_cross = true, boundary_stone = true, bomb_crater = true,
}

local ATTRACTION_TOURISM = {
    attraction = true, museum = true, gallery = true, viewpoint = true,
    zoo = true, theme_park = true, aquarium = true,
}
local FOOD = { restaurant = true, cafe = true }

local function classify(tags)
    if tags.amenity and FOOD[tags.amenity] then
        return 'restaurant', tags.amenity
    end
    if tags.tourism and ATTRACTION_TOURISM[tags.tourism] then
        return 'attraction', tags.tourism
    end
    if tags.historic then
        local h = tags.historic
        -- memorials are excluded unless they carry a wikidata tag (ADR 003)
        if EXCLUDED_HISTORIC[h] or (h == 'memorial' and not tags.wikidata) then
            return nil, nil, 'historic:' .. h
        end
        return 'attraction', 'historic:' .. h
    end
    return nil
end

local function make_row(tags, cls, sub)
    return {
        class = cls,
        subclass = sub,
        name = tags.name,
        name_en = tags['name:en'],
        name_latin = tags['name:ja-Latn'] or tags['name:ja_rm'] or tags.int_name,
        opening_hours = tags.opening_hours,
        cuisine = tags.cuisine,
        wikidata = tags.wikidata,
        website = tags.website or tags['contact:website'],
    }
end

local function insert_with(object, geom, cls, sub)
    if geom == nil or geom:is_null() then
        return
    end
    local r = make_row(object.tags, cls, sub)
    r.geom = geom
    poi:insert(r)
end

function osm2pgsql.process_node(object)
    local cls, sub, skipped = classify(object.tags)
    if skipped then
        excluded:insert({ subclass = skipped })
    elseif cls then
        insert_with(object, object:as_point(), cls, sub)
    end
end

function osm2pgsql.process_way(object)
    local cls, sub, skipped = classify(object.tags)
    if skipped then
        excluded:insert({ subclass = skipped })
        return
    end
    if not cls then
        return
    end
    local geom
    if object.is_closed then
        geom = object:as_polygon():centroid()
    else
        geom = object:as_linestring():centroid()
    end
    insert_with(object, geom, cls, sub)
end

function osm2pgsql.process_relation(object)
    if object.tags.type ~= 'multipolygon' then
        return
    end
    local cls, sub, skipped = classify(object.tags)
    if skipped then
        excluded:insert({ subclass = skipped })
    elseif cls then
        insert_with(object, object:as_multipolygon():centroid(), cls, sub)
    end
end
