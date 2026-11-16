import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { AppContent } from "../App";
import { colors } from "../theme";
import { createFakeClient } from "../testing/fakeClient";
import { Harness } from "../testing/harness";

const LONDON = {
  id: "greater-london",
  name: "Greater London",
  continent: "Europe",
  country_codes: ["GB"],
  state: "not_imported",
  places: 0,
  places_kept: 0,
  bytes: null,
  job: null,
};
const NEW_YORK = {
  id: "new-york",
  name: "New York State",
  continent: "North America",
  country_codes: ["US"],
  state: "not_imported",
  places: 0,
  places_kept: 0,
  bytes: null,
  job: null,
};
const AUSTRIA = {
  id: "austria",
  name: "Austria",
  continent: "Europe",
  country_codes: ["AT"],
  state: "available",
  places: 1200,
  places_kept: 0,
  bytes: 38_400_000,
  job: null,
};

function catalog(over: Record<string, unknown> = {}) {
  return {
    can_manage: true,
    import_enabled: true,
    geo_bytes: 38_000_000,
    geo_limit_bytes: 250_000_000,
    regions: [AUSTRIA, LONDON],
    ...over,
  };
}

async function open(handlers: Record<string, unknown> = {}) {
  const client = createFakeClient({
    "GET /v1/regions/catalog": () => catalog(),
    ...handlers,
  } as never);
  await render(
    <Harness client={client} initial={{ name: "regions" }}>
      <AppContent />
    </Harness>,
  );
  return client;
}

test("the regions are listed with their state and the space used", async () => {
  await open();
  expect(await screen.findByText("Greater London")).toBeOnTheScreen();
  expect(screen.getByText("Not imported")).toBeOnTheScreen();
  expect(screen.getByText("Available · 1,200 places · about 38 MB")).toBeOnTheScreen();
  expect(screen.getByTestId("regions-usage")).toHaveTextContent(
    "Imported data uses 38 MB of the 250 MB allowed.",
  );
});

test("someone who is not the owner can read the list but not import or remove", async () => {
  await open({ "GET /v1/regions/catalog": () => catalog({ can_manage: false }) });
  expect(await screen.findByText(/Only the owner of this server/)).toBeOnTheScreen();
  await fireEvent.press(await screen.findByTestId("region-greater-london"));
  // The row and the sheet both say it.
  expect(await screen.findAllByText("Not imported")).toHaveLength(2);
  expect(screen.queryByTestId("region-import")).toBeNull();
  expect(screen.queryByTestId("region-remove")).toBeNull();
});

test("importing a region asks the server and shows it as under way", async () => {
  const started = jest.fn(() => ({
    id: "j1",
    status: "requested",
    message: null,
    run_url: "https://github.com/o/r/actions/runs/1",
    requested_at: "2027-01-01T10:00:00Z",
    updated_at: "2027-01-01T10:00:00Z",
  }));
  let asked = false;
  const client = await open({
    "POST /v1/regions/{region_id}/import": () => {
      asked = true;
      return started();
    },
    "GET /v1/regions/catalog": () =>
      catalog({
        regions: [
          AUSTRIA,
          asked ? { ...LONDON, job: { ...started(), status: "running" } } : LONDON,
        ],
      }),
  });
  await fireEvent.press(await screen.findByTestId("region-greater-london"));
  await fireEvent.press(await screen.findByTestId("region-import"));
  await waitFor(() => expect(client.count("POST /v1/regions/{region_id}/import")).toBe(1));
  const post = client.calls.find((c) => c.method === "POST");
  expect(post?.body).toEqual({ gazetteer: true });
  expect(await screen.findByText("Importing…")).toBeOnTheScreen();
});

test("a refused import shows the server's reason", async () => {
  await open({
    "POST /v1/regions/{region_id}/import": () => ({
      status: 409,
      body: { code: "import_running", detail: "an import of austria is under way" },
    }),
  });
  await fireEvent.press(await screen.findByTestId("region-greater-london"));
  await fireEvent.press(await screen.findByTestId("region-import"));
  expect(await screen.findByText(/an import of austria is under way/)).toBeOnTheScreen();
  expect(screen.getByTestId("region-import")).toBeOnTheScreen();
});

test("removing a region shows what is kept first, then removes it", async () => {
  const removed = jest.fn(() => ({}));
  const client = await open({
    "GET /v1/regions/{region_id}/removal-preview": () => ({
      region_id: "austria",
      name: "Austria",
      places_total: 1200,
      places_removed: 1190,
      places_kept: 10,
      admin_areas_removed: 3,
      admin_areas_kept: 0,
      trips: [{ id: "t1", title: "Graz weekend", status: "past" }],
      bytes_freed_estimate: 7_000_000,
    }),
    "DELETE /v1/regions/{region_id}": removed,
  });
  await fireEvent.press(await screen.findByTestId("region-austria"));
  await fireEvent.press(await screen.findByTestId("region-remove"));
  expect(await screen.findByText("Remove Austria?")).toBeOnTheScreen();
  expect(screen.getByText(/10 places your trips use stay/)).toBeOnTheScreen();
  expect(screen.getByText(/Graz weekend/)).toBeOnTheScreen();
  expect(removed).not.toHaveBeenCalled(); // asking first
  await fireEvent.press(screen.getByTestId("confirm-region-remove"));
  await waitFor(() => expect(removed).toHaveBeenCalled());
  expect(client.count("GET /v1/regions/catalog")).toBeGreaterThanOrEqual(2);
});

test("a server with no GitHub access says so and cannot import", async () => {
  await open({ "GET /v1/regions/catalog": () => catalog({ import_enabled: false }) });
  expect(await screen.findByText(/no GitHub access set up/)).toBeOnTheScreen();
  await fireEvent.press(await screen.findByTestId("region-greater-london"));
  const button = await screen.findByTestId("region-import");
  expect(button.props.accessibilityState).toMatchObject({ disabled: true });
});

test("Regions is reachable from More", async () => {
  const client = createFakeClient({ "GET /v1/regions/catalog": () => catalog() } as never);
  await render(
    <Harness client={client} initial={{ name: "more" }}>
      <AppContent />
    </Harness>,
  );
  await fireEvent.press(await screen.findByTestId("more-regions"));
  expect(await screen.findByRole("header", { name: "Regions" })).toBeOnTheScreen();
});

test("an import under way has a yellow badge", async () => {
  const running = {
    ...LONDON,
    job: {
      id: "j1",
      status: "running",
      message: null,
      run_url: null,
      requested_at: "2027-01-01T10:00:00Z",
      updated_at: "2027-01-01T10:00:00Z",
    },
  };
  await open({ "GET /v1/regions/catalog": () => catalog({ regions: [AUSTRIA, running] }) });
  const badge = await screen.findByText("Importing");
  const pill = badge.parent;
  expect(pill && StyleSheet.flatten(pill.props.style).backgroundColor).toBe(colors.warning);
});

test("the regions are listed under their continent", async () => {
  await open({
    "GET /v1/regions/catalog": () => catalog({ regions: [AUSTRIA, LONDON, NEW_YORK] }),
  });
  expect(await screen.findByRole("header", { name: "Europe" })).toBeOnTheScreen();
  expect(screen.getByRole("header", { name: "North America" })).toBeOnTheScreen();
  expect(screen.getByText("New York State")).toBeOnTheScreen();
});
