"""People and their devices (ADR 034, step 1).

A person's id is the id of its first installation. A phone that joins a person brings its own
trips, places and display names along: they move to the person (step 2: trips by owner and
membership, ``app.trip_member``).

Codes are random from a 32-letter alphabet without 0, O, 1 and I, and only a keyed hash
(HMAC-SHA256 with the token secret) is stored, so a copy of the database does not let anyone try
codes offline. A link code is 8 letters (40 bits), works once and for 10 minutes; the request
limits (``abuse.py``) allow a few attempts. The recovery code is 26 letters (130 bits) and works
until it is replaced; using it signs out every other phone of the person.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

from detour_api.errors import ApiError, conflict
from detour_api.repo.trips import MAX_TRIPS_PER_INSTALLATION
from detour_api.repo.user_places import MAX_USER_PLACES

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
LINK_CODE_LENGTH = 8
RECOVERY_CODE_LENGTH = 26
LINK_CODE_MINUTES = 10

INVALID_CODE = "this code is not valid; a code from another phone works once and for 10 minutes"


@dataclass(frozen=True)
class Device:
    person_id: uuid.UUID
    revoked: bool


@dataclass(frozen=True)
class JoinResult:
    person_id: uuid.UUID
    recovered: bool
    moved_trips: int


def new_code(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def format_code(code: str) -> str:
    """``ABCD-EFGH``: groups of four, easier to read out and type."""
    return "-".join(code[i : i + 4] for i in range(0, len(code), 4))


def normalize_code(raw: str) -> str | None:
    """Upper case without spaces and hyphens; None when it cannot be a code of either kind."""
    code = "".join(raw.split()).replace("-", "").upper()
    if len(code) not in (LINK_CODE_LENGTH, RECOVERY_CODE_LENGTH):
        return None
    if any(c not in ALPHABET for c in code):
        return None
    return code


def code_hash(secret: bytes, purpose: str, code: str) -> bytes:
    return hmac.new(secret, f"{purpose}:{code}".encode(), hashlib.sha256).digest()


def resolve_device(conn: Connection, device_id: uuid.UUID) -> Device:
    """The person of a phone; a phone seen for the first time becomes a new person (the trigger of
    migration 0024 gives it a person with its own id)."""
    row = conn.execute(
        text("SELECT person_id, revoked_at FROM app.installation WHERE id = :i"),
        {"i": device_id},
    ).one_or_none()
    if row is None:
        conn.execute(
            text("INSERT INTO app.installation (id) VALUES (:i) ON CONFLICT (id) DO NOTHING"),
            {"i": device_id},
        )
        row = conn.execute(
            text("SELECT person_id, revoked_at FROM app.installation WHERE id = :i"),
            {"i": device_id},
        ).one()
    return Device(person_id=row.person_id, revoked=row.revoked_at is not None)


@dataclass(frozen=True)
class DeviceRow:
    id: uuid.UUID
    added_at: datetime
    joined_at: datetime | None
    last_seen_at: datetime


@dataclass(frozen=True)
class LinkedRow:
    id: uuid.UUID
    display_name: str | None
    linked_at: datetime


@dataclass(frozen=True)
class PersonRow:
    id: uuid.UUID
    display_name: str | None
    recovery_created_at: datetime | None
    devices: list[DeviceRow]
    people: list[LinkedRow]


MAX_LINKS = 5


def get_person(conn: Connection, person_id: uuid.UUID) -> PersonRow:
    person = conn.execute(
        text("SELECT id, display_name, recovery_created_at FROM app.person WHERE id = :p"),
        {"p": person_id},
    ).one()
    devices = conn.execute(
        text(
            """
            SELECT id, created_at, joined_at, last_seen_at FROM app.installation
            WHERE person_id = :p AND revoked_at IS NULL
            ORDER BY coalesce(joined_at, created_at), id
            """
        ),
        {"p": person_id},
    ).all()
    return PersonRow(
        id=person.id,
        display_name=person.display_name,
        people=linked_people(conn, person_id),
        recovery_created_at=person.recovery_created_at,
        devices=[
            DeviceRow(
                id=d.id, added_at=d.created_at, joined_at=d.joined_at, last_seen_at=d.last_seen_at
            )
            for d in devices
        ],
    )


def linked_people(conn: Connection, person_id: uuid.UUID) -> list[LinkedRow]:
    """The people this person may share trips with, by name, then when they were linked."""
    rows = conn.execute(
        text(
            """
            SELECT p.id, p.display_name, l.created_at FROM app.person_link l
            JOIN app.person p ON p.id = CASE WHEN l.person_a = :p THEN l.person_b ELSE l.person_a END
            WHERE :p IN (l.person_a, l.person_b)
            ORDER BY l.created_at, p.id
            """
        ),
        {"p": person_id},
    ).all()
    return [LinkedRow(id=r.id, display_name=r.display_name, linked_at=r.created_at) for r in rows]


def are_linked(conn: Connection, a: uuid.UUID, b: uuid.UUID) -> bool:
    return (
        conn.execute(
            text("SELECT 1 FROM app.person_link WHERE person_a = :a AND person_b = :b"),
            {"a": min(a, b), "b": max(a, b)},
        ).first()
        is not None
    )


def set_display_name(conn: Connection, person_id: uuid.UUID, name: str | None) -> None:
    clean = " ".join((name or "").split())[:40] or None
    conn.execute(
        text("UPDATE app.person SET display_name = :n WHERE id = :p"), {"n": clean, "p": person_id}
    )


_PURPOSE = {"device": "link", "invite": "invite"}


def create_link_code(
    conn: Connection,
    secret: bytes,
    person_id: uuid.UUID,
    device_id: uuid.UUID,
    kind: str = "device",
) -> tuple[str, datetime]:
    """A new one-time code of the kind (``device``: add one of your phones; ``invite``: link
    another person to you); an earlier unused code of the same kind stops working."""
    conn.execute(
        text("DELETE FROM app.link_code WHERE person_id = :p AND kind = :k AND used_at IS NULL"),
        {"p": person_id, "k": kind},
    )
    code = new_code(LINK_CODE_LENGTH)
    expires_at: datetime = conn.execute(
        text(
            """
            INSERT INTO app.link_code (code_hash, person_id, created_by, expires_at, kind)
            VALUES (:h, :p, :d, now() + make_interval(mins => :m), :k)
            RETURNING expires_at
            """
        ),
        {
            "h": code_hash(secret, _PURPOSE[kind], code),
            "p": person_id,
            "d": device_id,
            "m": LINK_CODE_MINUTES,
            "k": kind,
        },
    ).scalar_one()
    return code, expires_at


INVALID_INVITE = "this invite code is not valid; an invite code works once and for 10 minutes"


def link_people(
    conn: Connection, secret: bytes, person_id: uuid.UUID, device_id: uuid.UUID, raw_code: str
) -> uuid.UUID:
    """Link the caller to the person who showed the invite code; returns that person's id."""
    code = normalize_code(raw_code)
    if code is None or len(code) != LINK_CODE_LENGTH:
        raise ApiError(400, "code_invalid", INVALID_INVITE)
    h = code_hash(secret, "invite", code)
    other = conn.execute(
        text(
            """
            SELECT person_id FROM app.link_code
            WHERE code_hash = :h AND kind = 'invite' AND used_at IS NULL AND expires_at > now()
            FOR UPDATE
            """
        ),
        {"h": h},
    ).scalar_one_or_none()
    if other is None:
        raise ApiError(400, "code_invalid", INVALID_INVITE)
    if other == person_id:
        raise conflict("own_invite", "this is your own invite code; type it on the other phone")
    if are_linked(conn, person_id, other):
        raise conflict("already_linked", "you are already linked")
    for who in (person_id, other):
        if len(linked_people(conn, who)) >= MAX_LINKS:
            raise conflict("limit_reached", f"at most {MAX_LINKS} linked people each")
    conn.execute(
        text("INSERT INTO app.person_link (person_a, person_b) VALUES (:a, :b)"),
        {"a": min(person_id, other), "b": max(person_id, other)},
    )
    conn.execute(
        text("UPDATE app.link_code SET used_at = now(), used_by = :d WHERE code_hash = :h"),
        {"d": device_id, "h": h},
    )
    return uuid.UUID(str(other))


