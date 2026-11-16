import { openDatabaseAsync } from "expo-sqlite";

import { DATABASE_NAME } from "../cache/store";
import { createDeviceExchangeFiles } from "../exchange/files";
import { createDeviceFiles } from "./files";
import { createSqliteExtrasStore } from "./extras";
import { createSqliteDocumentStore } from "./store";

/** The app's documents: listed in SQLite, kept in the app's private storage (ADR 023). */
export const deviceDocumentStore = createSqliteDocumentStore(() =>
  openDatabaseAsync(DATABASE_NAME),
);
/** Album links and covers from the phone (ADR 031), in the same database. */
export const deviceExtrasStore = createSqliteExtrasStore(() => openDatabaseAsync(DATABASE_NAME));
export const deviceDocumentFiles = createDeviceFiles();
/** The trip file's reading, writing and sharing (ADR 028). */
export const deviceExchangeFiles = createDeviceExchangeFiles();
