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

export const window = {
  createOutputChannel(_name: string) {
    return {
      appendLine(line: string) {
        vscodeState.outputLines.push(line);
      },
      show() {
        vscodeState.outputShown = true;
      },
      dispose() {
        return undefined;
      },
    };
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
};
