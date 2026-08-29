import * as vscode from "vscode";

import { HOST_COMMANDS } from "../host/types";
import type { HoverModel } from "../hover/model";
import { renderHoverMarkdown } from "../hover/render";
import type { StatusBarModel } from "./map";

export function applyStatusBar(
  item: vscode.StatusBarItem,
  model: StatusBarModel,
  hover: HoverModel,
): void {
  item.text = model.text;
  const tooltip = new vscode.MarkdownString(renderHoverMarkdown(hover));
  tooltip.isTrusted = false;
  tooltip.supportThemeIcons = true;
  item.tooltip = tooltip;
  item.command = HOST_COMMANDS.showOutput;
  item.backgroundColor = undefined;
  item.show();
}
