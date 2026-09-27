import { detailFor } from "@/components/chat/agentTraceDetails";
import type { ReasoningStep } from "../../schemas";
import type { ReplayStepView } from "./ReplayTransportBar";

/** Enriches the backend's raw {index, token, node_id} reasoning-trail steps
 * with the human-readable agent name/color/caption already maintained for
 * the chat UI (agentTraceDetails.ts) -- a cross-cutting app utility, reused
 * rather than re-implemented, per the master spec's own guidance that this
 * mapping doesn't need to be duplicated. */
export function enrichReplaySteps(steps: ReasoningStep[]): Array<ReplayStepView & { nodeId: string }> {
  return steps.map((step) => {
    const detail = detailFor(step.token);
    return {
      index: step.index,
      nodeId: step.node_id,
      agent: detail.agent,
      color: detail.color,
      caption: detail.why || `${detail.agent} ran (${step.token}).`,
    };
  });
}
