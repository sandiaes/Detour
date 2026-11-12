import { Button } from "../components/Button";
import { Placeholder, Screen } from "../components/Screen";

type Props = { onCreateTrip: () => void; onOpenItinerary: () => void };

export function TripsScreen({ onCreateTrip, onOpenItinerary }: Props) {
  return (
    <Screen title="Trips">
      <Placeholder phase="Phase 5" text="Your trips will be listed here." />
      <Button label="Create trip" onPress={onCreateTrip} />
      <Button label="Open itinerary" onPress={onOpenItinerary} />
    </Screen>
  );
}
