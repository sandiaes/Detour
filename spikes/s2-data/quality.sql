-- Data quality per class (attraction / restaurant). Counts only; no value is invented.
SELECT
    class,
    count(*) AS total,
    count(*) FILTER (WHERE name IS NOT NULL) AS with_name,
    count(*) FILTER (WHERE name_en IS NOT NULL) AS with_name_en,
    count(*) FILTER (WHERE name_latin IS NOT NULL) AS with_name_latin,
    count(*) FILTER (WHERE name IS NOT NULL AND name !~ '[A-Za-z]') AS name_without_latin_letters,
    count(*) FILTER (WHERE cuisine IS NOT NULL) AS with_cuisine,
    count(*) FILTER (WHERE wikidata IS NOT NULL) AS with_wikidata,
    count(*) FILTER (WHERE website IS NOT NULL) AS with_website
FROM poi
GROUP BY class
ORDER BY class;