def unlink(conn: Connection, person_id: uuid.UUID, other: uuid.UUID) -> None:
    """Remove the link. Trips already shared stay shared (each can leave or stop sharing)."""
    removed = conn.execute(
        text("DELETE FROM app.person_link WHERE person_a = :a AND person_b = :b RETURNING 1"),
        {"a": min(person_id, other), "b": max(person_id, other)},
    ).first()
    if removed is None:
        raise ApiError(404, "not_found", "you are not linked to this person")


def create_recovery_code(
    conn: Connection, secret: bytes, person_id: uuid.UUID
) -> tuple[str, datetime]:
    """A new recovery code; the earlier one stops working."""
    code = new_code(RECOVERY_CODE_LENGTH)
    created_at: datetime = conn.execute(
        text(
            "UPDATE app.person SET recovery_hash = :h, recovery_created_at = now() WHERE id = :p"
            " RETURNING recovery_created_at"
        ),
        {"h": code_hash(secret, "recovery", code), "p": person_id},
    ).scalar_one()
    return code, created_at


_OWNER_COLUMN = {"trip": "owner_person_id", "user_place": "person_id"}


def _count(conn: Connection, table: str, owner: uuid.UUID) -> int:
    column = _OWNER_COLUMN[table]
    count: int = conn.execute(
        text(f"SELECT count(*) FROM app.{table} WHERE {column} = :o"), {"o": owner}
    ).scalar_one()
    return count


