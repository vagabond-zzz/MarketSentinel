import * as vscode from "vscode";

import { HostController } from "./host/controller";
import { bindCommands } from "./host/session";
import type { RawSettings } from "./host/types";

let controller: HostController | undefined;

function readSettings(): RawSettings {
  const cfg = vscode.workspace.getConfiguration("marketSentinel");
  return {
    coreRoot: cfg.get<string>("coreRoot"),
    uvPath: cfg.get<string>("uvPath"),
    watchlist: cfg.get("watchlist"),
    provider: cfg.get("provider"),
    replayPath: cfg.get<string>("replayPath"),
  };
}

function splitCoreLines(chunk: string, write: (line: string) => void): void {
  for (const line of chunk.split(/\r?\n/)) {
    if (line.length > 0) {
      write(line);
    }
  }
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const output = vscode.window.createOutputChannel("Market Sentinel");
  const logger = {
    host: (message: string) => {
      output.appendLine(`[host] ${message}`);
    },
    core: (chunk: string) => {
      splitCoreLines(chunk, (line) => output.appendLine(`[core] ${line}`));
    },
  };
  const host = new HostController({
    readSettings,
    workspaceFolders: () =>
      vscode.workspace.workspaceFolders?.map((folder) => folder.uri.fsPath) ?? [],
    logger,
  });
  controller = host;
  const commands = bindCommands(host, { show: () => output.show() }, logger);
  for (const [id, handler] of Object.entries(commands)) {
    context.subscriptions.push(vscode.commands.registerCommand(id, handler));
  }
  context.subscriptions.push(output);
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      const keys = ["watchlist", "coreRoot", "uvPath", "provider", "replayPath"].filter((key) =>
        event.affectsConfiguration(`marketSentinel.${key}`),
      );
      if (keys.length > 0) {
        void host.onConfigurationChanged(keys);
      }
    }),
  );
  context.subscriptions.push({
    dispose: () => {
      void host.shutdown();
    },
  });
  await host.start();
}

export async function deactivate(): Promise<void> {
  await controller?.shutdown();
  controller = undefined;
}
