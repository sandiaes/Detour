import { Placeholder, Screen } from "../components/Screen";

export function CreateTripScreen() {
  return (
    <Screen title="Create Trip">
      <Placeholder
        phase="Phase 5"
        text="Choose a destination and the number of days to get itinerary proposals."
      />
    </Screen>
  );
}
