import type { RenderObject } from "@/lib/render-ir/types";

interface EntityListProps {
  readonly objects: readonly RenderObject[];
  readonly visibleFloorId: string | null;
  readonly selectedId: string | null;
  readonly onSelect: (entityId: string) => void;
}

const TYPE_LABELS: Record<RenderObject["entity_type"], string> = {
  room: "Room",
  wall: "Wall",
  door: "Door",
  window: "Window",
};

export function EntityList({
  objects,
  visibleFloorId,
  selectedId,
  onSelect,
}: EntityListProps) {
  const visible = objects.filter(
    (item) => visibleFloorId === null || item.floor_id === visibleFloorId,
  );

  return (
    <ul className="entity-list" aria-label="Visible model entities">
      {visible.map((item) => (
        <li key={item.entity_id}>
          <button
            type="button"
            className="entity-row"
            data-selected={selectedId === item.entity_id}
            aria-pressed={selectedId === item.entity_id}
            onClick={() => onSelect(item.entity_id)}
          >
            <span className={`entity-mark entity-mark--${item.entity_type}`} aria-hidden="true" />
            <span className="entity-copy">
              <span className="entity-name">{item.name}</span>
              <span className="entity-id">{item.entity_id}</span>
            </span>
            <span className="entity-type">{TYPE_LABELS[item.entity_type]}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
