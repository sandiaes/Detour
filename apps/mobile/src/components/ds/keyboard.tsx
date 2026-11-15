import { type ComponentRef, type RefObject, useEffect, useRef, useState } from "react";
import {
  Dimensions,
  Keyboard,
  type KeyboardEvent,
  ScrollView,
  type ScrollViewProps,
  TextInput,
  View,
} from "react-native";

import { spacing } from "../../theme";

// The on-screen keyboard must never hide the field being typed in. On Android with an edge-to-edge
// window the system does not shrink the app for the keyboard, so the app does it: `useKeyboardOverlap`
// measures how far the keyboard reaches into a view and the view pads that much, and
// `KeyboardScrollView` scrolls the field in focus above it. Measured, not assumed: where the system
// already resized the window the overlap is zero and nothing is added twice.

/** How much of the view behind `ref` (a `useRef` of the caller's) the keyboard covers (0 when it is closed). Put `ref` on a
 * view whose own frame does not change when it pads (a flex: 1 wrapper) and pad it by `overlap`. */
export function useKeyboardOverlap(ref: RefObject<ComponentRef<typeof View> | null>): {
  overlap: number;
  visible: boolean;
} {
  const [overlap, setOverlap] = useState(0);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const show = Keyboard.addListener("keyboardDidShow", (e: KeyboardEvent) => {
      setVisible(true);
      const top = e.endCoordinates.screenY;
      const node = ref.current;
      if (!node || typeof node.measureInWindow !== "function") {
        setOverlap(e.endCoordinates.height);
        return;
      }
      node.measureInWindow((_x, y, _w, height) =>
        setOverlap(Math.max(0, Math.round(y + height - top))),
      );
    });
    const hide = Keyboard.addListener("keyboardDidHide", () => {
      setVisible(false);
      setOverlap(0);
    });
    return () => {
      show.remove();
      hide.remove();
    };
  }, [ref]);
  return { overlap, visible };
}

/**
 * A `ScrollView` for screens with input fields: taps on buttons still work while the keyboard is
 * open, and when the keyboard opens the field in focus is scrolled to just above it.
 */
export function KeyboardScrollView(props: ScrollViewProps) {
  const scroller = useRef<ComponentRef<typeof ScrollView>>(null);
  const offset = useRef(0);
  useEffect(() => {
    const show = Keyboard.addListener("keyboardDidShow", (e: KeyboardEvent) => {
      // After the screen has made room for the keyboard.
      const timer = setTimeout(() => {
        const input = TextInput.State.currentlyFocusedInput?.();
        if (!input || typeof input.measureInWindow !== "function") return;
        const keyboardTop =
          e.endCoordinates.screenY || Dimensions.get("window").height - e.endCoordinates.height;
        input.measureInWindow((_x, y, _w, height) => {
          const hidden = y + height + spacing.lg - keyboardTop;
          if (hidden > 0)
            scroller.current?.scrollTo({ y: offset.current + hidden, animated: true });
        });
      }, 120);
      return () => clearTimeout(timer);
    });
    return () => show.remove();
  }, []);
  return (
    <ScrollView
      keyboardShouldPersistTaps="handled"
      scrollEventThrottle={16}
      {...props}
      ref={scroller}
      onScroll={(e) => {
        offset.current = e.nativeEvent.contentOffset.y;
        props.onScroll?.(e);
      }}
    />
  );
}
