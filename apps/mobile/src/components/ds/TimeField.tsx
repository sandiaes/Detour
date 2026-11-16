import { useEffect, useRef, useState } from "react";
import { Keyboard, PanResponder, StyleSheet, Text, View } from "react-native";

import { clockFrom, parseClock } from "../../domain/clock";
import { border, colors, radius, size as sizes, spacing, type, weight } from "../../theme";
import { TextField } from "./fields";

// A time of day (docs/design.md, "Time field"): typed like "14:30", or turned like a roulette.
// "Pick" opens two wheels, hours and minutes; dragging a wheel UP makes the time later and
// dragging it DOWN makes it earlier (owner request, 2026-11-16, reversing the one of 2026-11-15). Tapping the row above or below the
// middle moves one step. Hours turn by 1, minutes by 5, each wrapping round. The typed field and
// the wheels always show the same time.

const ROW = sizes.controlSm;
const FALLBACK = "09:00";
const mod = (n: number, m: number) => ((n % m) + m) % m;

/** The value a wheel shows after a drag of `dy` px from `from`: up (negative) is later. */
export function wheelValue(from: number, dy: number, step: number, size: number, row: number) {
  return mod(from - Math.round(dy / row) * step, size);
}

function Wheel({
  value,
  step,
  size,
  label,
  onChange,
  testID,
}: {
  value: number;
  step: number;
  size: number;
  label: string;
  onChange: (value: number) => void;
  testID: string;
}) {
  const latest = useRef({ value, step, size, onChange });
  useEffect(() => {
    latest.current = { value, step, size, onChange };
  });
  const from = useRef(value);
  // The handlers read `latest` only when a gesture happens, never while rendering.
  // eslint-disable-next-line react-hooks/refs
  const [pan] = useState(() =>
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      // A wheel inside a scrolling page keeps the gesture until the finger is lifted.
      onPanResponderTerminationRequest: () => false,
      onShouldBlockNativeResponder: () => true,
      onPanResponderGrant: () => {
        from.current = latest.current.value;
      },
      onPanResponderMove: (_e, g) => {
        const { step: s, size: n, onChange: change, value: now } = latest.current;
        // Up is later, down is earlier: the wheel turns like a drum under the finger.
        const next = wheelValue(from.current, g.dy, s, n, ROW);
        if (next !== now) change(next);
      },
      onPanResponderRelease: (e, g) => {
        if (Math.abs(g.dx) > 4 || Math.abs(g.dy) > 4) return;
        const { step: s, size: n, onChange: change, value: now } = latest.current;
        const y = e.nativeEvent.locationY;
        if (y < ROW) change(mod(now - s, n));
        else if (y > ROW * 2) change(mod(now + s, n));
      },
    }),
  );
  const text = (n: number) => String(mod(n, size)).padStart(2, "0");
  return (
    <View
      {...pan.panHandlers}
      style={styles.wheel}
      accessible
      accessibilityRole="adjustable"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max: size - 1, now: value, text: text(value) }}
      accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
      onAccessibilityAction={(e) => {
        const by = e.nativeEvent.actionName === "increment" ? step : -step;
        onChange(mod(value + by, size));
      }}
      testID={testID}
    >
      <View style={styles.cell}>
        <Text style={styles.near}>{text(value - step)}</Text>
      </View>
      <View style={styles.cell}>
        <Text style={styles.now}>{text(value)}</Text>
      </View>
      <View style={styles.cell}>
        <Text style={styles.near}>{text(value + step)}</Text>
      </View>
    </View>
  );
}

export function TimeField({
  label = "Start time",
  value,
  onChange,
  error,
  hint = "24-hour, like 14:30. Pick turns a roulette.",
  testID = "time",
}: {
  label?: string;
  /** "HH:MM" as typed; may be empty or not yet a time. */
  value: string;
  onChange: (text: string) => void;
  error?: string | null;
  hint?: string | null;
  testID?: string;
}) {
  const [open, setOpen] = useState(false);
  const clock = parseClock(value) ?? FALLBACK;
  const hours = Number(clock.slice(0, 2));
  const minutes = Number(clock.slice(3, 5));
  const wrongTime = value.trim().length > 0 && parseClock(value) === null;
  return (
    <View style={styles.wrap}>
      <TextField
        label={label}
        icon="clock"
        value={value}
        onChangeText={onChange}
        keyboardType="numbers-and-punctuation"
        autoCorrect={false}
        testID={testID}
        hint={error ? undefined : hint}
        error={error ?? (wrongTime ? "use hours and minutes, like 09:30" : null)}
        suffixAction={{
          label: "Pick",
          accessibilityLabel: open ? "Close the time roulette" : "Open the time roulette",
          onPress: () => {
            Keyboard.dismiss();
            setOpen((o) => !o);
          },
          testID: `${testID}-pick`,
        }}
      />
      {open ? (
        <View style={styles.panel} testID={`${testID}-roulette`}>
          <View style={styles.band} pointerEvents="none" />
          <Wheel
            value={hours}
            step={1}
            size={24}
            label="Hours"
            onChange={(h) => onChange(clockFrom(h, minutes))}
            testID={`${testID}-hours`}
          />
          <Text style={styles.colon}>:</Text>
          <Wheel
            value={minutes}
            step={5}
            size={60}
            label="Minutes"
            onChange={(m) => onChange(clockFrom(hours, m))}
            testID={`${testID}-minutes`}
          />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  // Like a drop-down's list: a bordered surface that opens under the field.
  panel: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    borderRadius: radius.md,
    borderWidth: border.hairline,
    borderColor: colors.outline,
    backgroundColor: colors.surface,
    overflow: "hidden",
  },
  // The chosen time sits in the middle row, on a soft band.
  band: {
    position: "absolute",
    left: spacing.md,
    right: spacing.md,
    top: ROW,
    height: ROW,
    borderRadius: radius.sm,
    backgroundColor: colors.selectedSoft,
  },
  wheel: { width: 72, height: ROW * 3, alignItems: "center" },
  cell: { height: ROW, alignSelf: "stretch", alignItems: "center", justifyContent: "center" },
  near: { ...type.label, color: colors.muted },
  now: { ...type.headline, fontWeight: weight.semibold, color: colors.text },
  colon: { ...type.headline, color: colors.text },
});
