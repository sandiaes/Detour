import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Button } from "../Button";
import { TOUCH, colors, radius, spacing, type } from "../../theme";
import { formatDate, parseIsoDate } from "../../util/format";
import { IconButton, Sheet } from "./primitives";

// A month calendar for choosing a date (the new-trip screen's start date). Drawn in JavaScript on
// purpose: the system date picker is a native module that Detour does not add (CLAUDE.md, "No
// Android-only native dependency without an ADR"). Weeks start on Monday; every day is a 48 dp
// button that says its full date; the chosen day and today are told in words as well as shape.

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const WEEKDAY_HEADS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

const pad = (n: number) => String(n).padStart(2, "0");
export const toIso = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

/** The weeks of a month (month 0 to 11), Monday first; a null is a blank cell. */
export function monthGrid(year: number, month: number): (string | null)[][] {
  const first = new Date(Date.UTC(year, month, 1)).getUTCDay(); // 0 = Sunday
  const lead = (first + 6) % 7;
  const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const cells: (string | null)[] = [
    ...Array<null>(lead).fill(null),
    ...Array.from({ length: days }, (_, i) => toIso(year, month, i + 1)),
  ];
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

export function CalendarSheet({
  visible,
  title = "Start date",
  value,
  today,
  onPick,
  onClear,
  onClose,
}: {
  visible: boolean;
  title?: string;
  /** The chosen date, ISO, or empty. */
  value: string;
  /** Today's date, ISO: ringed, and where an empty value starts. */
  today: string;
  onPick: (iso: string) => void;
  /** Removes the date again (the start date is optional). */
  onClear: () => void;
  onClose: () => void;
}) {
  const start = parseIsoDate(value) ?? parseIsoDate(today) ?? new Date();
  const [view, setView] = useState({ y: start.getUTCFullYear(), m: start.getUTCMonth() });
  const step = (by: number) =>
    setView(({ y, m }) => {
      const n = new Date(Date.UTC(y, m + by, 1));
      return { y: n.getUTCFullYear(), m: n.getUTCMonth() };
    });
  const weeks = monthGrid(view.y, view.m);
  return (
    <Sheet visible={visible} title={title} onClose={onClose}>
      <View style={styles.nav}>
        <IconButton icon="back" label="Previous month" onPress={() => step(-1)} testID="cal-prev" />
        <Text
          accessibilityRole="header"
          accessibilityLiveRegion="polite"
          style={styles.month}
          testID="cal-month"
        >
          {MONTH_NAMES[view.m]} {view.y}
        </Text>
        <IconButton
          icon="chevronRight"
          label="Next month"
          onPress={() => step(1)}
          testID="cal-next"
        />
      </View>
      <View style={styles.week} accessible={false} importantForAccessibility="no-hide-descendants">
        {WEEKDAY_HEADS.map((d) => (
          <Text key={d} style={styles.head}>
            {d}
          </Text>
        ))}
      </View>
      {weeks.map((week, i) => (
        <View key={i} style={styles.week}>
          {week.map((iso, j) => {
            if (!iso) return <View key={j} style={styles.cell} />;
            const chosen = iso === value;
            const isToday = iso === today;
            return (
              <Pressable
                key={iso}
                accessibilityRole="button"
                accessibilityLabel={`${formatDate(iso)}${isToday ? ", today" : ""}`}
                accessibilityState={{ selected: chosen }}
                onPress={() => onPick(iso)}
                style={styles.cell}
                testID={`cal-${iso}`}
              >
                <View style={[styles.day, isToday && styles.today, chosen && styles.chosen]}>
                  <Text style={[styles.dayText, chosen && styles.chosenText]}>
                    {Number(iso.slice(8))}
                  </Text>
                </View>
              </Pressable>
            );
          })}
        </View>
      ))}
      {value ? (
        <View style={styles.clear}>
          <Button label="Clear the date" variant="quiet" onPress={onClear} testID="cal-clear" />
        </View>
      ) : null}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  clear: { alignItems: "center", paddingTop: spacing.sm },
  nav: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  month: { ...type.heading, color: colors.text },
  week: { flexDirection: "row" },
  head: {
    flex: 1,
    textAlign: "center",
    ...type.caption,
    fontWeight: "600",
    color: colors.muted,
    paddingVertical: spacing.xs,
  },
  cell: { flex: 1, minHeight: TOUCH, alignItems: "center", justifyContent: "center" },
  day: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  today: { borderWidth: 1.5, borderColor: colors.outline, borderRadius: radius.pill },
  chosen: { backgroundColor: colors.ink, borderColor: colors.ink },
  dayText: { ...type.small, color: colors.text },
  chosenText: { color: colors.onPrimary, fontWeight: "700" },
});
