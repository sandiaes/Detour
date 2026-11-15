import type { Day } from "@detour/shared";
import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { layout } from "../theme";
import { formatClock, formatDayLabel, formatMinutes } from "../util/format";
import { Button, ChoiceRow, SelectField, TextField } from "./ds";
import { DurationField } from "./ds/DurationField";

// Putting a place on a day at a time the user picks, with no proposal. It is the only way to fill
// an empty trip (nothing to recalculate), and an option on a planned one.

/** Where a day's start time suggestion comes from for a restaurant or café: the midday gap. */
export const EATING_START = "13:00";

export type ChosenSlot = {
  day: number;
  /** "HH:MM" */
  time: string;
  minutes: number;
  /** Where in the day, so the day stays in time order. */
  position: number;
};

/** "9:30" or "09:30" -> "09:30"; null when it is not a time of day. */
export function parseClock(text: string): string | null {
  const m = /^(\d{1,2})[:.](\d{2})$/.exec(text.trim());
  if (!m) return null;
  const [h, min] = [Number(m[1]), Number(m[2])];
  if (h > 23 || min > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

/** The 1-based position that keeps a day in time order for a new item at `time`. */
export function positionFor(day: Day | undefined, time: string): number {
  const earlier = (day?.items ?? []).filter(
    (i) => i.start_time && (formatClock(i.start_time) ?? "") <= time,
  ).length;
  return earlier + 1;
}

export function ChooseSlot({
  days,
  startDate,
  defaultTime = "10:00",
  minutes: fixedMinutes,
  defaultMinutes = null,
  name,
  working,
  disabled,
  onSubmit,
}: {
  days: Day[];
  startDate: string | null;
  /** The start time suggested first (the user can change it). */
  defaultTime?: string;
  /** How long the place gets, when the screen already asked; otherwise it is asked here. */
  minutes: number | null;
  /** The usual length offered by the pill when it is asked here (a restaurant's or cafe's). */
  defaultMinutes?: number | null;
  name: string;
  working: boolean;
  disabled: boolean;
  onSubmit: (slot: ChosenSlot) => void;
}) {
  const [day, setDay] = useState(days[0]?.day_index ?? 1);
  const [picking, setPicking] = useState(false);
  const [timeText, setTimeText] = useState(defaultTime);
  // null: the usual length. Typed lengths replace it.
  const [ownMinutes, setOwnMinutes] = useState<number | null>(null);
  const [ownValid, setOwnValid] = useState(true);
  const time = parseClock(timeText);
  const minutes = fixedMinutes ?? ownMinutes ?? defaultMinutes ?? 60;
  const canSubmit = time !== null && (fixedMinutes !== null || ownValid);

  return (
    <View style={styles.gap} testID="choose-slot">
      <SelectField
        label="Day"
        placeholder="Choose a day"
        icon="calendar"
        value={formatDayLabel(startDate, day)}
        open={picking}
        onToggle={() => setPicking((o) => !o)}
        testID="slot-day"
      >
        {days.map((d) => (
          <ChoiceRow
            key={d.day_index}
            title={formatDayLabel(startDate, d.day_index)}
            meta={d.items.length === 0 ? "Nothing planned yet" : `${d.items.length} planned`}
            selected={day === d.day_index}
            testID={`slot-day-${d.day_index}`}
            onPress={() => {
              setDay(d.day_index);
              setPicking(false);
            }}
          />
        ))}
      </SelectField>
      <TextField
        label="Start time"
        icon="clock"
        value={timeText}
        onChangeText={setTimeText}
        keyboardType="numbers-and-punctuation"
        autoCorrect={false}
        testID="slot-time"
        hint="24-hour, like 14:30"
        error={timeText.trim() && time === null ? "use hours and minutes, like 09:30" : null}
      />
      {fixedMinutes === null ? (
        <DurationField
          minutes={ownMinutes}
          onChange={setOwnMinutes}
          onValidity={setOwnValid}
          hasDefault={defaultMinutes !== null}
          defaultMinutes={defaultMinutes}
          defaultLabel="Default"
          testID="slot-length"
        />
      ) : null}
      <Button
        label={time ? `Add to day ${day} at ${time}` : "Add to the plan"}
        testID="add-at-time"
        fill
        disabled={disabled || !canSubmit}
        loading={working}
        hint={`Puts ${name || "it"} on day ${day} for ${formatMinutes(minutes)}. It is not moved by anything else.`}
        onPress={() =>
          time &&
          onSubmit({
            day,
            time,
            minutes,
            position: positionFor(
              days.find((d) => d.day_index === day),
              time,
            ),
          })
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  gap: { gap: layout.block },
});
