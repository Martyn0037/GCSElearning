// frontend/src/game/continuePath.ts
import type { ContinueOut } from "../api/generated/model";

/** Where the Continue button goes. */
export function continuePath(target: ContinueOut): string | null {
  switch (target.kind) {
    case "daily":
      return "/daily";
    case "review":
      return "/review";
    case "topic":
      return target.enrolmentId && target.topicId
        ? `/practice/${target.enrolmentId}/${target.topicId}`
        : null;
    default:
      return null;
  }
}
