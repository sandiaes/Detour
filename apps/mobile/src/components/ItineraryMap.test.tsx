import type { Day } from "@detour/shared";
import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { __mock as maplibre } from "../testing/maplibreMock";
import { makeItinerary, makeLeg } from "../testing/fixtures";
import { MAP_CONFIG } from "../testing/harness";
import { ItineraryMap } from "./ItineraryMap";

const itinerary = makeItinerary("essentials");
const [day1, day2] = itinerary.days as [Day, Day];

beforeEach(() => {
  jest.useFakeTimers();
  maplibre.reset();
});
afterEach(() => jest.useRealTimers());

function manyStops(count: number): Day {
  const items = Array.from({ length: count }, (_, i) => ({
    ...day1.items[0]!,
    id: `m${i}`,
    position: i + 1,
    display_name: `Stop name ${i + 1}`,
    lat: 48.2 + i * 0.001,
    lon: 16.37 + i * 0.001,
    transfer:
      i < count - 1
        ? {
            to_item_id: `m${i + 1}`,
            mode: "walk" as const,
            seconds: 300,
            meters: 400,
            confidence: "estimated" as const,
          }
        : null,
  }));
  return { ...day1, id: "many", items };
}

const props = { map: MAP_CONFIG, onShowList: () => {}, selectedId: null, onSelect: () => {} };
const markers = () => screen.queryAllByTestId(/^marker-/);

test("gives the map the style URL that the backend sent", async () => {
  await render(<ItineraryMap day={day1} {...props} />);
  expect(maplibre.map?.mapStyle).toBe("https://tiles.example.org/styles/test");
});

test("attribution for OpenStreetMap and the tile provider is visible on the map", async () => {
  await render(<ItineraryMap day={day1} {...props} />);
  expect(screen.getByText("Data from OpenStreetMap")).toBeOnTheScreen();
  expect(screen.getByText("OpenFreeMap")).toBeOnTheScreen();
});

test("each stop is a numbered marker with a spoken label", async () => {
  await render(<ItineraryMap day={day1} {...props} />);
  expect(markers()).toHaveLength(5); // three sights and two meals
  expect(screen.getByLabelText("Stop 1, Attraction: Schönbrunn Palace")).toBeOnTheScreen();
  expect(screen.getByLabelText("Stop 3, Restaurant: Gasthaus Zum Test")).toBeOnTheScreen();
  expect(screen.getByLabelText("Stop 4, Attraction: St. Stephen's Cathedral")).toBeOnTheScreen();
  expect(screen.getByText("2")).toBeOnTheScreen();
});

test("markers load progressively, a batch at a time, with a visible count", async () => {
  await render(<ItineraryMap day={manyStops(15)} {...props} />);
  expect(markers()).toHaveLength(6);
  expect(screen.getByText("Placing stops 6 of 15…")).toBeOnTheScreen();
  await act(async () => {
    jest.advanceTimersByTime(60);
  });
  expect(markers()).toHaveLength(12);
  await act(async () => {
    jest.advanceTimersByTime(60);
  });
  expect(markers()).toHaveLength(15);
  expect(screen.queryByText(/Placing stops/)).toBeNull();
});

test("transfer lines are drawn solid when routed and dashed when estimated, and say so", async () => {
  await render(<ItineraryMap day={day1} {...props} />);
  const lines = maplibre.sources.transfers as {
    features: { properties: { confidence: string } }[];
  };
  expect(lines.features.map((f) => f.properties.confidence)).toEqual([
    "estimated",
    "routed",
    "estimated",
    "estimated",
  ]);
  const routed = maplibre.layers.find((l) => l.id === "transfers-routed");
  const estimated = maplibre.layers.find((l) => l.id === "transfers-estimated");
  expect(routed?.style.lineDasharray).toBeUndefined();
  expect(estimated?.style.lineDasharray).toEqual([2, 2]);
  expect(routed?.filter).toEqual(["==", ["get", "confidence"], "routed"]);
  // The map key names each marker and says the line is direct and dashed when estimated.
  await fireEvent.press(screen.getByRole("button", { name: "Map key" }));
  expect(screen.getByText("Attraction")).toBeOnTheScreen();
  expect(screen.getByText("Restaurant or café")).toBeOnTheScreen();
  expect(screen.getByText("Travel to a new base city, or transport you entered")).toBeOnTheScreen();
  expect(screen.getByText(/dashed if estimated/)).toBeOnTheScreen();
});

test("a line appears only once both of its stops are on the map", async () => {
  await render(<ItineraryMap day={manyStops(15)} {...props} />);
  const count = () => (maplibre.sources.transfers as { features: unknown[] }).features.length;
  expect(count()).toBe(5); // 6 stops placed, 5 lines between them
  await act(async () => {
    jest.advanceTimersByTime(200);
  });
  expect(count()).toBe(14);
});

test("tapping a marker selects its stop; the selected marker is announced as selected", async () => {
  const onSelect = jest.fn();
  const view = await render(<ItineraryMap day={day1} {...props} onSelect={onSelect} />);
  await fireEvent.press(screen.getByTestId(`marker-${day1.items[0]!.id}`));
  expect(onSelect).toHaveBeenCalledWith(day1.items[0]!.id);
  await view.rerender(
    <ItineraryMap day={day1} {...props} selectedId={day1.items[0]!.id} onSelect={onSelect} />,
  );
  expect(
    screen.getByLabelText("Stop 1, Attraction: Schönbrunn Palace").props.accessibilityState,
  ).toEqual({ selected: true });
});

