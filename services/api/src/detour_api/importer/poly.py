"""Parser for Geofabrik ``.poly`` files (the clip polygon of an extract) -> WKT MultiPolygon."""


def poly_to_wkt(text: str) -> str:
    """Convert the osmosis polygon filter format to a WKT MULTIPOLYGON.

    Sections whose name starts with ``!`` are holes of the preceding outer ring.
    """
    lines = [line.strip() for line in text.splitlines()]
    sections: list[tuple[bool, list[tuple[float, float]]]] = []
    current: list[tuple[float, float]] | None = None
    hole = False
    for line in lines[1:]:  # the first line is the file's name
        if not line:
            continue
        if line == "END":
            if current is None:
                # The final END closes the file
                break
            sections.append((hole, current))
            current = None
        elif current is None:
            hole = line.startswith("!")
            current = []
        else:
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"bad coordinate line in poly file: {line!r}")
            current.append((float(parts[0]), float(parts[1])))

    polygons: list[list[list[tuple[float, float]]]] = []
    for is_hole, ring in sections:
        if len(ring) < 4:
            raise ValueError("a ring in the poly file has fewer than four points")
        if ring[0] != ring[-1]:
            ring = [*ring, ring[0]]
        if is_hole:
            if not polygons:
                raise ValueError("a hole in the poly file precedes any outer ring")
            polygons[-1].append(ring)
        else:
            polygons.append([ring])
    if not polygons:
        raise ValueError("the poly file contains no polygon")

    def ring_wkt(ring: list[tuple[float, float]]) -> str:
        return "(" + ", ".join(f"{x!r} {y!r}" for x, y in ring) + ")"

    return (
        "MULTIPOLYGON("
        + ", ".join("(" + ", ".join(ring_wkt(r) for r in rings) + ")" for rings in polygons)
        + ")"
    )
