import type { HostController } from "./controller";
import type { HostLogger } from "./types";
import { HOST_COMMANDS } from "./types";

export interface OutputUi {
  show(): void;
}

export type HostCommandHandler = () => Promise<void>;

export function bindCommands(
  controller: HostController,
  output: OutputUi,
  logger: HostLogger,
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
  };
}

export { HOST_COMMANDS };
