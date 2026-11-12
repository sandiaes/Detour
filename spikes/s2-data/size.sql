-- Size of the imported data. Indexes are included in total_bytes.
-- This is a spike schema, not the final geo schema, so treat it as an estimate.
SELECT
    (SELECT count(*) FROM poi) AS rows,
    pg_relation_size('poi') AS table_bytes,
    pg_indexes_size('poi') AS index_bytes,
    pg_total_relation_size('poi') AS total_bytes,
    pg_database_size(current_database()) AS database_bytes;
