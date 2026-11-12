-- Objects left out by the ADR 003 selection rule, by subclass.
SELECT subclass, count(*) AS total
FROM excluded
GROUP BY subclass
ORDER BY total DESC, subclass;
