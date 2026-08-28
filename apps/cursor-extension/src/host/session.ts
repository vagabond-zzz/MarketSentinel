import type { FeedbackType } from "../protocol/types";
import type { HostController } from "./controller";
import type { HostLogger } from "./types";
import { HOST_COMMANDS } from "./types";

export interface OutputUi {
  show(): void;
}

export type HostCommandHandler = () => Promise<void>;

export interface SignalChoice {
  label: string;
  id: string;
}

export interface FeedbackChoice {
  label: string;
  value: FeedbackType;
}

export interface FeedbackPrompt {
  pickSignal(items: SignalChoice[]): Promise<SignalChoice | undefined>;
  pickLabel(items: FeedbackChoice[]): Promise<FeedbackChoice | undefined>;
}

export const FEEDBACK_CHOICES: FeedbackChoice[] = [
  { label: "有用", value: "useful" },
  { label: "没用", value: "not_useful" },
  { label: "太吵", value: "too_noisy" },
  { label: "太晚", value: "too_late" },
];

export function bindCommands(
  controller: HostController,
  output: OutputUi,
  logger: HostLogger,
  prompt?: FeedbackPrompt,
): Record<string, HostCommandHandler> {
  const wrap = (name: string, fn: () => Promise<void>): HostCommandHandler => {
    return async () => {
      try {
        await fn();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        logger.host(`${name} failed: ${message}`);
      }
    };
  };
  return {
    [HOST_COMMANDS.pause]: wrap("pause", () => controller.pause()),
    [HOST_COMMANDS.resume]: wrap("resume", () => controller.resume()),
    [HOST_COMMANDS.restartCore]: wrap("restartCore", () => controller.restartCore()),
    [HOST_COMMANDS.showOutput]: async () => {
      output.show();
    },
    [HOST_COMMANDS.resetAlertBadge]: wrap("resetAlertBadge", async () => {
      controller.resetAlertBadge();
    }),
    [HOST_COMMANDS.submitSignalFeedback]: wrap("submitSignalFeedback", async () => {
      const targets = controller.signalFeedbackTargets();
      if (targets.length === 0) {
        logger.host("no active signals for feedback");
        return;
      }
      if (prompt === undefined) {
        logger.host("signal feedback UI is unavailable");
        return;
      }
      const signal = await prompt.pickSignal(targets);
      if (signal === undefined) {
        return;
      }
      const choice = await prompt.pickLabel(FEEDBACK_CHOICES);
      if (choice === undefined) {
        return;
      }
      await controller.submitSignalFeedback(signal.id, choice.value);
    }),
  };
}

export { HOST_COMMANDS };
