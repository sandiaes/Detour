import { Directory, File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

// The device side of the trip file (ADR 028): reading and writing the zip and handing it to the
// system share sheet. Nothing is uploaded by Detour. This interface lets tests run without the
// native modules.

export type PickedArchive = { uri: string; name: string };

export interface ExchangeFiles {
  /** Opens the system picker for a trip file; null when the user cancels. */
  pick(): Promise<PickedArchive | null>;
  readBytes(uri: string): Promise<Uint8Array>;
  /** Writes the file for sharing (in the cache, which the system may clear) and returns its URI. */
  saveShareable(name: string, bytes: Uint8Array): Promise<string>;
  /** Opens the system share sheet; false if this device has none. */
  share(uri: string): Promise<boolean>;
  /** Writes a restored document into the app's private storage and returns the URI. */
  keepBytes(bytes: Uint8Array, tripId: string, id: string, fileName: string): Promise<string>;
}

function extensionOf(name: string): string {
  const match = /\.[A-Za-z0-9]{1,8}$/.exec(name);
  return match ? match[0].toLowerCase() : "";
}

export function createDeviceExchangeFiles(): ExchangeFiles {
  return {
    async pick() {
      const picked = await File.pickFileAsync({ mimeTypes: ["*/*"] });
      if (picked.canceled || !picked.result) return null;
      return { uri: picked.result.uri, name: picked.result.name };
    },
    async readBytes(uri) {
      return new File(uri).bytes();
    },
    async saveShareable(name, bytes) {
      const folder = new Directory(Paths.cache, "exports");
      folder.create({ intermediates: true, idempotent: true });
      const file = new File(folder, name);
      if (file.exists) file.delete();
      file.create();
      file.write(bytes);
      return file.uri;
    },
    async share(uri) {
      if (!(await Sharing.isAvailableAsync())) return false;
      await Sharing.shareAsync(uri, {
        mimeType: "application/octet-stream",
        UTI: "public.data",
        dialogTitle: "Export trip",
      });
      return true;
    },
    async keepBytes(bytes, tripId, id, fileName) {
      const folder = new Directory(Paths.document, "documents", tripId);
      folder.create({ intermediates: true, idempotent: true });
      const file = new File(folder, `${id}${extensionOf(fileName)}`);
      file.create();
      file.write(bytes);
      return file.uri;
    },
  };
}