def _move_data(conn: Connection, source: uuid.UUID, target: uuid.UUID) -> int:
    """Move the trips, places and name overrides of one person to another. Limits are checked
    first; an override the target already has for the same place wins over the moved one."""
    trips = _count(conn, "trip", source)
    if trips + _count(conn, "trip", target) > MAX_TRIPS_PER_INSTALLATION:
        raise conflict(
            "limit_reached",
            f"together the two would have more than {MAX_TRIPS_PER_INSTALLATION} trips",
        )
    if _count(conn, "user_place", source) + _count(conn, "user_place", target) > MAX_USER_PLACES:
        raise conflict(
            "limit_reached", f"together the two would have more than {MAX_USER_PLACES} places"
        )
    conn.execute(
        text(
            """
            DELETE FROM app.place_name_override s
            USING app.place_name_override t
            WHERE s.person_id = :s AND t.person_id = :t
              AND s.entity_kind = t.entity_kind AND s.entity_ref = t.entity_ref
            """
        ),
        {"s": source, "t": target},
    )
    for statement in (
        "UPDATE app.trip SET owner_person_id = :t WHERE owner_person_id = :s",
        # A trip both are members of keeps one row: the owner's role wins.
        "DELETE FROM app.trip_member x WHERE x.person_id = :t AND EXISTS (SELECT 1 FROM"
        " app.trip_member y WHERE y.trip_id = x.trip_id AND y.person_id = :s AND y.role = 'owner')",
        "DELETE FROM app.trip_member x WHERE x.person_id = :s AND EXISTS (SELECT 1 FROM"
        " app.trip_member y WHERE y.trip_id = x.trip_id AND y.person_id = :t)",
        "UPDATE app.trip_member SET person_id = :t WHERE person_id = :s",
        "UPDATE app.user_place SET person_id = :t WHERE person_id = :s",
        "UPDATE app.place_name_override SET person_id = :t WHERE person_id = :s",
        # The phone's partner links come along (a link to the target itself is dropped).
        "INSERT INTO app.person_link (person_a, person_b)"
        " SELECT least(:t, o.other), greatest(:t, o.other) FROM (SELECT CASE WHEN person_a = :s"
        " THEN person_b ELSE person_a END AS other FROM app.person_link"
        " WHERE :s IN (person_a, person_b)) o WHERE o.other <> :t ON CONFLICT DO NOTHING",
    ):
        conn.execute(text(statement), {"s": source, "t": target})
    return trips


