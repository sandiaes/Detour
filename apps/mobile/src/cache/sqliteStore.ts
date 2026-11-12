import { openDatabaseAsync } from "expo-sqlite";

import { DATABASE_NAME, createSqliteStore, safeStore } from "./store";

/** The app's store: SQLite on the device, never fatal. */
export const deviceCacheStore = safeStore(
  createSqliteStore(() => openDatabaseAsync(DATABASE_NAME)),
);
