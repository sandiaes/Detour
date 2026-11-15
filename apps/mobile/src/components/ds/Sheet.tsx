import { type ComponentRef, type ReactNode, useRef } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { TOUCH, colors, layout, radius, shadow, spacing, type } from "../../theme";
import { Button } from "./Button";
import { useKeyboardOverlap } from "./keyboard";
import { IconButton } from "./primitives";

/** A sheet that slides up from the bottom: a white surface with 24 dp corners, a grabber, a title
 * and a close button. Tapping outside, Close or Android Back closes it. */
export function Sheet({
  visible,
  title,
  onClose,
  children,
}: {
  visible: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const insets = useSafeAreaInsets();
  // The keyboard lifts the sheet, so a field in it is never covered.
  const root = useRef<ComponentRef<typeof View>>(null);
  const keyboard = useKeyboardOverlap(root);
  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <View ref={root} style={[styles.root, { paddingBottom: keyboard.overlap }]}>
        <Pressable
          style={styles.backdrop}
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={onClose}
        />
        <View
          style={[
            styles.sheet,
            { paddingBottom: spacing.lg + (keyboard.visible ? 0 : insets.bottom) },
          ]}
        >
          <View style={styles.grabber} />
          <View style={styles.head}>
            <Text accessibilityRole="header" style={styles.title}>
              {title}
            </Text>
            <IconButton icon="close" label="Close" size="sm" onPress={onClose} />
          </View>
          {children}
        </View>
      </View>
    </Modal>
  );
}

/**
 * Asks before an action that cannot be undone (delete a trip, mark it as past, delete a document):
 * what will happen, a red confirming button and a way back. One pattern everywhere.
 */
export function ConfirmSheet({
  visible,
  title,
  message,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  busy = false,
  destructive = true,
  confirmTestID,
}: {
  visible: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
  destructive?: boolean;
  confirmTestID?: string;
}) {
  return (
    <Sheet visible={visible} title={title} onClose={onCancel}>
      <Text style={styles.message}>{message}</Text>
      <View style={styles.actions}>
        <Button
          label={confirmLabel}
          variant={destructive ? "destructive" : "primary"}
          fill
          loading={busy}
          disabled={busy}
          testID={confirmTestID}
          onPress={onConfirm}
        />
        <Button label={cancelLabel} variant="secondary" fill disabled={busy} onPress={onCancel} />
      </View>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFill, minHeight: TOUCH, backgroundColor: colors.backdrop },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: layout.gutter,
    gap: spacing.md,
    maxHeight: "92%",
    ...shadow.raised,
  },
  grabber: {
    alignSelf: "center",
    width: 36,
    height: 4,
    borderRadius: radius.pill,
    marginTop: spacing.sm,
    backgroundColor: colors.border,
  },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { ...type.headline, color: colors.text, flex: 1 },
  message: { ...type.body, color: colors.text },
  actions: { gap: spacing.sm },
});
