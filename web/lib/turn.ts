// A photograph's TURN is degrees clockwise, applied after its own orientation
// tag, that puts it the right way up (migration 0021). A face box is x1,y1,x2,y2
// as fractions of the picture it was measured on, at the turn that picture had
// (faces.turn); drawn on the photo as it is shown now, it is turned by the
// difference.

export const TURNS = [0, 90, 180, 270] as const;

export function norm(deg: number): number {
  const d = ((Math.round(deg / 90) * 90) % 360 + 360) % 360;
  return d;
}

// a box measured at `from` degrees, as it sits on the same picture turned to `to`
export function turnBox(bbox: number[], from: number, to: number): number[] {
  const [x1, y1, x2, y2] = bbox.map(Number);
  switch (norm(to - from)) {
    case 90: return [1 - y2, x1, 1 - y1, x2];
    case 180: return [1 - x2, 1 - y2, 1 - x1, 1 - y1];
    case 270: return [y1, 1 - x2, y2, 1 - x1];
    default: return [x1, y1, x2, y2];
  }
}
