import type { Trip } from "@detour/shared";
import { useMemo, useState } from "react";
import { Linking, StyleSheet, Text, View } from "react-native";

import { describeError } from "../../api/unwrap";
import {
  AlbumError,
  useExtrasActions,
  useSyncTrips,
  useTripExtras,
} from "../../documents/DocumentsProvider";
import {
  type TripAlbum,
  MAX_ALBUM_NAME,
  albumSource,
  isGooglePhotos,
} from "../../documents/extras";
import { colors, layout, spacing, type } from "../../theme";
import {
  Button,
  IconButton,
  InlineStatus,
  ListRow,
  Notice,
  RowGroup,
  Sheet,
  StateView,
  TextField,
  Tile,
} from "../ds";

// A trip's Photos tab (ADR 031): links to the user's own albums, kept on the server for everyone
// on the trip (ADR 034, step 5) with a copy on the phone. Detour never reads an album: a link opens
// it in Google Photos (or the browser), where the photos stay.

/** Said wherever album links are added: where the link is kept, and what a shared link means. */
export const ALBUM_NOTE =
  "Everyone on this trip sees the links added here. Detour does not read or copy the photos. Anyone who has a shared album's link can open it.";

export const HOW_TO_LINK =
  "In Google Photos, open the album, tap Share, then Copy link, and paste it here.";

export async function openAlbum(album: TripAlbum): Promise<void> {
  await Linking.openURL(album.url);
}

export function TripAlbums({ trip }: { trip: Trip }) {
  const { extras, error } = useTripExtras(trip.id);
  const actions = useExtrasActions();
  // The server holds the trip's albums for everyone on it (ADR 034): read them when shown.
  useSyncTrips(useMemo(() => [trip], [trip]));
  const [adding, setAdding] = useState(false);
  const [menu, setMenu] = useState<TripAlbum | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!extras) return <InlineStatus text="Loading the albums…" busy />;

  const open = async (album: TripAlbum) => {
    setProblem(null);
    try {
      await openAlbum(album);
    } catch {
      setProblem("This phone could not open the album's link. Check that the link is right.");
    }
  };

  const addButton = (
    <Button
      label="Link an album"
      icon="add"
      fill
      testID="link-album"
      onPress={() => setAdding(true)}
    />
  );

  return (
    <View style={styles.wrap}>
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      {extras.albums.length === 0 ? (
        <StateView
          kind="empty"
          layout="inline"
          tight
          icon="photos"
          title="No album linked yet"
          text="Link the album you keep for this trip in Google Photos. Detour opens it in Google Photos; your photos stay there."
          testID="albums-empty"
        >
          {addButton}
          <Text style={styles.note}>{ALBUM_NOTE}</Text>
        </StateView>
      ) : (
        <>
          <RowGroup>
            {extras.albums.map((album) => (
              <ListRow
                key={album.id}
                inset="none"
                leading={<Tile icon="photos" fg={colors.primary} bg={colors.selectedSoft} />}
                title={album.name}
                detail={`${albumSource(album.url)} · ${
                  isGooglePhotos(album.url) ? "opens in Google Photos" : "opens in the browser"
                }`}
                accessibilityHint="Opens the album outside Detour"
                testID={`album-${album.id}`}
                onPress={() => void open(album)}
                trailing={
                  <IconButton
                    icon="dots"
                    label={`Options for ${album.name}`}
                    size="sm"
                    testID={`album-menu-${album.id}`}
                    onPress={() => setMenu(album)}
                  />
                }
              />
            ))}
          </RowGroup>
          {addButton}
          <Text style={styles.note}>{ALBUM_NOTE}</Text>
        </>
      )}
      {adding ? (
        <AddAlbumSheet
          onClose={() => setAdding(false)}
          onSave={async (name, link) => {
            await actions.addAlbum(trip.id, name, link);
            setAdding(false);
          }}
        />
      ) : null}
      {menu ? (
        <AlbumMenuSheet
          album={menu}
          onClose={() => setMenu(null)}
          onRename={async (name) => {
            await actions.renameAlbum(trip.id, menu.id, name);
            setMenu(null);
          }}
          onRemove={async () => {
            await actions.removeAlbum(trip.id, menu.id);
            setMenu(null);
          }}
        />
      ) : null}
    </View>
  );
}

function AddAlbumSheet({
  onClose,
  onSave,
}: {
  onClose: () => void;
  onSave: (name: string, link: string) => Promise<void>;
}) {
  const [link, setLink] = useState("");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(name, link);
    } catch (e) {
      setError(e instanceof AlbumError ? e.message : describeError(e));
      setSaving(false);
    }
  };
  return (
    <Sheet visible title="Link an album" onClose={onClose}>
      <TextField
        label="Album link"
        value={link}
        onChangeText={(t) => {
          setLink(t);
          setError(null);
        }}
        placeholder="https://photos.app.goo.gl/…"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        hint={HOW_TO_LINK}
        error={error}
        testID="album-link"
      />
      <TextField
        label="Name (optional)"
        value={name}
        onChangeText={setName}
        placeholder="Trip album"
        maxLength={MAX_ALBUM_NAME}
        testID="album-name"
      />
      <View style={styles.actions}>
        <Button
          label="Link album"
          fill
          loading={saving}
          disabled={saving || !link.trim()}
          testID="save-album"
          onPress={() => void save()}
        />
        <Button label="Cancel" variant="secondary" fill disabled={saving} onPress={onClose} />
      </View>
    </Sheet>
  );
}

function AlbumMenuSheet({
  album,
  onClose,
  onRename,
  onRemove,
}: {
  album: TripAlbum;
  onClose: () => void;
  onRename: (name: string) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const [name, setName] = useState(album.name);
  const [busy, setBusy] = useState<"rename" | "remove" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async (what: "rename" | "remove") => {
    setBusy(what);
    setError(null);
    try {
      await (what === "rename" ? onRename(name) : onRemove());
    } catch (e) {
      setError(describeError(e));
      setBusy(null);
    }
  };
  return (
    <Sheet visible title={album.name} onClose={onClose}>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <TextField
        label="Name"
        value={name}
        onChangeText={setName}
        maxLength={MAX_ALBUM_NAME}
        testID="album-rename"
      />
      <Button
        label="Save name"
        variant="secondary"
        fill
        loading={busy === "rename"}
        disabled={busy !== null || !name.trim() || name.trim() === album.name}
        testID="save-album-name"
        onPress={() => void run("rename")}
      />
      <Button
        label="Remove link"
        variant="secondary"
        tone="danger"
        fill
        loading={busy === "remove"}
        disabled={busy !== null}
        hint="Removes the link from Detour; the album itself is not touched"
        testID="remove-album"
        onPress={() => void run("remove")}
      />
      <Text style={styles.note}>Removing the link does not delete the album or its photos.</Text>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: layout.block },
  actions: { gap: spacing.sm },
  note: { ...type.caption, color: colors.muted },
});
