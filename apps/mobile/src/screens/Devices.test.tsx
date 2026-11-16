import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { AppContent } from "../App";
import { codeKind, deviceDetail, deviceTitle, joinedMessage } from "../domain/devices";
import { createFakeClient } from "../testing/fakeClient";
import { Harness } from "../testing/harness";

const THIS = {
  id: "11111111-2222-3333-4444-555555555555",
  added_at: "2026-11-12T10:00:00Z",
  last_seen_at: "2026-11-16T10:00:00Z",
  this_device: true,
};
const OTHER = {
  id: "99999999-2222-3333-4444-555555555555",
  added_at: "2026-11-16T09:00:00Z",
  last_seen_at: "2026-11-16T10:00:00Z",
  this_device: false,
};

function me(over: Record<string, unknown> = {}) {
  return {
    person_id: THIS.id,
    device_id: THIS.id,
    devices: [THIS, OTHER],
    recovery_code_created_at: null,
    ...over,
  };
}

async function open(handlers: Record<string, unknown> = {}, retry = jest.fn()) {
  const client = createFakeClient({ "GET /v1/me": () => me(), ...handlers } as never);
  await render(
    <Harness client={client} initial={{ name: "devices" }} retry={retry}>
      <AppContent />
    </Harness>,
  );
  return client;
}

test("the phones are listed, this one first", async () => {
  await open();
  expect(await screen.findByText("This phone")).toBeOnTheScreen();
  expect(screen.getByText("Phone 2")).toBeOnTheScreen();
  expect(screen.getByText("You have no recovery code yet.")).toBeOnTheScreen();
  // This phone cannot remove itself.
  expect(screen.queryByTestId("device-remove-0")).toBeNull();
});

test("a link code is shown with the time it stops working", async () => {
  const client = await open({
    "POST /v1/me/link-codes": () => ({ code: "K7MQ-R4XT", expires_at: "2026-11-16T10:10:00Z" }),
  });
  await fireEvent.press(await screen.findByTestId("devices-show-code"));
  expect(await screen.findByTestId("link-code")).toHaveTextContent("K7MQ-R4XT");
  expect(screen.getByText(/Works once, until/)).toBeOnTheScreen();
  expect(client.calls.some((c) => c.method === "POST" && c.path === "/v1/me/link-codes")).toBe(
    true,
  );
});

test("another phone can be removed after confirming", async () => {
  const client = await open({ "DELETE /v1/me/devices/{device_id}": () => undefined });
  await fireEvent.press(await screen.findByTestId("device-remove-1"));
  await fireEvent.press(await screen.findByTestId("device-remove-confirm"));
  await waitFor(() =>
    expect(client.calls.find((c) => c.method === "DELETE")?.params).toEqual({
      device_id: OTHER.id,
    }),
  );
});

test("a code from another phone joins this phone and reconnects", async () => {
  const retry = jest.fn();
  const client = await open(
    {
      "POST /v1/installations/join": () => ({
        person: me({ person_id: OTHER.id }),
        recovered: false,
        moved_trips: 2,
      }),
    },
    retry,
  );
  const join = await screen.findByTestId("devices-join");
  expect(join).toBeDisabled(); // nothing typed yet
  await fireEvent.changeText(screen.getByTestId("devices-code-input"), "k7mq r4xt");
  await fireEvent.press(join);
  await fireEvent.press(await screen.findByTestId("devices-join-confirm"));
  expect(
    await screen.findByText(/This phone is now one of yours. The 2 trips that were on this phone/),
  ).toBeOnTheScreen();
  expect(client.calls.find((c) => c.path === "/v1/installations/join")?.body).toEqual({
    code: "k7mq r4xt",
  });
  expect(retry).toHaveBeenCalled();
});

test("a wrong code says why", async () => {
  await open({
    "POST /v1/installations/join": () => ({
      status: 400,
      body: { detail: "x", code: "code_invalid" },
    }),
  });
  await fireEvent.changeText(await screen.findByTestId("devices-code-input"), "ABCD-EFGH");
  await fireEvent.press(screen.getByTestId("devices-join"));
  await fireEvent.press(await screen.findByTestId("devices-join-confirm"));
  expect(await screen.findByText(/That code does not work/)).toBeOnTheScreen();
});

test("the recovery code is shown once; replacing one asks first", async () => {
  await open({
    "GET /v1/me": () => me({ recovery_code_created_at: "2026-11-14T08:00:00Z" }),
    "POST /v1/me/recovery-code": () => ({
      code: "ABCD-EFGH-JKLM-NPQR-STUV-WXYZ-23",
      created_at: "2026-11-16T10:00:00Z",
    }),
  });
  expect(await screen.findByText(/You made a recovery code on/)).toBeOnTheScreen();
  await fireEvent.press(screen.getByTestId("devices-recovery"));
  await fireEvent.press(await screen.findByTestId("devices-recovery-confirm"));
  expect(await screen.findByTestId("recovery-code")).toHaveTextContent(
    "ABCD-EFGH-JKLM-NPQR-STUV-WXYZ-23",
  );
});

test("helpers", () => {
  expect(codeKind("k7mq-r4xt")).toBe("link");
  expect(codeKind("ABCD EFGH JKLM NPQR STUV WXYZ 23")).toBe("recovery");
  expect(codeKind("abc")).toBeNull();
  expect(deviceTitle(THIS, 0)).toBe("This phone");
  expect(deviceTitle(OTHER, 1)).toBe("Phone 2");
  expect(deviceDetail(OTHER, Date.parse("2026-11-16T10:05:00Z"))).toBe(
    "Added Mon 16 Nov 2026 · last used 5 minutes ago",
  );
  expect(joinedMessage({ person: me(), recovered: false, moved_trips: 0 } as never)).toBe(
    "This phone is now one of yours.",
  );
});
