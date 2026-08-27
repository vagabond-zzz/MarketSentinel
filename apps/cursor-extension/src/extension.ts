import * as vscode from "vscode";

import { parseAlertToast, planCriticalToast } from "./alerts/state";
import { HostController } from "./host/controller";
import { bindCommands } from "./host/session";
import { HOST_COMMANDS, type RawSettings } from "./host/types";
import { renderHoverMarkdown } from "./hover/render";
import type { HoverModel } from "./hover/model";
import type { AlertMessage } from "./protocol/types";
import type { StatusBarModel } from "./statusbar/map";

let controller: HostController | undefined;

function readSettings(): RawSettings {
  const cfg = vscode.workspace.getConfiguration("marketSentinel");
  return {
    coreRoot: cfg.get<string>("coreRoot"),
    uvPath: cfg.get<string>("uvPath"),
    watchlist: cfg.get("watchlist"),
    provider: cfg.get("provider"),
    replayPath: cfg.get<string>("replayPath"),
    enableHoverDetails: cfg.get<boolean>("enableHoverDetails"),
    alertToast: cfg.get<string>("alertToast"),
  };
}

function splitCoreLines(chunk: string, write: (line: string) => void): void {
  for (const line of chunk.split(/\r?\n/)) {
    if (line.length > 0) {
      write(line);
    }
  }
}

function applyStatusBar(
  item: vscode.StatusBarItem,
  model: StatusBarModel,
  hover: HoverModel,
): void {
  item.text = model.text;
  const tooltip = new vscode.MarkdownString(renderHoverMarkdown(hover));
  tooltip.isTrusted = false;
  item.tooltip = tooltip;
  item.command = HOST_COMMANDS.showOutput;
  if (model.tone === "error") {
    item.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
  } else if (model.tone === "warning") {
    item.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
  } else {
    item.backgroundColor = undefined;
  }
  item.show();
}

export function presentHostAlertToast(message: AlertMessage, alertToast: unknown): void {
  const plan = planCriticalToast(parseAlertToast(alertToast), message.candidates);
  if (plan.show && plan.message !== undefined) {
    void vscode.window.showInformationMessage(plan.message);
  }
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const output = vscode.window.createOutputChannel("Market Sentinel");
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
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
    onUiSnapshot: (snapshot) => applyStatusBar(statusBar, snapshot.statusBar, snapshot.hover),
    onAlertEdge: (message) => presentHostAlertToast(message, readSettings().alertToast),
  });
  controller = host;
  applyStatusBar(statusBar, host.statusBarModel(), host.hoverModel());
  const commands = bindCommands(host, { show: () => output.show() }, logger);
  for (const [id, handler] of Object.entries(commands)) {
    context.subscriptions.push(vscode.commands.registerCommand(id, handler));
  }
  context.subscriptions.push(output, statusBar);
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      const keys = [
        "watchlist",
        "coreRoot",
        "uvPath",
        "provider",
        "replayPath",
        "enableHoverDetails",
        "alertToast",
      ].filter((key) => event.affectsConfiguration(`marketSentinel.${key}`));
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
