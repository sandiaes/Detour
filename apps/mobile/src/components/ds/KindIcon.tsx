import { type StopKind, isEatKind } from "../../domain/itinerary";
import { colors } from "../../theme";
import { Icon, type IconName, type IconSize } from "./Icon";

// The small icon that says what a place is, used wherever a place is listed (day list, place
// detail, search results, proposals): a fork and knife for a restaurant, a coffee cup for a café,
// a visitor at a landmark for an attraction. A word always sits beside it: the icon never carries
// the meaning alone.

const NAME: Record<StopKind, IconName> = {
  restaurant: "restaurant",
  cafe: "cafe",
  attraction: "sight",
  other: "pin",
};

export function KindIcon({
  kind,
  size = "xs",
  color,
}: {
  kind: StopKind;
  size?: IconSize;
  color?: string;
}) {
  return (
    <Icon
      name={NAME[kind]}
      size={size}
      color={color ?? (isEatKind(kind) ? colors.accentText : colors.primary)}
    />
  );
}

/** The kind of an imported place (the search results): a restaurant or café, else an attraction. */
export function placeKind(place: { kind: string; venue_type?: string | null }): StopKind {
  if (place.kind === "restaurant") return place.venue_type === "cafe" ? "cafe" : "restaurant";
  return place.kind === "attraction" ? "attraction" : "other";
}
