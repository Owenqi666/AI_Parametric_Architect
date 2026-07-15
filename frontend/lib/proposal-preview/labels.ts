const ROOM_LABELS: Readonly<Record<string, string>> = {
  bathroom: "Bathroom",
  bedroom: "Bedroom",
  dining: "Dining",
  dining_room: "Dining",
  kitchen: "Kitchen",
  living: "Living",
  living_room: "Living",
  office: "Office",
  storage: "Storage",
};

export function roomLabel(roomType: string): string {
  return ROOM_LABELS[roomType] ?? roomType.replaceAll("_", " ");
}
