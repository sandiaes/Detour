import type { Trip, TripVisit } from "@detour/shared";
import { useMemo, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";

import { call, describeError } from "../api/unwrap";
import { useBackend } from "../api/BackendProvider";
import {
  Button,
  CompactHeader,
  EmptyState,
  ErrorState,
  Icon,
  IconButton,
  KindIcon,
  ListRow,
  LoadingState,
  Notice,
  RowGroup,
  StopMark,
  Tabs,
  WakingServer,
} from "../components/ds";
import { PastTripMap } from "../components/PastTripMap";
import { OfflineMap } from "../components/OfflineMap";
import { ResourceNotices } from "../components/ResourceNotices";
import { keys, useTripActions } from "../data/actions";
import { useResource } from "../data/DataProvider";
import {
  type VisitGroup,
  VISIT_KIND_LABEL,
  dayColor,
  daySoft,
  dayRecord,
  groupVisitsByCity,
  stopRecordLine,
  visitCounts,
  visitedPoints,
} from "../domain/pastTrip";
import { useNavigation } from "../nav/Navigator";
import { border, colors, layout, radius, size as sizes, spacing, type, weight } from "../theme";
import { formatDayLabel, formatTripSpan, pluralise } from "../util/format";

type Row =
  | { type: "city"; key: string; group: VisitGroup }
  | { type: "day"; key: string; day: number; startDate: string | null }
  | { type: "visit"; key: string; visit: TripVisit; startDate: string | null; withDay: boolean };

function rowsOf(groups: VisitGroup[], startDate: string | null): Row[] {
  return groups.flatMap((group) => [
    { type: "city" as const, key: `g:${group.key}`, group },
    ...group.visits.map((visit) => ({
      type: "visit" as const,
      key: visit.id,
      visit,
      startDate,
      withDay: true,
    })),
  ]);
}

/** The day record as rows: a heading for each day, then its stops with their times. */
function daysOf(visits: TripVisit[], startDate: string | null): Row[] {
  return dayRecord(visits).flatMap(({ day, stops }) => [
    { type: "day" as const, key: `d:${day}`, day, startDate },
    ...stops.map((visit) => ({
      type: "visit" as const,
      key: visit.id,
      visit,
      startDate,
      withDay: false,
    })),
  ]);
}

/** A past trip (ADR 006, ADR 026): the stops that were visited, on a map, as the day-by-day record
 * and as a list grouped by city. There are no routes or travel times: the archive does not keep
 * them. */
export function PastTripScreen({ tripId }: { tripId: string }) {
  const nav = useNavigation();
  const { state } = useBackend();
  const actions = useTripActions();
  const trips = useResource<Trip[]>(keys.trips, (c) => call(c.GET("/v1/trips")));
  const visits = useResource<TripVisit[]>(keys.visits(tripId), (c) =>
    call(c.GET("/v1/trips/{trip_id}/visits", { params: { path: { trip_id: tripId } } })),
  );
  const [view, setView] = useState<"map" | "days" | "list">("map");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const trip = trips.data?.find((t) => t.id === tripId);
  const all = visits.data;
  const groups = useMemo(
    () => (all && trip ? groupVisitsByCity(all, trip.destination.name) : []),
    [all, trip],
  );
  const rows = useMemo(() => rowsOf(groups, trip?.start_date ?? null), [groups, trip?.start_date]);
  const days = useMemo(() => daysOf(all ?? [], trip?.start_date ?? null), [all, trip?.start_date]);
  const points = useMemo(() => (all ? visitedPoints(all) : []), [all]);

  if (trips.data === undefined || all === undefined) {
    const failed = trips.status === "error" ? trips : visits.status === "error" ? visits : null;
    return (
      <View style={styles.fill}>
        <CompactHeader title="Past trip" onBack={nav.back} />
        {failed ? (
          <ErrorState
            text={describeError(failed.error)}
            onRetry={() => {
              trips.refresh();
              visits.refresh();
            }}
          />
        ) : trips.waking || visits.waking ? (
          <WakingServer />
        ) : (
          <LoadingState text="Loading the trip…" />
        )}
      </View>
    );
  }
  if (!trip) {
    return (
      <View style={styles.fill}>
        <CompactHeader title="Past trip" onBack={nav.back} />
        <EmptyState
          title="Trip not found"
          text="It may have been deleted."
          action={{ label: "Back to trips", onPress: () => nav.switchRoot({ name: "trips" }) }}
        />
      </View>
    );
  }

  const counts = visitCounts(all);
  const mapConfig = state.phase === "ready" ? state.connection.config.map : null;

  const toggle = async (visit: TripVisit) => {
    setBusy(visit.id);
    setProblem(null);
    try {
      await actions.setVisitConfirmed(tripId, visit.id, !visit.confirmed);
    } catch (e) {
      setProblem(describeError(e));
    } finally {
      setBusy(null);
    }
  };

  const summary = counts.placesToEat
    ? `${pluralise(counts.cities, "city", "cities")}, ${pluralise(counts.attractions, "attraction")} ` +
      `and ${pluralise(counts.placesToEat, "place")} to eat visited`
    : `${pluralise(counts.cities, "city", "cities")} and ` +
      `${pluralise(counts.attractions, "attraction")} visited`;

  const header = (
    <View>
      <CompactHeader
        title={trip.title}
        subtitle={`${trip.destination.name} · ${formatTripSpan(trip.start_date, trip.end_date, trip.duration_days)}`}
        onBack={nav.back}
        right={
          <IconButton
            icon="settings"
            label="Trip settings"
            hint="Mark as past, ask for new proposals or delete the trip"
            size="sm"
            testID="trip-settings"
            onPress={() => nav.push({ name: "tripSettings", tripId })}
          />
        }
      />
      <View style={styles.facts}>
        <Text style={styles.summary}>{summary}</Text>
        {counts.skipped > 0 ? (
          <Text style={styles.meta}>{pluralise(counts.skipped, "visit")} marked as skipped</Text>
        ) : null}
      </View>
      <RowGroup>
        <ListRow
          icon="document"
          title="Documents"
          detail="Tickets and bookings, kept on this phone"
          testID="past-trip-documents"
          onPress={() => nav.push({ name: "tripDocuments", tripId })}
        />
        <ListRow
          icon="export"
          title="Export trip"
          detail="A file with this trip, to keep or share"
          testID="past-trip-export"
          onPress={() => nav.push({ name: "exportTrips", tripId })}
        />
      </RowGroup>
      <ResourceNotices resource={visits} noun="this trip" inset />
      {problem ? (
        <Notice inset tone="error">
          {problem}
        </Notice>
      ) : null}
      <Tabs<"map" | "days" | "list">
        items={[
          { key: "map", label: "Map", accessibilityLabel: "Show the map" },
          { key: "days", label: "Days", accessibilityLabel: "Show the days" },
          { key: "list", label: "List", accessibilityLabel: "Show the list by city" },
        ]}
        value={view}
        onChange={setView}
        testID="show"
      />
    </View>
  );

  if (all.length === 0) {
    return (
      <View style={styles.fill}>
        {header}
        <EmptyState
          title="Nothing was kept"
          text="This trip had no plan chosen and no destination city, so there are no places to show."
        />
      </View>
    );
  }

  if (view === "map") {
    return (
      <View style={styles.fill}>
        {header}
        {points.length === 0 ? (
          <EmptyState
            title="Every visit is marked as skipped"
            text="Nothing is left to show on the map. Restore a visit in the list."
            action={{ label: "Show the list", onPress: () => setView("list") }}
          />
        ) : mapConfig ? (
          <PastTripMap points={points} map={mapConfig} onShowList={() => setView("list")} />
        ) : (
          <OfflineMap />
        )}
      </View>
    );
  }

  const shown = view === "days" ? days : rows;
  return (
    <View style={styles.fill}>
      <FlatList
        data={shown}
        keyExtractor={(r) => r.key}
        ListHeaderComponent={header}
        contentContainerStyle={styles.list}
        initialNumToRender={14}
        maxToRenderPerBatch={14}
        windowSize={7}
        ListEmptyComponent={
          <EmptyState
            title="No stops were kept by day"
            text="This trip was archived before days were kept. Its places are in the list and on the map."
            action={{ label: "Show the list", onPress: () => setView("list") }}
          />
        }
        renderItem={({ item }) =>
          item.type === "day" ? (
            <View style={styles.dayHeadRow}>
              <StopMark kind="sight" label={item.day} color={dayColor(item.day)} />
              <Text accessibilityRole="header" style={styles.dayHeading}>
                {formatDayLabel(item.startDate, item.day)}
              </Text>
            </View>
          ) : item.type === "city" ? (
            <CityHeader
              group={item.group}
              busy={busy === item.group.city?.id}
              disabled={busy !== null || !actions.connected}
              onToggle={toggle}
            />
          ) : (
            <VisitRow
              visit={item.visit}
              startDate={item.startDate}
              withDay={item.withDay}
              busy={busy === item.visit.id}
              disabled={busy !== null || !actions.connected}
              onToggle={toggle}
            />
          )
        }
      />
    </View>
  );
}

function ToggleButton({
  visit,
  busy,
  disabled,
  onToggle,
}: {
  visit: TripVisit;
  busy: boolean;
  disabled: boolean;
  onToggle: (v: TripVisit) => Promise<void>;
}) {
  return (
    <Button
      testID={`toggle-${visit.id}`}
      label={visit.confirmed ? "Skip" : "Restore"}
      variant="ghost"
      size="sm"
      accessibilityLabel={
        visit.confirmed ? `Mark ${visit.name} as skipped` : `Mark ${visit.name} as visited again`
      }
      loading={busy}
      disabled={disabled}
      onPress={() => void onToggle(visit)}
    />
  );
}

function CityHeader({
  group,
  busy,
  disabled,
  onToggle,
}: {
  group: VisitGroup;
  busy: boolean;
  disabled: boolean;
  onToggle: (v: TripVisit) => Promise<void>;
}) {
  const { city } = group;
  const skipped = city !== null && !city.confirmed;
  return (
    <View style={styles.cityRow}>
      <Icon name="city" size="md" color={skipped ? colors.muted : colors.primary} />
      <View style={styles.rowText}>
        <Text accessibilityRole="header" style={[styles.cityName, skipped && styles.skipped]}>
          {group.name}
        </Text>
        <Text style={styles.meta}>
          {city ? `${VISIT_KIND_LABEL.city} · ${skipped ? "skipped" : "visited"}` : "Destination"}
          {` · ${
            group.visits.every((v) => v.kind === "attraction")
              ? pluralise(group.visits.length, "attraction")
              : pluralise(group.visits.length, "stop")
          }`}
        </Text>
      </View>
      {city ? (
        <ToggleButton visit={city} busy={busy} disabled={disabled} onToggle={onToggle} />
      ) : null}
    </View>
  );
}

function VisitRow({
  visit,
  startDate,
  withDay,
  busy,
  disabled,
  onToggle,
}: {
  visit: TripVisit;
  startDate: string | null;
  /** The list by city says the day; the day record is already under a day heading. */
  withDay: boolean;
  busy: boolean;
  disabled: boolean;
  onToggle: (v: TripVisit) => Promise<void>;
}) {
  return (
    <View style={styles.visitRow}>
      <View
        style={[
          styles.visitIcon,
          { backgroundColor: visit.confirmed ? daySoft(visit.day_number) : colors.surfaceMuted },
        ]}
      >
        <KindIcon
          kind={visit.kind === "city" ? "other" : visit.kind}
          size="sm"
          color={visit.confirmed ? dayColor(visit.day_number) : colors.muted}
        />
      </View>
      <View style={styles.rowText}>
        <Text style={[styles.visitName, !visit.confirmed && styles.skipped]}>{visit.name}</Text>
        <Text style={styles.meta}>
          {withDay
            ? `${formatDayLabel(startDate, visit.day_number)}${visit.kind === "attraction" ? "" : ` · ${VISIT_KIND_LABEL[visit.kind]}`}`
            : stopRecordLine(visit)}
          {visit.confirmed ? "" : " · skipped"}
        </Text>
      </View>
      <ToggleButton visit={visit} busy={busy} disabled={disabled} onToggle={onToggle} />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  list: { paddingBottom: spacing.xxl },
  facts: { paddingHorizontal: layout.gutter, paddingBottom: layout.block, gap: spacing.xxs },
  summary: { ...type.cardTitle, color: colors.text },
  meta: { ...type.caption, color: colors.muted },
  // Flat rows under hairlines, as everywhere else: no tinted boxes, no round buttons.
  cityRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginTop: layout.block,
    minHeight: sizes.row,
    paddingHorizontal: layout.gutter,
    paddingVertical: spacing.xs,
    borderBottomWidth: border.hairline,
    borderBottomColor: colors.border,
  },
  // A row is an icon on a soft tile in the day's colour, the name and a quiet line, and a small
  // text action: no boxes, one hairline between rows.
  visitRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: sizes.row,
    paddingHorizontal: layout.gutter,
    paddingVertical: spacing.xs,
    borderBottomWidth: border.hairline,
    borderBottomColor: colors.border,
  },
  visitIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  dayHeadRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: layout.section,
    paddingHorizontal: layout.gutter,
    paddingBottom: spacing.sm,
    borderBottomWidth: border.hairline,
    borderBottomColor: colors.border,
  },
  dayHeading: { ...type.label, fontWeight: weight.bold, color: colors.text },
  rowText: { flex: 1, gap: spacing.xxs },
  cityName: { ...type.label, fontWeight: weight.bold, color: colors.text },
  visitName: { ...type.label, fontWeight: weight.semibold, color: colors.text },
  // Skipped is also written in the line below the name: never colour or strike-through alone.
  skipped: { textDecorationLine: "line-through", color: colors.muted },
});
