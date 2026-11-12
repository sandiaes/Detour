-- Most common subclasses, to see what the data is made of.
SELECT class, subclass, count(*) AS total
FROM poi
GROUP BY class, subclass
ORDER BY total DESC, class, subclass
LIMIT 40;
