import * as vscode from "vscode";

import { parseAlertToast, planCriticalToast } from "./alerts/state";
import { HostController } from "./host/controller";
import { bindCommands, type FeedbackPrompt } from "./host/session";
import type { RawSettings } from "./host/types";
import type { AlertMessage } from "./protocol/types";
import { applyStatusBar } from "./statusbar/adapter";

export interface ExtensionApi {
  statusBar: vscode.StatusBarItem;
  shutdown(): Promise<void>;
}

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

export function presentHostAlertToast(message: AlertMessage, alertToast: unknown): void {
  const plan = planCriticalToast(parseAlertToast(alertToast), message.candidates);
  if (plan.show && plan.message !== undefined) {
    void vscode.window.showInformationMessage(plan.message);
  }
}

function vscodeFeedbackPrompt(): FeedbackPrompt {
  return {
    pickSignal: async (items) => {
      const picked = await vscode.window.showQuickPick(
        items.map((item) => ({ label: item.label, id: item.id })),
        { placeHolder: "选择信号" },
      );
      return picked === undefined ? undefined : { id: picked.id, label: picked.label };
    },
    pickLabel: async (items) => {
      const picked = await vscode.window.showQuickPick(
        items.map((item) => ({ label: item.label, value: item.value })),
        { placeHolder: "这条提醒对你有帮助吗？" },
      );
      return picked;
    },
  };
}

export async function activate(context: vscode.ExtensionContext): Promise<ExtensionApi> {
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
  const commands = bindCommands(host, { show: () => output.show() }, logger, vscodeFeedbackPrompt());
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
  return {
    statusBar,
    shutdown: async () => {
      await host.shutdown();
    },
  };
}

export async function deactivate(): Promise<void> {
  await controller?.shutdown();
  controller = undefined;
}