def join(conn: Connection, secret: bytes, device_id: uuid.UUID, raw_code: str) -> JoinResult:
    """Make this phone one of the person the code belongs to.

    A link code is used up. The recovery code is not, but every other phone of the person is
    signed out. A phone whose own person has other phones cannot move (it would leave them behind).
    """
    code = normalize_code(raw_code)
    if code is None:
        raise ApiError(400, "code_invalid", INVALID_CODE)
    recovered = len(code) == RECOVERY_CODE_LENGTH
    if recovered:
        target = conn.execute(
            text("SELECT id FROM app.person WHERE recovery_hash = :h FOR UPDATE"),
            {"h": code_hash(secret, "recovery", code)},
        ).scalar_one_or_none()
    else:
        target = conn.execute(
            text(
                """
                SELECT person_id FROM app.link_code
                WHERE code_hash = :h AND kind = 'device' AND used_at IS NULL
                  AND expires_at > now()
                FOR UPDATE
                """
            ),
            {"h": code_hash(secret, "link", code)},
        ).scalar_one_or_none()
    if target is None:
        raise ApiError(400, "code_invalid", INVALID_CODE)

    current: uuid.UUID = conn.execute(
        text("SELECT person_id FROM app.installation WHERE id = :d FOR UPDATE"), {"d": device_id}
    ).scalar_one()
    moved = 0
    if current != target:
        others = conn.execute(
            text(
                """
                SELECT count(*) FROM app.installation
                WHERE person_id = :c AND id <> :d AND revoked_at IS NULL
                """
            ),
            {"c": current, "d": device_id},
        ).scalar_one()
        if others:
            raise conflict(
                "has_other_devices",
                "this phone is linked to other phones; remove them under Your devices first",
            )
        moved = _move_data(conn, current, target)
        conn.execute(
            text(
                "UPDATE app.installation SET person_id = :t, joined_at = now(), revoked_at = NULL"
                " WHERE id = :d"
            ),
            {"t": target, "d": device_id},
        )
        # The phone's old person has nothing left (its removed phones go with it).
        conn.execute(text("DELETE FROM app.person WHERE id = :c"), {"c": current})

    if recovered:
        conn.execute(
            text(
                """
                UPDATE app.installation SET revoked_at = now()
                WHERE person_id = :t AND id <> :d AND revoked_at IS NULL
                """
            ),
            {"t": target, "d": device_id},
        )
        # A code someone made on a lost phone must not let it back in.
        conn.execute(
            text("DELETE FROM app.link_code WHERE person_id = :t AND used_at IS NULL"),
            {"t": target},
        )
    else:
        conn.execute(
            text("UPDATE app.link_code SET used_at = now(), used_by = :d WHERE code_hash = :h"),
            {"d": device_id, "h": code_hash(secret, "link", code)},
        )
    return JoinResult(person_id=target, recovered=recovered, moved_trips=moved)


def remove_device(
    conn: Connection, person_id: uuid.UUID, device_id: uuid.UUID, target: uuid.UUID
) -> None:
    if target == device_id:
        raise conflict("this_device", "this phone cannot remove itself; use another of your phones")
    removed = conn.execute(
        text(
            """
            UPDATE app.installation SET revoked_at = now()
            WHERE id = :t AND person_id = :p AND revoked_at IS NULL
            RETURNING id
            """
        ),
        {"t": target, "p": person_id},
    ).scalar_one_or_none()
    if removed is None:
        raise ApiError(404, "not_found", "no such phone among yours")
