import { type ReactNode, useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { colors, layout, radius, size as sizes, spacing, type, weight } from "../../theme";
import { Button } from "./Button";
import { Icon, type IconName } from "./Icon";
import { Badge } from "./primitives";

// States (docs/design.md, "States"). One look for loading, empty, error, waking and planned
// screens: a mark in a soft circle, a short title, a sentence and at most one action. `fill` centres
// it in the space a screen has; `inline` puts it in the flow of a list or a sheet. Small progress
// inside a form is an `InlineStatus`; a message above content is a `Notice`.

export type StateKind = "loading" | "empty" | "error" | "waking" | "planned";

const KIND_ICON: Record<Exclude<StateKind, "loading" | "waking">, IconName> = {
  empty: "info",
  error: "alert",
  planned: "info",
};

export function StateView({
  kind,
  title,
  text,
  icon,
  action,
  layout: placement = "fill",
  badge,
  children,
  live = false,
  accessibleSummary,
  testID,
}: {
  kind: StateKind;
  title?: string;
  text?: string;
  icon?: IconName;
  action?: { label: string; onPress: () => void; variant?: "primary" | "secondary" };
  layout?: "fill" | "inline";
  /** A word under the text ("Not built yet"). */
  badge?: string;
  /** Extra content under the text (the Documents tab's four kinds). */
  children?: ReactNode;
  /** Announce changes (loading and errors). */
  live?: boolean;
  /** Read the whole state as one phrase (a planned feature). */
  accessibleSummary?: string;
  testID?: string;
}) {
  const spinner = kind === "loading" || kind === "waking";
  const mark = spinner ? null : (icon ?? KIND_ICON[kind]);
  return (
    <View
      style={[styles.state, placement === "fill" ? styles.fill : styles.inline]}
      accessibilityLiveRegion={live ? "polite" : undefined}
      accessible={accessibleSummary !== undefined || undefined}
      accessibilityLabel={accessibleSummary}
      testID={testID}
    >
      {spinner ? (
        <ActivityIndicator size="small" color={colors.primary} />
      ) : mark ? (
        <View style={[styles.mark, kind === "error" && styles.markError]}>
          <Icon name={mark} size="md" color={kind === "error" ? colors.danger : colors.primary} />
        </View>
      ) : null}
      {title ? (
        <Text
          style={styles.title}
          accessibilityRole={placement === "inline" ? "header" : undefined}
        >
          {title}
        </Text>
      ) : null}
      {text ? <Text style={styles.text}>{text}</Text> : null}
      {badge ? <Badge label={badge} /> : null}
      {children}
      {action ? (
        <Button
          label={action.label}
          variant={action.variant ?? "secondary"}
          onPress={action.onPress}
        />
      ) : null}
    </View>
  );
}

export function LoadingState({
  text,
  layout: placement,
}: {
  text: string;
  layout?: "fill" | "inline";
}) {
  return <StateView kind="loading" text={text} live layout={placement} accessibleSummary={text} />;
}

/** The cold start of the free host (ADR 005): a calm explanation and a running count. */
export function WakingServer() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <View style={[styles.state, styles.fill]}>
      <ActivityIndicator size="small" color={colors.primary} />
      <View accessibilityLiveRegion="polite" accessible style={styles.group}>
        <Text style={styles.title}>Waking the server</Text>
        <Text style={styles.text}>
          The free host sleeps when it has been idle. The first request can take about a minute.
          Nothing is wrong, and your saved trips stay available below once they load.
        </Text>
      </View>
      {/* Outside the live region, so a screen reader is not interrupted every second. */}
      <Text style={styles.meta}>Waiting {seconds} s</Text>
    </View>
  );
}

export function EmptyState({
  title,
  text,
  action,
  layout: placement,
  icon,
}: {
  title: string;
  text: string;
  action?: { label: string; onPress: () => void };
  layout?: "fill" | "inline";
  icon?: IconName;
}) {
  return (
    <StateView
      kind="empty"
      title={title}
      text={text}
      action={action}
      layout={placement}
      icon={icon}
    />
  );
}

export function ErrorState({
  title = "Something went wrong",
  text,
  onRetry,
}: {
  title?: string;
  text: string;
  onRetry?: () => void;
}) {
  return (
    <StateView
      kind="error"
      title={title}
      text={text}
      live
      action={onRetry ? { label: "Try again", onPress: onRetry } : undefined}
    />
  );
}

