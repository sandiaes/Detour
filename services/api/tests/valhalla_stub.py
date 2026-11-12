"""A stand-in for the FOSSGIS Valhalla server. No test reaches the network.

It answers like the documented format (see ``tests/fixtures/valhalla/README.md``) and can be told
to fail in each way the adapter must survive.
"""

import json
from pathlib import Path
from typing import Any

import httpx

from detour_api.travel.types import Coord, distance_m

FIXTURES = Path(__file__).parent / "fixtures" / "valhalla"
ROUTE_FIXTURE = json.loads((FIXTURES / "route-florence-rome-documented.json").read_text())
DATE = "Wed, 11 Nov 2026 12:00:00 GMT"


def coord(lat: float, lon: float) -> Coord:
    return Coord.from_degrees(lat, lon)


def street(n: int) -> list[Coord]:
    """``n`` points 400 m apart along a meridian in Florence (all within one matrix)."""
    return [coord(43.7624 + 0.0036 * i, 11.2298) for i in range(n)]


class ValhallaStub:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.mode = "ok"
        self.algorithm: str | None = "timedistancematrix"
        self.null_targets: set[tuple[float, float]] = set()
        self.zero_targets: set[tuple[float, float]] = set()
        self.route_body: dict[str, Any] = ROUTE_FIXTURE

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.mode == "timeout":
            raise httpx.ConnectTimeout("simulated", request=request)
        if self.mode == "429":
            return httpx.Response(429, headers={"Retry-After": "120"})
        if self.mode == "500":
            return httpx.Response(500, text="boom")
        if self.mode == "error154":
            return httpx.Response(
                400,
                json={
                    "error_code": 154,
                    "error": "Path distance exceeds the max distance limit: 150000 meters",
                },
            )
        if self.mode == "garbage":
            return httpx.Response(200, text="<html>not json</html>")
        if self.mode == "wrong_shape":
            return httpx.Response(200, json={"sources_to_targets": [[{"time": 1}]]})
        body = json.loads(request.content)
        headers = {"Date": DATE}
        if request.url.path == "/route":
            return httpx.Response(200, json=self.route_body, headers=headers)
        assert request.url.path == "/sources_to_targets"
        source = body["sources"][0]
        row = []
        for index, target in enumerate(body["targets"]):
            key = (target["lat"], target["lon"])
            metres = distance_m(
                coord(source["lat"], source["lon"]), coord(target["lat"], target["lon"])
            )
            if key in self.null_targets:
                time_, km = None, None
            elif key in self.zero_targets:
                time_, km = 0, 0.0
            else:
                time_, km = round(metres / 1.2), round(metres * 1.3 / 1000, 3)
            row.append({"distance": km, "time": time_, "from_index": 0, "to_index": index})
        payload: dict[str, Any] = {"sources_to_targets": [row], "units": "kilometers"}
        if self.algorithm:
            payload["algorithm"] = self.algorithm
        return httpx.Response(200, json=payload, headers=headers)


class FakeClock:
    """A monotonic clock that only moves when told to, and a sleep that moves it."""

    def __init__(self) -> None:
        self.t = 1000.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds
