-- Spike S2 (throwaway): osm2pgsql flex import of the objects Detour cares about.
-- The class lists below must match the osmium filter in run.sh.

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
        return 'attraction', 'historic:' .. tags.historic
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
    local cls, sub = classify(object.tags)
    if cls then
        insert_with(object, object:as_point(), cls, sub)
    end
end

function osm2pgsql.process_way(object)
    local cls, sub = classify(object.tags)
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
    local cls, sub = classify(object.tags)
    if cls then
        insert_with(object, object:as_multipolygon():centroid(), cls, sub)
    end
end