/** Says plainly that a part of the design is not built yet, and what it will do. */
export function PlannedFeature({
  icon,
  title,
  text,
  testID,
}: {
  icon: IconName;
  title: string;
  text: string;
  testID?: string;
}) {
  return (
    <StateView
      kind="planned"
      layout="inline"
      icon={icon}
      title={title}
      text={text}
      badge="Not built yet"
      accessibleSummary={`${title}. ${text}`}
      testID={testID}
    />
  );
}

/** Small progress or an answer inside a form: "Searching…", "Reading the plan…". */
export function InlineStatus({
  text,
  busy = false,
  testID,
}: {
  text: string;
  busy?: boolean;
  testID?: string;
}) {
  return (
    <View style={styles.inlineStatus} accessibilityLiveRegion="polite" testID={testID}>
      {busy ? <ActivityIndicator size="small" color={colors.muted} /> : null}
      <Text style={styles.inlineText}>{text}</Text>
    </View>
  );
}

// ---- notices -------------------------------------------------------------------------------------

export type NoticeTone = "info" | "warning" | "error" | "success";

/** Tone is carried by the label word and the icon as well as the colour. */
const TONE_LABEL: Record<NoticeTone, string> = {
  info: "Note",
  warning: "Offline",
  error: "Problem",
  success: "Done",
};
const TONE_ICON: Record<NoticeTone, IconName> = {
  info: "info",
  warning: "alert",
  error: "alert",
  success: "check",
};

/** A message above or among content: offline, a problem, a note. It has no outer margin of its own;
 * `inset` gives it the screen gutter where its parent has none. */
export function Notice({
  tone,
  label,
  children,
  action,
  inset = false,
}: {
  tone: NoticeTone;
  label?: string;
  children: ReactNode;
  action?: { label: string; onPress: () => void };
  inset?: boolean;
}) {
  const fg =
    tone === "warning"
      ? colors.warningText
      : tone === "error"
        ? colors.errorText
        : tone === "success"
          ? colors.primary
          : colors.muted;
  return (
    <View
      style={[
        styles.notice,
        tone === "warning" && styles.noticeWarning,
        tone === "error" && styles.noticeError,
        tone === "success" && styles.noticeSuccess,
        tone === "info" && styles.noticeInfo,
        inset && styles.noticeInset,
      ]}
      accessibilityLiveRegion="polite"
    >
      <View style={styles.noticeRow}>
        <Icon name={TONE_ICON[tone]} size="sm" color={fg} />
        <Text style={styles.noticeText}>
          <Text style={styles.noticeLabel}>{label ?? TONE_LABEL[tone]}. </Text>
          {children}
        </Text>
      </View>
      {action ? (
        <View style={styles.noticeAction}>
          <Button label={action.label} variant="ghost" size="sm" onPress={action.onPress} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  state: { alignItems: "center", gap: spacing.sm },
  fill: { flex: 1, justifyContent: "center", padding: spacing.xl },
  inline: { paddingVertical: spacing.xl, paddingHorizontal: spacing.lg },
  group: { alignItems: "center", gap: spacing.sm },
  mark: {
    width: sizes.stateMark,
    height: sizes.stateMark,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.primarySoft,
    marginBottom: spacing.xs,
  },
  markError: { backgroundColor: colors.dangerSoft },
  title: { ...type.headline, color: colors.text, textAlign: "center" },
  text: { ...type.label, color: colors.muted, textAlign: "center", maxWidth: 360 },
  meta: { ...type.caption, color: colors.muted },
  inlineStatus: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  inlineText: { ...type.caption, color: colors.muted, flexShrink: 1 },

  notice: { padding: spacing.md, gap: spacing.sm, borderRadius: radius.sm },
  noticeInset: { marginHorizontal: layout.gutter },
  noticeInfo: { backgroundColor: colors.surfaceMuted },
  noticeWarning: { backgroundColor: colors.warning },
  noticeError: { backgroundColor: colors.error },
  noticeSuccess: { backgroundColor: colors.primarySoft },
  noticeRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  noticeText: { ...type.label, color: colors.text, flex: 1 },
  noticeLabel: { fontWeight: weight.bold },
  noticeAction: { paddingLeft: spacing.lg + spacing.sm },
});
