import type { DocumentFiles } from "../documents/files";
import { CannotOpenError } from "../documents/files";
import type { PickedFile } from "../documents/model";

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
