import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { hoursText, minutesFromHours } from "../../domain/clock";
import { parseMinutes } from "../../domain/duration";
import { spacing } from "../../theme";
import { formatMinutes } from "../../util/format";
import { TextField } from "./fields";
import { Chip } from "./primitives";

// How long to stay: one free field (minutes, "1h30", or hours with the unit switched to h) and,
// where the place has a usual length, a pill that goes back to it. The unit at the end of the
// field is pressed to switch between min and h. Replaces the fixed 30/60/90 pills (owner request,
// 2026-11-15).

type Unit = "min" | "h";

/** What was typed, as minutes, in the unit the field shows. "1h30" always works. */
function parseLength(text: string, unit: Unit): number | null {
  if (unit === "h" && /^[\d.,]+$/.test(text.trim())) return minutesFromHours(text);
  return parseMinutes(text);
}

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
  const [unit, setUnit] = useState<Unit>("min");
  const inUnit = (m: number) => (unit === "h" ? hoursText(m) : String(m));
  const shownDefault = defaultMinutes !== null ? inUnit(defaultMinutes) : "";
  // What the user typed; dropped when the length is changed from outside (a pill, a new place).
  const [draft, setDraft] = useState<string | null>(null);
  // While the field is first entered its text is selected so the first key replaces it. The
  // selection is let go at the first key (or tap), so later keys are never swallowed by it.
  const [selection, setSelection] = useState<{ start: number; end: number } | undefined>();
  const draftParsed = draft !== null ? parseLength(draft, unit) : null;
  const showDraft = draft !== null && (draftParsed === null || draftParsed === minutes);
  const text = showDraft ? draft : minutes !== null ? inUnit(minutes) : shownDefault;
  const invalid = showDraft && text.trim().length > 0 && draftParsed === null;

  const edit = (t: string) => {
    setSelection(undefined);
    setDraft(t);
    const parsed = parseLength(t, unit);
    onValidity?.(parsed !== null);
    if (parsed !== null) onChange(parsed);
  };

  const switchUnit = () => {
    setDraft(null);
    setSelection(undefined);
    setUnit(unit === "min" ? "h" : "min");
    onValidity?.(true);
  };

  const usingDefault = hasDefault && minutes === null;
  const pillLabel =
    defaultLabel ??
    (defaultMinutes !== null ? `Default · ${formatMinutes(defaultMinutes)}` : "Default");
  const unitName = unit === "min" ? "minutes" : "hours";
  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <View style={styles.field}>
          <TextField
            label={label}
            testID={testID}
            accessibilityLabel={`${label}, in ${unitName}`}
            hint={undefined}
            value={text}
            onChangeText={edit}
            keyboardType="numbers-and-punctuation"
            placeholder={hasDefault ? "Default" : unit === "min" ? "Minutes" : "Hours"}
            autoCorrect={false}
            selection={selection}
            onFocus={() => setSelection({ start: 0, end: text.length })}
            onBlur={() => setSelection(undefined)}
            onSelectionChange={(e) => {
              // A tap that puts the cursor somewhere ends the "everything selected" state.
              const { start, end } = e.nativeEvent.selection;
              if (start === end) setSelection(undefined);
            }}
            suffixAction={{
              label: unit,
              accessibilityLabel: `Unit: ${unitName}. Switch to ${unit === "min" ? "hours" : "minutes"}`,
              onPress: switchUnit,
              testID: `${testID}-unit`,
            }}
            quiet={usingDefault}
            error={
              invalid
                ? unit === "h"
                  ? "enter hours (like 1.5), or hours and minutes, like 1h30."
                  : "enter minutes (1 to 1440) or hours and minutes, like 1h30."
                : null
            }
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
