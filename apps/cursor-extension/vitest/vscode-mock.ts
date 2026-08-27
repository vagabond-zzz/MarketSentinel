export type ConfigMap = Record<string, unknown>;

export const vscodeState = {
  folders: [] as { uri: { fsPath: string } }[],
  settings: {} as ConfigMap,
  commands: new Map<string, () => Promise<void> | void>(),
  outputLines: [] as string[],
  outputShown: false,
  configListeners: [] as Array<(event: { affectsConfiguration: (key: string) => boolean }) => void>,
};

export function resetVscodeMock(): void {
  vscodeState.folders = [];
  vscodeState.settings = {};
  vscodeState.commands.clear();
  vscodeState.outputLines = [];
  vscodeState.outputShown = false;
  vscodeState.configListeners = [];
}

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
};
