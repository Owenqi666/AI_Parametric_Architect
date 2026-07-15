import type { CSSProperties } from "react";
import type { DetachedFloorPlanProposal, PreviewRoom } from "@/lib/proposal-preview/types";
import styles from "./design-studio.module.css";

interface ProposalPlanProps {
  readonly proposal: DetachedFloorPlanProposal;
  readonly selectedPlanId: string | null;
  readonly onSelect: (planId: string) => void;
}

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

function roomCenter(room: PreviewRoom, boundaryHeight: number): readonly [number, number] {
  return [room.x + room.width / 2, boundaryHeight - room.y - room.height / 2];
}

export function ProposalPlan({ proposal, selectedPlanId, onSelect }: ProposalPlanProps) {
  const rooms = new Map(proposal.rooms.map((room) => [room.plan_id, room]));
  const { width, height } = proposal.boundary;

  return (
    <div className={styles.planFrame}>
      <div className={styles.detachedWatermark} aria-hidden="true">
        Detached planning sandbox
      </div>
      <div
        className={styles.planBoundary}
        style={{ "--plan-ratio": `${width} / ${height}` } as CSSProperties}
        aria-label={`Detached proposal boundary, ${width} by ${height} metres`}
      >
        <svg
          className={styles.constraintLayer}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {proposal.spatial_constraints.map((constraint, index) => {
            const source = rooms.get(constraint.source_plan_id);
            const target = rooms.get(constraint.target_plan_id);
            if (!source || !target) return null;
            const [x1, y1] = roomCenter(source, height);
            const [x2, y2] = roomCenter(target, height);
            return (
              <line
                key={`${constraint.source_plan_id}-${constraint.relation}-${constraint.target_plan_id}-${index}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                vectorEffect="non-scaling-stroke"
                data-relation={constraint.relation}
              />
            );
          })}
        </svg>

        {proposal.rooms.map((room, index) => {
          const roomStyle = {
            left: `${(room.x / width) * 100}%`,
            top: `${((height - room.y - room.height) / height) * 100}%`,
            width: `${(room.width / width) * 100}%`,
            height: `${(room.height / height) * 100}%`,
            "--room-index": index,
          } as CSSProperties;
          return (
            <button
              key={room.plan_id}
              type="button"
              className={styles.planRoom}
              data-selected={selectedPlanId === room.plan_id}
              style={roomStyle}
              aria-pressed={selectedPlanId === room.plan_id}
              aria-label={`${ROOM_LABELS[room.room_type] ?? room.room_type}, ${(room.width * room.height).toFixed(1)} square metres, ${room.orientation} orientation`}
              onClick={() => onSelect(room.plan_id)}
            >
              <span className={styles.roomIndex}>{String(index + 1).padStart(2, "0")}</span>
              <span className={styles.roomName}>{ROOM_LABELS[room.room_type] ?? room.room_type}</span>
              <span className={styles.roomArea}>{(room.width * room.height).toFixed(1)} m²</span>
              <span className={styles.roomOrientation}>{room.orientation}</span>
            </button>
          );
        })}
        <span className={styles.boundaryWidth}>{width} m</span>
        <span className={styles.boundaryHeight}>{height} m</span>
      </div>

      <div className={styles.compass} aria-label="Plan orientation: north is up">
        <span>N</span>
        <i aria-hidden="true" />
        <small>W</small>
        <small>E</small>
        <b>S</b>
      </div>
    </div>
  );
}

export function roomLabel(roomType: string): string {
  return ROOM_LABELS[roomType] ?? roomType.replaceAll("_", " ");
}
