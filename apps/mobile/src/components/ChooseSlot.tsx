import type { Day } from "@detour/shared";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { MEAL_LABEL, MEALS, type Meal } from "../domain/restaurants";
import { colors, spacing, type } from "../theme";
import { formatClock, formatDayLabel, formatMinutes } from "../util/format";
import { Button } from "./Button";
import { Chip, Field } from "./ui";

// Putting a place on a day at a time the user picks, with no proposal. It is the only way to fill
// an empty trip (nothing to recalculate), and an option on a planned one.

export const SLOT_DURATIONS = [30, 60, 90, 120, 180] as const;
const MEAL_START: Record<Meal, string> = {
  breakfast: "09:00",
  lunch: "13:00",
  snack: "16:00",
  dinner: "20:00",
};

export type ChosenSlot = {
  day: number;
  /** "HH:MM" */
  time: string;
  minutes: number;
  meal: Meal | null;
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
  meal,
  minutes: fixedMinutes,
  name,
  working,
  disabled,
  onSubmit,
}: {
  days: Day[];
  startDate: string | null;
  /** Ask which meal (a restaurant) */
  meal: boolean;
  /** How long the place gets, when the screen already asked; otherwise it is asked here. */
  minutes: number | null;
  name: string;
  working: boolean;
  disabled: boolean;
  onSubmit: (slot: ChosenSlot) => void;
}) {
  const [day, setDay] = useState(days[0]?.day_index ?? 1);
  const [mealType, setMealType] = useState<Meal>("lunch");
  const [timeText, setTimeText] = useState(meal ? MEAL_START.lunch : "10:00");
  const [ownMinutes, setOwnMinutes] = useState(60);
  const time = parseClock(timeText);
  const minutes = fixedMinutes ?? ownMinutes;

  return (
    <View style={styles.gap} testID="choose-slot">
      <Text style={styles.label}>Day</Text>
      <View style={styles.row}>
        {days.map((d) => (
          <Chip
            key={d.day_index}
            label={formatDayLabel(startDate, d.day_index)}
            selected={day === d.day_index}
            onPress={() => setDay(d.day_index)}
            testID={`slot-day-${d.day_index}`}
          />
        ))}
      </View>
      {meal ? (
        <>
          <Text style={styles.label}>Meal</Text>
          <View style={styles.row}>
            {MEALS.map((m) => (
              <Chip
                key={m}
                label={MEAL_LABEL[m]}
                selected={mealType === m}
                onPress={() => {
                  setMealType(m);
                  setTimeText(MEAL_START[m]);
                }}
              />
            ))}
          </View>
        </>
      ) : null}
      <Field
        label="Start time"
        value={timeText}
        onChangeText={setTimeText}
        keyboardType="numbers-and-punctuation"
        autoCorrect={false}
        testID="slot-time"
        hint="Local time at the destination, 24-hour, for example 14:30."
        error={timeText.trim() && time === null ? "Use hours and minutes, like 09:30" : null}
      />
      {fixedMinutes === null ? (
        <>
          <Text style={styles.label}>How long</Text>
          <View style={styles.row}>
            {SLOT_DURATIONS.map((m) => (
              <Chip
                key={m}
                label={formatMinutes(m)}
                selected={ownMinutes === m}
                onPress={() => setOwnMinutes(m)}
              />
            ))}
          </View>
        </>
      ) : null}
      <Button
        label={time ? `Add to day ${day} at ${time}` : "Add to the plan"}
        testID="add-at-time"
        fill
        disabled={disabled || time === null}
        loading={working}
        hint={`Puts ${name || "it"} on day ${day} for ${formatMinutes(minutes)}. It is not moved by anything else.`}
        onPress={() =>
          time &&
          onSubmit({
            day,
            time,
            minutes,
            meal: meal ? mealType : null,
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
  gap: { gap: spacing.sm },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  label: { ...type.small, fontWeight: "700", color: colors.text },
});
