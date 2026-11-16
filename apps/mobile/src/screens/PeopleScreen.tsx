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
import { useData, useResource } from "../data/DataProvider";
import { keys } from "../data/actions";
import { type LinkCode, type PersonInfo, clockTime, codeKind } from "../domain/devices";
import { type LinkedPerson, personName } from "../domain/sharing";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";
import { formatDate } from "../util/format";

const KEY = "me";

/**
 * People (ADR 034, step 3): your name, the people you can share trips with, and the one-time
 * invite code that links two people. A trip is shared from its settings, or with "Who's going"
 * when it is created.
 */
export function PeopleScreen() {
  const nav = useNavigation();
  const { state } = useBackend();
  const data = useData();
  const client = state.phase === "ready" ? state.connection.client : null;
  const me = useResource<PersonInfo>(KEY, (c) => call(c.GET("/v1/me")), { ttlMs: 0 });

  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const [invite, setInvite] = useState<LinkCode | null>(null);
  const [typed, setTyped] = useState("");
  const [unlinking, setUnlinking] = useState<LinkedPerson | null>(null);

  const shownName = name ?? me.data?.display_name ?? "";

  const run = async (work: () => Promise<void>) => {
    if (!client) {
      setProblem("The server is not connected yet.");
      return;
    }
    setBusy(true);
    setProblem(null);
    setDone(null);
    try {
      await work();
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(false);
    }
  };

  const saveName = () =>
    run(async () => {
      const updated = await call(
        client!.PATCH("/v1/me", { body: { display_name: shownName.trim() || null } }),
      );
      data.put(KEY, updated);
      setName(null);
      // Trips show members by name.
      data.invalidate(keys.trips);
      setDone(
        updated.display_name ? `Others now see you as ${updated.display_name}.` : "Name removed.",
      );
    });

  const showInvite = () =>
    run(async () => {
      setInvite(await call(client!.POST("/v1/me/invite-codes")));
    });

  const link = () =>
    run(async () => {
      const updated = await call(client!.POST("/v1/people/link", { body: { code: typed.trim() } }));
      data.put(KEY, updated);
      setTyped("");
      const newest = updated.people[updated.people.length - 1];
      setDone(
        `You are linked with ${personName(newest?.name)}. Share a trip from its settings, or choose them under "Who's going" on a new trip.`,
      );
    });

  const unlink = () =>
    run(async () => {
      if (!unlinking) return;
      await callEmpty(
        client!.DELETE("/v1/people/{person_id}", {
          params: { path: { person_id: unlinking.person_id } },
        }),
      );
      setUnlinking(null);
      me.refresh();
    });

  return (
    <View style={styles.fill}>
      <ScreenHeader title="People" onBack={nav.back} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.block}>
          <Text style={styles.text}>
            Plan a trip together: link with someone once, then share a trip with them. Both of you
            see and change it; only the person who created it can delete it.
          </Text>
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {done ? <Notice tone="success">{done}</Notice> : null}
        </View>

        <View style={styles.block}>
          <SectionHeader title="Your name" />
          <TextField
            label="Name others see"
            value={shownName}
            onChangeText={setName}
            maxLength={40}
            placeholder="For example Jose"
            hint="Shown on shared trips. Nothing else about you is shared."
            testID="people-name"
          />
          <Button
            label="Save name"
            variant="secondary"
            size="sm"
            disabled={busy || name === null}
            testID="people-save-name"
            onPress={saveName}
          />
        </View>

        <View style={styles.section}>
          <View style={styles.block}>
            <SectionHeader title="Linked people" />
          </View>
          {me.status === "error" && !me.data ? (
            <ErrorState text={describeError(me.error)} onRetry={me.refresh} />
          ) : !me.data ? (
            <LoadingState text="Loading…" />
          ) : me.data.people.length === 0 ? (
            <View style={styles.block}>
              <Text style={styles.muted}>Nobody yet.</Text>
            </View>
          ) : (
            <RowGroup>
              {me.data.people.map((p, i) => (
                <ListRow
                  key={p.person_id}
                  icon="trips"
                  title={personName(p.name)}
                  detail={`Linked ${formatDate(p.linked_at.slice(0, 10))}`}
                  testID={`person-${i}`}
                  trailing={
                    <Button
                      label="Unlink"
                      variant="ghost"
                      size="sm"
                      tone="danger"
                      accessibilityLabel={`Unlink ${personName(p.name)}`}
                      testID={`person-unlink-${i}`}
                      onPress={() => setUnlinking(p)}
                    />
                  }
                />
              ))}
            </RowGroup>
          )}
        </View>

        <View style={styles.block}>
          <SectionHeader title="Add someone" />
          <Text style={styles.text}>
            Show your invite code to the other person. They open More, People on their phone and
            type it under &quot;Use an invite code&quot;.
          </Text>
          {invite ? (
            <View style={styles.codeBox}>
              <Text selectable style={styles.code} testID="invite-code">
                {invite.code}
              </Text>
              <Text style={styles.muted}>Works once, until {clockTime(invite.expires_at)}.</Text>
            </View>
          ) : null}
          <Button
            label={invite ? "New invite code" : "Show my invite code"}
            variant={invite ? "secondary" : "primary"}
            disabled={busy}
            testID="people-show-invite"
            onPress={showInvite}
          />
        </View>

        <View style={styles.block}>
          <SectionHeader title="Use an invite code" />
          <TextField
            label="Invite code from the other person"
            value={typed}
            onChangeText={setTyped}
            autoCapitalize="characters"
            autoCorrect={false}
            placeholder="K7MQ-R4XT"
            testID="people-code-input"
          />
          <Button
            label="Link"
            variant="secondary"
            disabled={busy || codeKind(typed) !== "link"}
            testID="people-link"
            onPress={link}
          />
        </View>
      </ScrollView>

      <ConfirmSheet
        visible={unlinking !== null}
        title="Unlink this person?"
        message={`You can no longer share new trips with ${personName(unlinking?.name)}. Trips already shared stay shared until one of you leaves or stops sharing them.`}
        confirmLabel="Unlink"
        busy={busy}
        confirmTestID="person-unlink-confirm"
        onConfirm={() => void unlink()}
        onCancel={() => setUnlinking(null)}
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
