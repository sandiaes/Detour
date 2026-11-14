import type { DocumentFiles } from "../documents/files";
import { CannotOpenError } from "../documents/files";
import type { PickedFile } from "../documents/model";
import type { ExchangeFiles, PickedArchive } from "../exchange/files";

/** Files without the native module: what was picked, kept, removed and opened. */
export type FakeFiles = DocumentFiles & {
  /** The next pick's answer; null is a cancelled picker. */
  next: PickedFile | null;
  kept: string[];
  removed: string[];
  opened: string[];
  /** When set, open() fails with this message. */
  openFails: string | null;
};

export const PICKED_PDF: PickedFile = {
  uri: "content://picker/Train_ticket-Vienna.pdf",
  name: "Train_ticket-Vienna.pdf",
  mimeType: "application/pdf",
  size: 245_000,
};

export function createFakeFiles(next: PickedFile | null = PICKED_PDF): FakeFiles {
  const fake: FakeFiles = {
    next,
    kept: [],
    removed: [],
    opened: [],
    openFails: null,
    pick: async () => fake.next,
    keep: async (picked, tripId, id) => {
      const ext = picked.name.includes(".") ? picked.name.slice(picked.name.lastIndexOf(".")) : "";
      const uri = `file:///app/documents/${tripId}/${id}${ext}`;
      fake.kept.push(uri);
      return uri;
    },
    remove: async (uri) => {
      fake.removed.push(uri);
    },
    open: async (doc) => {
      if (fake.openFails) throw new CannotOpenError(fake.openFails);
      fake.opened.push(doc.uri);
    },
  };
  return fake;
}

/** The trip file without the native modules: what was shared, what is picked and what is kept. */
export type FakeExchange = ExchangeFiles & {
  /** The next pick's answer; null is a cancelled picker. */
  next: PickedArchive | null;
  /** Bytes by URI: the picked file, shared files and kept documents. */
  disk: Map<string, Uint8Array>;
  shared: { uri: string; name: string }[];
  /** False: the device has no share sheet. */
  canShare: boolean;
};

export function createFakeExchange(): FakeExchange {
  const fake: FakeExchange = {
    next: null,
    disk: new Map(),
    shared: [],
    canShare: true,
    pick: async () => fake.next,
    readBytes: async (uri) => {
      const bytes = fake.disk.get(uri);
      if (!bytes) throw new Error(`no such file: ${uri}`);
      return bytes;
    },
    saveShareable: async (name, bytes) => {
      const uri = `file:///cache/exports/${name}`;
      fake.disk.set(uri, bytes);
      return uri;
    },
    share: async (uri) => {
      if (!fake.canShare) return false;
      fake.shared.push({ uri, name: uri.slice(uri.lastIndexOf("/") + 1) });
      return true;
    },
    keepBytes: async (bytes, tripId, id, fileName) => {
      const ext = fileName.includes(".") ? fileName.slice(fileName.lastIndexOf(".")) : "";
      const uri = `file:///app/documents/${tripId}/${id}${ext}`;
      fake.disk.set(uri, bytes);
      return uri;
    },
  };
  return fake;
}
