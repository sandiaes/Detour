import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { useBackend } from "../api/BackendProvider";
import { call, describeError } from "../api/unwrap";
import {
  Badge,
  Button,
  ConfirmSheet,
  ErrorState,
  ListRow,
  LoadingState,
  Notice,
  RowGroup,
  ScreenHeader,
  GroupHeader,
  Sheet,
} from "../components/ds";
import { useResource } from "../data/DataProvider";
import {
  type CatalogRegion,
  type RegionCatalog,
  type RegionRemoval,
  anyImportInProgress,
  groupByContinent,
  groupSummary,
  hasData,
  importInProgress,
  regionLine,
  removalMessage,
  usageLine,
} from "../domain/regions";
import { useNavigation } from "../nav/Navigator";
import { colors, layout, spacing, type } from "../theme";

const REFRESH_MS = 15_000;
const KEY = "regions:catalog";

/**
 * Regions (ADR 033): the regions whose places the server can offer as sights, and, for the
 * owner, importing a region (the server asks GitHub to run the import, which takes minutes) and
 * removing one to free space. A trip keeps every place it uses when a region is removed.
 */
export function RegionsScreen() {
  const nav = useNavigation();
  const { state } = useBackend();
  const client = state.phase === "ready" ? state.connection.client : null;
  const catalog = useResource<RegionCatalog>(KEY, (c) => call(c.GET("/v1/regions/catalog")), {
    ttlMs: 0,
  });
  const [openId, setOpenId] = useState<string | null>(null);
  // The continents the user opened or closed; the others follow the default below.
  const [folded, setFolded] = useState<Record<string, boolean>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [removal, setRemoval] = useState<RegionRemoval | null>(null);

  // An import takes minutes: look again while one is under way.
  const watching = anyImportInProgress(catalog.data);
  const { refresh } = catalog;
  useEffect(() => {
    if (!watching) return;
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [watching, refresh]);

  const groups = groupByContinent(catalog.data?.regions ?? []);
  const anyData = groups.some((g) => g.regions.some(hasData));
  const region = catalog.data?.regions.find((r) => r.id === openId) ?? null;
  const canManage = catalog.data?.can_manage === true;

  const run = async (work: () => Promise<void>) => {
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

  const startImport = (r: CatalogRegion) =>
    run(async () => {
      if (!client) throw new Error("The server is not connected yet.");
      await call(
        client.POST("/v1/regions/{region_id}/import", {
          params: { path: { region_id: r.id } },
          body: { gazetteer: true },
        }),
      );
      setOpenId(null);
      catalog.refresh();
    });

  const askRemoval = (r: CatalogRegion) =>
    run(async () => {
      if (!client) throw new Error("The server is not connected yet.");
      setRemoval(
        await call(
          client.GET("/v1/regions/{region_id}/removal-preview", {
            params: { path: { region_id: r.id } },
          }),
        ),
      );
    });

  const remove = () =>
    run(async () => {
      if (!client || !removal) return;
      await call(
        client.DELETE("/v1/regions/{region_id}", {
          params: { path: { region_id: removal.region_id } },
        }),
      );
      setRemoval(null);
      setOpenId(null);
      catalog.refresh();
    });

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Regions" onBack={nav.back} />
      <ScrollView contentContainerStyle={styles.content}>
        {catalog.status === "error" && !catalog.data ? (
          <ErrorState text={describeError(catalog.error)} onRetry={catalog.refresh} />
        ) : !catalog.data ? (
          <LoadingState text="Loading the regions…" />
        ) : (
          <>
            <View style={styles.intro}>
              <Text style={styles.text}>
                Sights come from the regions below. A trip to another place still works: you add its
                places yourself.
              </Text>
              <Text style={styles.muted} testID="regions-usage">
                {usageLine(catalog.data)}
              </Text>
              {!canManage ? (
                <Notice tone="info">
                  Only the owner of this server can import or remove regions.
                </Notice>
              ) : !catalog.data.import_enabled ? (
                <Notice tone="warning" label="Import">
                  This server cannot start imports: it has no GitHub access set up.
                </Notice>
              ) : null}
              {problem && !region && !removal ? <Notice tone="error">{problem}</Notice> : null}
            </View>
            <View>
              {groups.map((group, index) => {
                // A continent starts open when it holds data or an import; when none does, the
                // first one is open so the screen is never a list of closed bands.
                const startsOpen = anyData ? group.regions.some(hasData) : index === 0;
                const open =
                  folded[group.continent] === undefined ? startsOpen : !folded[group.continent];
                return (
                  <View key={group.continent}>
                    <GroupHeader
                      title={group.continent}
                      summary={groupSummary(group.regions)}
                      expanded={open}
                      onToggle={() => setFolded((f) => ({ ...f, [group.continent]: open }))}
                      testID={`continent-${group.continent}`}
                    />
                    {open ? (
                      <RowGroup>
                        {group.regions.map((r) => (
                          <ListRow
                            key={r.id}
                            title={r.name}
                            detail={regionLine(r)}
                            testID={`region-${r.id}`}
                            trailing={
                              importInProgress(r) ? (
                                <Badge label="Importing" tone="warning" />
                              ) : r.state === "available" ? (
                                <Badge label="Available" tone="primary" />
                              ) : undefined
                            }
                            onPress={() => {
                              setProblem(null);
                              setOpenId(r.id);
                            }}
                          />
                        ))}
                      </RowGroup>
                    ) : null}
                  </View>
                );
              })}
            </View>
          </>
        )}
      </ScrollView>

      {region ? (
        <Sheet visible title={region.name} onClose={() => setOpenId(null)}>
          <Text style={styles.text}>{regionLine(region)}</Text>
          {region.job?.message ? <Text style={styles.muted}>{region.job.message}</Text> : null}
          {problem ? <Notice tone="error">{problem}</Notice> : null}
          {canManage && catalog.data ? (
            <View style={styles.actions}>
              {importInProgress(region) ? (
                <Text style={styles.muted}>
                  The import runs on GitHub and takes a few minutes. This screen updates by itself.
                </Text>
              ) : (
                <Button
                  label={region.state === "available" ? "Import again" : "Import this region"}
                  variant="primary"
                  fill
                  loading={busy}
                  disabled={busy || !catalog.data.import_enabled}
                  testID="region-import"
                  onPress={() => void startImport(region)}
                />
              )}
              {region.places > 0 || region.places_kept > 0 ? (
                <Button
                  label="Remove its data"
                  variant="secondary"
                  tone="danger"
                  fill
                  disabled={busy || importInProgress(region)}
                  testID="region-remove"
                  onPress={() => void askRemoval(region)}
                />
              ) : null}
            </View>
          ) : null}
        </Sheet>
      ) : null}

      <ConfirmSheet
        visible={removal !== null}
        title={removal ? `Remove ${removal.name}?` : "Remove region?"}
        message={removal ? removalMessage(removal) : ""}
        confirmLabel="Yes, remove the data"
        cancelLabel="Keep it"
        confirmTestID="confirm-region-remove"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoval(null)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { gap: layout.section, paddingBottom: spacing.xxl },
  intro: { paddingHorizontal: layout.gutter, gap: spacing.sm },
  text: { ...type.label, color: colors.text },
  muted: { ...type.caption, color: colors.muted },
  actions: { gap: spacing.sm },
});
