import * as assert from "node:assert/strict";

import * as vscode from "vscode";

import { EXTENSION_ID, HOST_COMMANDS } from "../../host/types";

suite("Extension Host smoke", function () {
  this.timeout(30_000);

  test("activates, registers commands, creates StatusBar, and can deactivate", async () => {
    const extension = vscode.extensions.getExtension<{
      statusBar: vscode.StatusBarItem;
      shutdown(): Promise<void>;
    }>(EXTENSION_ID);
    assert.ok(extension, `missing extension ${EXTENSION_ID}`);
    const api = await extension.activate();
    assert.equal(extension.isActive, true);
    assert.ok(api.statusBar, "StatusBar item was not created");
    assert.equal(typeof api.statusBar.text, "string");
    assert.ok(
      api.statusBar.text.includes("$("),
      `unexpected StatusBar text: ${api.statusBar.text}`,
    );

    const commands = await vscode.commands.getCommands(true);
    for (const id of Object.values(HOST_COMMANDS)) {
      assert.ok(commands.includes(id), `command not registered: ${id}`);
    }

    await vscode.commands.executeCommand(HOST_COMMANDS.showOutput);
    await vscode.commands.executeCommand(HOST_COMMANDS.resetAlertBadge);
    await api.shutdown();
  });
});
