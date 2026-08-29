export type ConfigMap = Record<string, unknown>;

export class MarkdownString {
  value: string;
  isTrusted = false;
  supportHtml = false;
  supportThemeIcons = false;

  constructor(value = "") {
    this.value = value;
  }
}

export const vscodeState = {
  folders: [] as { uri: { fsPath: string } }[],
  settings: {} as ConfigMap,
  commands: new Map<string, () => Promise<void> | void>(),
  outputLines: [] as string[],
  outputShown: false,
  detailsPanel: {
    shown: false,
    html: "",
    messages: [] as unknown[],
    disposed: false,
    revealCount: 0,
    title: "",
    viewType: "",
  },
  toasts: [] as string[],
  configListeners: [] as Array<(event: { affectsConfiguration: (key: string) => boolean }) => void>,
  statusBar: {
    text: "",
    tooltip: undefined as string | MarkdownString | undefined,
    shown: false,
    command: undefined as string | undefined,
    backgroundColor: undefined as { id: string } | undefined,
  },
};

export function resetVscodeMock(): void {
  vscodeState.folders = [];
  vscodeState.settings = {};
  vscodeState.commands.clear();
  vscodeState.outputLines = [];
  vscodeState.outputShown = false;
  vscodeState.detailsPanel = {
    shown: false,
    html: "",
    messages: [],
    disposed: false,
    revealCount: 0,
    title: "",
    viewType: "",
  };
  vscodeState.toasts = [];
  vscodeState.configListeners = [];
  vscodeState.statusBar = {
    text: "",
    tooltip: undefined,
    shown: false,
    command: undefined,
    backgroundColor: undefined,
  };
}

export class ThemeColor {
  constructor(public id: string) {}
}

export const StatusBarAlignment = {
  Left: 1,
  Right: 2,
} as const;

export const ViewColumn = {
  One: 1,
  Two: 2,
  Three: 3,
  Active: -1,
  Beside: -2,
} as const;

export const ConfigurationTarget = {
  Global: 1,
  Workspace: 2,
  WorkspaceFolder: 3,
} as const;

export const window = {
  createOutputChannel(_name: string) {
    return {
      appendLine(line: string) {
        vscodeState.outputLines.push(line);
      },
      clear() {
        vscodeState.outputLines = [];
      },
      show() {
        vscodeState.outputShown = true;
      },
      dispose() {
        return undefined;
      },
    };
  },
  createWebviewPanel(viewType: string, title: string, _column?: number, _options?: unknown) {
    let disposeListener: (() => void) | undefined;
    const webview = {
      cspSource: "vscode-webview://test",
      get html() {
        return vscodeState.detailsPanel.html;
      },
      set html(value: string) {
        vscodeState.detailsPanel.html = value;
      },
      postMessage(message: unknown) {
        vscodeState.detailsPanel.messages.push(message);
        return Promise.resolve(true);
      },
    };
    vscodeState.detailsPanel.viewType = viewType;
    vscodeState.detailsPanel.title = title;
    vscodeState.detailsPanel.shown = true;
    return {
      webview,
      reveal() {
        vscodeState.detailsPanel.shown = true;
        vscodeState.detailsPanel.revealCount += 1;
      },
      onDidDispose(listener: () => void) {
        disposeListener = listener;
        return { dispose() { return undefined; } };
      },
      dispose() {
        vscodeState.detailsPanel.disposed = true;
        vscodeState.detailsPanel.shown = false;
        disposeListener?.();
      },
    };
  },
  showInformationMessage(message: string) {
    vscodeState.toasts.push(message);
    return Promise.resolve(undefined);
  },
  showInputBox(_options?: { prompt?: string; ignoreFocusOut?: boolean }): Promise<string | undefined> {
    return Promise.resolve(undefined);
  },
  showQuickPick<T>(_items: T[], _options?: { placeHolder?: string }): Promise<T | undefined> {
    return Promise.resolve(undefined);
  },
  createStatusBarItem(_alignment?: number, _priority?: number) {
    return {
      text: "",
      tooltip: undefined as string | MarkdownString | undefined,
      command: undefined as string | undefined,
      backgroundColor: undefined as ThemeColor | undefined,
      show() {
        vscodeState.statusBar.shown = true;
        vscodeState.statusBar.text = this.text;
        vscodeState.statusBar.tooltip = this.tooltip;
        vscodeState.statusBar.command = this.command;
        vscodeState.statusBar.backgroundColor = this.backgroundColor;
      },
      hide() {
        vscodeState.statusBar.shown = false;
      },
      dispose() {
        vscodeState.statusBar.shown = false;
      },
    };
  },
};

export const commands = {
  registerCommand(id: string, handler: () => Promise<void> | void) {
    vscodeState.commands.set(id, handler);
    return {
      dispose() {
        vscodeState.commands.delete(id);
      },
    };
  },
};

export const workspace = {
  get workspaceFolders() {
    return vscodeState.folders.length > 0 ? vscodeState.folders : undefined;
  },
  getConfiguration(section: string) {
    return {
      get(key: string) {
        return vscodeState.settings[`${section}.${key}`];
      },
      update(key: string, value: unknown, _target?: number) {
        vscodeState.settings[`${section}.${key}`] = value;
        return Promise.resolve();
      },
    };
  },
  onDidChangeConfiguration(
    listener: (event: { affectsConfiguration: (key: string) => boolean }) => void,
  ) {
    vscodeState.configListeners.push(listener);
    return {
      dispose() {
        return undefined;
      },
    };
  },
};

export default {
  window,
  commands,
  workspace,
  StatusBarAlignment,
  ThemeColor,
  MarkdownString,
  ConfigurationTarget,
  ViewColumn,
};
