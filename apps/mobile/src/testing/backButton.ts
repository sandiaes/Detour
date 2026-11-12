import { BackHandler } from "react-native";

/** Records the app's hardware-back handler, so a test can press Android's back button. */
export function captureBackButton() {
  const handlers: ((...args: never[]) => boolean | null | undefined)[] = [];
  jest.spyOn(BackHandler, "addEventListener").mockImplementation((_event, handler) => {
    handlers.push(handler);
    return {
      remove: () => {
        const at = handlers.indexOf(handler);
        if (at >= 0) handlers.splice(at, 1);
      },
    };
  });
  return {
    /** True if the app handled the press; false means Android would leave the app. */
    press: (): boolean =>
      Boolean((handlers[handlers.length - 1] as (() => boolean) | undefined)?.()),
  };
}
