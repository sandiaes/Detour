import { Directory, File, Paths } from "expo-file-system";

import { ACCEPTED_TYPES, type PickedFile, type TripDocument, mimeFromName } from "./model";

// The files of documents (ADR 023): picked with the system file picker, copied into the app's
// private storage (Paths.document/documents/<trip>/), opened with the system viewer. Nothing is
// uploaded. This interface lets tests run without the native module.

export interface DocumentFiles {
  /** Opens the system picker; null when the user cancels. */
  pick(): Promise<PickedFile | null>;
  /** Copies the picked file into the app's storage and returns the copy's URI. */
  keep(picked: PickedFile, tripId: string, id: string): Promise<string>;
  /** Opens the system picker for one picture (a trip's cover, ADR 031); null when cancelled. */
  pickImage(): Promise<PickedFile | null>;
  /** Copies a picked picture into the app's covers folder and returns the copy's URI. Each copy
   * has a new name, so a changed cover is never shown from an old cached image. */
  keepCover(picked: PickedFile, tripId: string): Promise<string>;
  /** The bytes of a file kept by the app (a cover to upload, ADR 034). */
  readBytes(uri: string): Promise<Uint8Array>;
  /** Writes a cover received from the server into the covers folder and returns its URI. */
  keepCoverBytes(bytes: Uint8Array, tripId: string): Promise<string>;
  remove(uri: string): Promise<void>;
  /** Shows the file with the platform's viewer (Quick Look on iOS, an installed app on Android). */
  open(doc: Pick<TripDocument, "uri" | "mimeType" | "title">): Promise<void>;
}

export class CannotOpenError extends Error {}

function extensionOf(name: string): string {
  const match = /\.[A-Za-z0-9]{1,8}$/.exec(name);
  return match ? match[0].toLowerCase() : "";
}

/** The device implementation (tests use testing/fakeFiles.ts instead). */
export function createDeviceFiles(): DocumentFiles {
  return {
    async pick() {
      const picked = await File.pickFileAsync({ mimeTypes: ACCEPTED_TYPES });
      if (picked.canceled || !picked.result) return null;
      const f = picked.result;
      return {
        uri: f.uri,
        name: f.name,
        mimeType: f.type || mimeFromName(f.name),
        size: Number.isFinite(f.size) && f.size > 0 ? f.size : null,
      };
    },
    async pickImage() {
      const picked = await File.pickFileAsync({ mimeTypes: ["image/*"] });
      if (picked.canceled || !picked.result) return null;
      const f = picked.result;
      const mimeType = f.type || mimeFromName(f.name);
      if (!mimeType.startsWith("image/")) return null;
      return {
        uri: f.uri,
        name: f.name,
        mimeType,
        size: Number.isFinite(f.size) && f.size > 0 ? f.size : null,
      };
    },
    async keepCover(picked, tripId) {
      const folder = new Directory(Paths.document, "covers");
      folder.create({ intermediates: true, idempotent: true });
      const target = new File(folder, `${tripId}-${Date.now()}${extensionOf(picked.name)}`);
      await new File(picked.uri).copy(target);
      return target.uri;
    },
    async readBytes(uri) {
      return new File(uri).bytes();
    },
    async keepCoverBytes(bytes, tripId) {
      const folder = new Directory(Paths.document, "covers");
      folder.create({ intermediates: true, idempotent: true });
      const target = new File(folder, `${tripId}-${Date.now()}.jpg`);
      target.create();
      target.write(bytes);
      return target.uri;
    },
    async keep(picked, tripId, id) {
      const folder = new Directory(Paths.document, "documents", tripId);
      folder.create({ intermediates: true, idempotent: true });
      const target = new File(folder, `${id}${extensionOf(picked.name)}`);
      await new File(picked.uri).copy(target);
      return target.uri;
    },
    async remove(uri) {
      const file = new File(uri);
      if (file.exists) file.delete();
    },
    async open(doc) {
      const file = new File(doc.uri);
      if (!file.exists) throw new CannotOpenError("The file is no longer on this device.");
      if (!(await file.canPreview({ mimeType: doc.mimeType }))) {
        throw new CannotOpenError("No app on this device can show this kind of file.");
      }
      await file.preview({ title: doc.title, mimeType: doc.mimeType });
    },
  };
}