test("a stop chosen elsewhere is brought into view once the map has loaded", async () => {
  const view = await render(<ItineraryMap day={day1} {...props} />);
  await act(async () => {
    maplibre.map?.onDidFinishLoadingMap?.({ nativeEvent: null });
  });
  expect(maplibre.easeTo).not.toHaveBeenCalled();
  await view.rerender(<ItineraryMap day={day1} {...props} selectedId="i3" />);
  expect(maplibre.easeTo).toHaveBeenCalledWith({ center: [16.3731, 48.2085], duration: 350 });
});

test("the arrival at a new base city is a transport marker with its leg", async () => {
  const onSelect = jest.fn();
  await render(<ItineraryMap day={day2} previousDay={day1} {...props} onSelect={onSelect} />);
  const marker = screen.getByLabelText(
    "Transport: drive to Graz from Vienna, 2 h 20 min, estimated",
  );
  expect(marker).toBeOnTheScreen();
  const lines = maplibre.sources.transfers as {
    features: { id: string; geometry: { coordinates: number[][] } }[];
  };
  const leg = lines.features.find((f) => f.id === `arrival-${day2.id}`);
  expect(leg?.geometry.coordinates).toEqual([
    [16.3738, 48.2082],
    [15.4395, 47.0707],
  ]);
  await fireEvent.press(screen.getByTestId(`marker-arrival-${day2.id}`));
  expect(onSelect).toHaveBeenCalledWith(`arrival-${day2.id}`);
});

test("without the base city's position no transport marker is placed", async () => {
  await render(
    <ItineraryMap
      day={{ ...day2, base_city_lat: null, base_city_lon: null }}
      previousDay={day1}
      {...props}
    />,
  );
  expect(screen.queryByLabelText(/^Transport:/)).toBeNull();
});

test("the camera fits the day's stops once the map has loaded, and again for another day", async () => {
  const view = await render(<ItineraryMap day={day1} {...props} />);
  expect(maplibre.fitBounds).not.toHaveBeenCalled();
  await act(async () => {
    maplibre.map?.onDidFinishLoadingMap?.({ nativeEvent: null });
  });
  expect(maplibre.fitBounds).toHaveBeenCalledTimes(1);
  const [bounds] = maplibre.fitBounds.mock.calls[0] as [number[]];
  expect(bounds[0]).toBeCloseTo(16.3122);
  expect(bounds[3]).toBeCloseTo(48.2085);
  await view.rerender(<ItineraryMap day={day2} {...props} />);
  expect(maplibre.fitBounds).toHaveBeenCalledTimes(2);
  expect(screen.getByLabelText("Stop 1, Attraction: Hofburg")).toBeOnTheScreen();
  expect(screen.queryByLabelText("Stop 1, Attraction: Schönbrunn Palace")).toBeNull();
});

test("a map that cannot load says so, offers a retry that remounts it, and the list", async () => {
  const onShowList = jest.fn();
  await render(<ItineraryMap day={day1} {...props} onShowList={onShowList} />);
  expect(screen.getByText("Loading the map…")).toBeOnTheScreen();
  await act(async () => {
    maplibre.map?.onDidFailLoadingMap?.({ nativeEvent: null });
  });
  expect(screen.getByText(/The map could not load/)).toBeOnTheScreen();
  expect(screen.getByText(/The day list still works/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByText("Show the day list"));
  expect(onShowList).toHaveBeenCalled();
  await fireEvent.press(screen.getByText("Try the map again"));
  expect(screen.queryByText(/The map could not load/)).toBeNull();
  expect(screen.getByText("Loading the map…")).toBeOnTheScreen();
});

test("a user gesture on the map collapses the credit to an i button that restores it", async () => {
  await render(<ItineraryMap day={day1} {...props} />);
  await act(async () => {
    maplibre.map?.onRegionWillChange?.({ nativeEvent: { userInteraction: true } });
  });
  expect(screen.queryByText("Data from OpenStreetMap")).toBeNull();
  await fireEvent.press(screen.getByLabelText("Show map attribution"));
  expect(screen.getByText("Data from OpenStreetMap")).toBeOnTheScreen();
});

test("a day with nothing planned still shows a map and says so", async () => {
  await render(<ItineraryMap day={{ ...day1, id: "empty", items: [] }} {...props} />);
  expect(markers()).toHaveLength(0);
  expect(screen.getByText(/Nothing is planned on this day/)).toBeOnTheScreen();
});

test("a transport leg the user entered is a line with its mode at the middle (ADR 032)", async () => {
  const leg = makeLeg({ id: "leg1", day_id: day1.id });
  const day: Day = { ...day1, items: [...day1.items, leg] };
  await render(<ItineraryMap day={day} {...props} />);
  expect(screen.getByTestId("leg-marker-leg1")).toBeOnTheScreen();
  expect(
    screen.getByLabelText(/^Transport you entered\. Train from Rome to Florence/),
  ).toBeTruthy();
  const legs = maplibre.sources.legs as { features: { geometry: { coordinates: unknown } }[] };
  expect(legs.features).toHaveLength(1);
  expect(legs.features[0]!.geometry.coordinates).toEqual([
    [12.5, 41.9],
    [11.25, 43.77],
  ]);
  // The leg has a marker of its own, but it is not a numbered stop.
  expect(screen.getAllByLabelText(/^Stop \d/)).toHaveLength(5);
});

test("a journey leg replaces the computed arrival's marker", async () => {
  const leg = makeLeg({ id: "j0", day_id: day2.id }, { is_journey: true });
  const day: Day = {
    ...day2,
    arrival: { ...day2.arrival!, covered_by_item_id: "j0" },
    items: [leg, ...day2.items],
  };
  await render(<ItineraryMap day={day} previousDay={day1} {...props} />);
  expect(screen.queryByLabelText(/^Transport: drive to Graz/)).toBeNull();
  expect(screen.getByTestId("leg-marker-j0")).toBeOnTheScreen();
});
