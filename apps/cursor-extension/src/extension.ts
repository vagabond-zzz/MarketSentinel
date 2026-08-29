import * as vscode from "vscode";

import { parseAlertToast, planCriticalToast } from "./alerts/state";
import { HostController } from "./host/controller";
import { bindCommands, type FeedbackPrompt, type WatchlistPrompt } from "./host/session";
import type { RawSettings } from "./host/types";
import type { AlertMessage, WatchlistItem } from "./protocol/types";
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
    intelligence: cfg.get<string>("intelligence"),
    symbolNames: cfg.get("symbolNames"),
    symbolDisplay: cfg.get<string>("symbolDisplay"),
    statusBarMaxSymbols: cfg.get<number>("statusBarMaxSymbols"),
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

function vscodeWatchlistPrompt(): WatchlistPrompt {
  return {
    inputSymbol: async () => {
      const value = await vscode.window.showInputBox({
        prompt: "输入标的代码，例如 600519.SH",
        ignoreFocusOut: true,
      });
      return value;
    },
    pickSymbol: async (items) => {
      const picked = await vscode.window.showQuickPick(
        items.map((item) => ({ label: item.label, symbol: item.symbol })),
        { placeHolder: "选择要移除的标的" },
      );
      return picked?.symbol;
    },
    pickManageAction: async (count, max) => {
      const picked = await vscode.window.showQuickPick(
        [
          { label: "Add", action: "add" as const },
          { label: "Remove", action: "remove" as const },
        ],
        { placeHolder: `当前 ${count} / ${max}` },
      );
      return picked?.action;
    },
  };
}

async function persistWatchlist(items: WatchlistItem[]): Promise<void> {
  const cfg = vscode.workspace.getConfiguration("marketSentinel");
  const target =
    vscode.workspace.workspaceFolders !== undefined && vscode.workspace.workspaceFolders.length > 0
      ? vscode.ConfigurationTarget.Workspace
      : vscode.ConfigurationTarget.Global;
  await cfg.update(
    "watchlist",
    items.map((item) => item.symbol),
    target,
  );
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
    persistWatchlist,
    onUiSnapshot: (snapshot) => applyStatusBar(statusBar, snapshot.statusBar, snapshot.hover),
    onAlertEdge: (message) => presentHostAlertToast(message, readSettings().alertToast),
  });
  controller = host;
  applyStatusBar(statusBar, host.statusBarModel(), host.hoverModel());
  const commands = bindCommands(
    host,
    { show: () => output.show() },
    logger,
    vscodeFeedbackPrompt(),
    vscodeWatchlistPrompt(),
  );
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
        "intelligence",
        "symbolNames",
        "symbolDisplay",
        "statusBarMaxSymbols",
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
