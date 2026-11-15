import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { parseMinutes } from "../../domain/duration";
import { spacing } from "../../theme";
import { formatMinutes } from "../../util/format";
import { TextField } from "./fields";
import { Chip } from "./primitives";

// How long to stay: one free field (minutes, or "1h30") and, where the place has a usual length,
// a pill that goes back to it. Replaces the fixed 30/60/90 pills (owner request, 2026-11-15).

export function DurationField({
  label = "How long",
  minutes,
  onChange,
  onValidity,
  hasDefault = false,
  defaultMinutes = null,
  defaultLabel,
  testID = "duration",
}: {
  label?: string;
  /** The length typed; null means "use the default". */
  minutes: number | null;
  onChange: (minutes: number | null) => void;
  /** False while the text is not a length (the caller keeps its action disabled). */
  onValidity?: (valid: boolean) => void;
  /** A usual length exists (a sight's category, a restaurant's or cafe's). */
  hasDefault?: boolean;
  /** Its number, when known, shown in the pill and in the field while it is used. */
  defaultMinutes?: number | null;
  defaultLabel?: string;
  testID?: string;
}) {
  const shownDefault = defaultMinutes !== null ? String(defaultMinutes) : "";
  // What the user typed; dropped when the length is changed from outside (a pill, a new place).
  const [draft, setDraft] = useState<string | null>(null);
  const draftParsed = draft !== null ? parseMinutes(draft) : null;
  const showDraft = draft !== null && (draftParsed === null || draftParsed === minutes);
  const text = showDraft ? draft : minutes !== null ? String(minutes) : shownDefault;
  const invalid = showDraft && text.trim().length > 0 && draftParsed === null;

  const edit = (t: string) => {
    setDraft(t);
    const parsed = parseMinutes(t);
    onValidity?.(parsed !== null);
    if (parsed !== null) onChange(parsed);
  };

  const usingDefault = hasDefault && minutes === null;
  const parsed = parseMinutes(text);
  const suffix = parsed !== null && parsed >= 60 ? formatMinutes(parsed) : "min";
  const pillLabel =
    defaultLabel ??
    (defaultMinutes !== null ? `Default · ${formatMinutes(defaultMinutes)}` : "Default");
  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <View style={styles.field}>
          <TextField
            label={label}
            testID={testID}
            accessibilityLabel={`${label}, in minutes`}
            hint={undefined}
            value={text}
            onChangeText={edit}
            keyboardType="numbers-and-punctuation"
            placeholder={hasDefault ? "Default" : "Minutes"}
            autoCorrect={false}
            selectTextOnFocus
            suffix={suffix}
            quiet={usingDefault}
            error={invalid ? "enter minutes (1 to 1440) or hours and minutes, like 1h30." : null}
          />
        </View>
        {hasDefault ? (
          <Chip
            label={pillLabel}
            selected={usingDefault}
            testID={`${testID}-default`}
            onPress={() => {
              setDraft(null);
              onValidity?.(true);
              onChange(null);
            }}
          />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {},
  // The pill sits level with the box, below the small label.
  row: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm },
  field: { flex: 1 },
});
