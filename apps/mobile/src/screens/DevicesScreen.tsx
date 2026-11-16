import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, callEmpty, describeError } from "../api/unwrap";
import {
  Button,
  ConfirmSheet,
  ErrorState,
  ListRow,
  LoadingState,
  Notice,
  RowGroup,
  ScreenHeader,
  SectionHeader,
  TextField,
} from "../components/ds";
import { useResource } from "../data/DataProvider";
import {
  type DeviceInfo,
  type LinkCode,
  type PersonInfo,
  type RecoveryCode,
  clockTime,
  codeKind,
  deviceDetail,
  deviceTitle,
  joinedMessage,
} from "../domain/devices";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";
import { formatDate } from "../util/format";

const KEY = "me";

/**
 * Your phones (ADR 034, step 1). Your trips belong to you, not to one phone: another phone joins
 * with a one-time code shown here, and a new phone gets everything back with the recovery code.
 */
export function DevicesScreen() {
  const nav = useNavigation();
  const { state, retry } = useBackend();
  const client = state.phase === "ready" ? state.connection.client : null;
  const me = useResource<PersonInfo>(KEY, (c) => call(c.GET("/v1/me")), { ttlMs: 0 });

  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [linkCode, setLinkCode] = useState<LinkCode | null>(null);
  const [recovery, setRecovery] = useState<RecoveryCode | null>(null);
  const [askRecovery, setAskRecovery] = useState(false);
  const [removing, setRemoving] = useState<DeviceInfo | null>(null);
  const [typed, setTyped] = useState("");
  const [askJoin, setAskJoin] = useState(false);
  // The time the list was drawn against ("last used 5 minutes ago").
  const [now] = useState(() => Date.now());
  const [joined, setJoined] = useState<{ text: string; recovered: boolean } | null>(null);

  const run = async (work: () => Promise<void>) => {
    if (!client) {
      setProblem("The server is not connected yet.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await work();
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const showLinkCode = () =>
    run(async () => {
      setLinkCode(await call(client!.POST("/v1/me/link-codes")));
    });

  const makeRecovery = () =>
    run(async () => {
      setAskRecovery(false);
      setRecovery(await call(client!.POST("/v1/me/recovery-code")));
      setJoined((j) => (j ? { ...j, recovered: false } : j));
      me.refresh();
    });

  const remove = () =>
    run(async () => {
      if (!removing) return;
      await callEmpty(
        client!.DELETE("/v1/me/devices/{device_id}", {
          params: { path: { device_id: removing.id } },
        }),
      );
      setRemoving(null);
      me.refresh();
    });

  const join = () =>
    run(async () => {
      setAskJoin(false);
      const result = await call(
        client!.POST("/v1/installations/join", { body: { code: typed.trim() } }),
      );
      setTyped("");
      setLinkCode(null);
      setJoined({ text: joinedMessage(result), recovered: result.recovered });
      // Connect again: the phone now belongs to another person, so the saved trips of the old
      // one are cleared and the person's trips load.
      retry();
    });

  const kind = codeKind(typed);
  const recoveryLine = me.data
    ? me.data.recovery_code_created_at
      ? `You made a recovery code on ${formatDate(me.data.recovery_code_created_at.slice(0, 10))}.`
      : "You have no recovery code yet."
    : null;

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Your phones" onBack={nav.back} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.block}>
          <Text style={styles.text}>
            Your trips belong to you, not to one phone. Use Detour on another phone with a code from
            this one, or get everything back on a new phone with your recovery code.
          </Text>
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {joined ? (
            <Notice tone="success" label="Done">
              {joined.text}
            </Notice>
          ) : null}
          {joined?.recovered ? (
            <Notice tone="warning" label="Recovery code">
              Your other phones are signed out. Make a new recovery code now and keep it safe.
            </Notice>
          ) : null}
        </View>

        <View style={styles.section}>
          <View style={styles.block}>
            <SectionHeader title="Phones" />
          </View>
          {me.status === "error" && !me.data ? (
            <ErrorState text={describeError(me.error)} onRetry={me.refresh} />
          ) : !me.data ? (
            <LoadingState text="Loading your phones…" />
          ) : (
            <RowGroup>
              {me.data.devices.map((d, i) => (
                <ListRow
                  key={d.id}
                  icon="lock"
                  title={deviceTitle(d, i)}
                  detail={deviceDetail(d, now)}
                  testID={`device-${i}`}
                  trailing={
                    d.this_device ? undefined : (
                      <Button
                        label="Remove"
                        variant="ghost"
                        size="sm"
                        tone="danger"
                        accessibilityLabel={`Remove ${deviceTitle(d, i)}`}
                        testID={`device-remove-${i}`}
                        onPress={() => setRemoving(d)}
                      />
                    )
                  }
                />
              ))}
            </RowGroup>
          )}
        </View>

        <View style={styles.block}>
          <SectionHeader title="Add a phone" />
          <Text style={styles.text}>
            On the other phone, open More, Your phones, and type this code under &quot;Use a code on
            this phone&quot;.
          </Text>
          {linkCode ? (
            <View style={styles.codeBox}>
              <Text selectable style={styles.code} testID="link-code">
                {linkCode.code}
              </Text>
              <Text style={styles.muted}>
                Works once, until {clockTime(linkCode.expires_at)}. Making a new code cancels this
                one.
              </Text>
            </View>
          ) : null}
          <Button
            label={linkCode ? "New code" : "Show a code"}
            variant={linkCode ? "secondary" : "primary"}
            loading={busy && !linkCode}
            disabled={busy}
            testID="devices-show-code"
            onPress={showLinkCode}
          />
        </View>

        <View style={styles.block}>
          <SectionHeader title="Use a code on this phone" />
          <TextField
            label="Code from your other phone, or your recovery code"
            value={typed}
            onChangeText={setTyped}
            autoCapitalize="characters"
            autoCorrect={false}
            placeholder="K7MQ-R4XT"
            hint={
              kind === "recovery"
                ? "A recovery code: your other phones will be signed out."
                : "Spaces and hyphens do not matter."
            }
            testID="devices-code-input"
          />
          <Button
            label="Use this code"
            variant="secondary"
            disabled={busy || kind === null}
            testID="devices-join"
            onPress={() => setAskJoin(true)}
          />
        </View>

        <View style={styles.block}>
          <SectionHeader title="Recovery code" />
          <Text style={styles.text}>
            If you lose every phone, this code is the only way back to your trips: there is no email
            or password. Write it down or keep it in a password manager.
          </Text>
          {recoveryLine ? <Text style={styles.muted}>{recoveryLine}</Text> : null}
          {recovery ? (
            <View style={styles.codeBox}>
              <Text selectable style={styles.code} testID="recovery-code">
                {recovery.code}
              </Text>
              <Text style={styles.muted}>
                Shown only now. Any earlier recovery code no longer works.
              </Text>
            </View>
          ) : null}
          <Button
            label={
              me.data?.recovery_code_created_at
                ? "Make a new recovery code"
                : "Make a recovery code"
            }
            variant="secondary"
            disabled={busy}
            testID="devices-recovery"
            onPress={() =>
              me.data?.recovery_code_created_at ? setAskRecovery(true) : void makeRecovery()
            }
          />
        </View>
      </ScrollView>

      <ConfirmSheet
        visible={removing !== null}
        title="Remove this phone?"
        message="It is signed out at once and starts again as a new, empty phone. Your trips stay with you. Documents kept only on that phone stay there."
        confirmLabel="Remove phone"
        busy={busy}
        confirmTestID="device-remove-confirm"
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(null)}
      />
      <ConfirmSheet
        visible={askJoin}
        title="Use this code?"
        message={
          kind === "recovery"
            ? "This phone becomes one of yours and every other phone of yours is signed out. Trips already on this phone come along."
            : "This phone becomes one of yours and shows your trips. Trips already on this phone come along."
        }
        confirmLabel="Use code"
        destructive={kind === "recovery"}
        busy={busy}
        confirmTestID="devices-join-confirm"
        onConfirm={() => void join()}
        onCancel={() => setAskJoin(false)}
      />
      <ConfirmSheet
        visible={askRecovery}
        title="Make a new recovery code?"
        message="Your current recovery code stops working. Keep the new one somewhere safe."
        confirmLabel="Make new code"
        destructive={false}
        busy={busy}
        confirmTestID="devices-recovery-confirm"
        onConfirm={() => void makeRecovery()}
        onCancel={() => setAskRecovery(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { gap: layout.section, paddingBottom: spacing.xxl },
  section: { gap: spacing.sm },
  block: { paddingHorizontal: layout.gutter, gap: spacing.sm },
  text: { ...type.label, color: colors.text },
  muted: { ...type.caption, color: colors.muted },
  codeBox: { gap: spacing.xs, paddingVertical: spacing.sm },
  code: { ...type.title, color: colors.text, letterSpacing: 2 },
});
