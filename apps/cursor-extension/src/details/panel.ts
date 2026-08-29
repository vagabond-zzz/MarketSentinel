import { randomBytes } from "node:crypto";
import * as vscode from "vscode";

import type { HoverModel } from "../hover/model";
import { renderDetailsBody, renderDetailsDocument } from "./render";

const VIEW_TYPE = "marketSentinel.details";
const TITLE = "Market Sentinel · 行情详情";

interface RenderMessage {
  type: "render";
  html: string;
}

export class MarketDetailsPanel implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private lastModel: HoverModel | undefined;

  show(model: HoverModel): void {
    this.lastModel = model;
    if (this.panel === undefined) {
      this.panel = this.createPanel(model);
      return;
    }
    this.panel.reveal(undefined, false);
    this.post(model);
  }

  update(model: HoverModel): void {
    this.lastModel = model;
    if (this.panel !== undefined) {
      this.post(model);
    }
  }

  dispose(): void {
    this.panel?.dispose();
    this.panel = undefined;
  }

  private createPanel(model: HoverModel): vscode.WebviewPanel {
    const panel = vscode.window.createWebviewPanel(
      VIEW_TYPE,
      TITLE,
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      },
    );
    const nonce = randomBytes(16).toString("hex");
    panel.webview.html = renderDetailsDocument(panel.webview.cspSource, nonce, model);
    panel.onDidDispose(() => {
      if (this.panel === panel) {
        this.panel = undefined;
      }
    });
    return panel;
  }

  private post(model: HoverModel): void {
    const panel = this.panel;
    if (panel === undefined) {
      return;
    }
    const message: RenderMessage = { type: "render", html: renderDetailsBody(model) };
    void panel.webview.postMessage(message);
  }
}
