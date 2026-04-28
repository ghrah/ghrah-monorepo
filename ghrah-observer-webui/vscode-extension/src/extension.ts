import {
  commands,
  type ExtensionContext,
  ViewColumn,
  type WebviewPanel,
  window,
  workspace,
} from "vscode";
import { Launcher } from "./launcher.js";

let panel: WebviewPanel | undefined;
let launcher: Launcher | undefined;

export async function activate(context: ExtensionContext) {
  launcher = new Launcher();

  const config = workspace.getConfiguration("ghrah");
  const autoStart = config.get<boolean>("gateway.autoStart", true);

  if (autoStart) {
    const gatewayUrl = config.get<string>("gateway.url", "ws://localhost:8000/ws");
    const launchMethod = config.get<string>("gateway.launchMethod", "uv");
    const binaryPath = config.get<string>("gateway.binaryPath", "");
    const workspaceRoot = config.get<string>("workspace.root", "");

    await launcher.ensureGateway(gatewayUrl, { launchMethod, binaryPath });

    const subjectAutoStart = config.get<boolean>("subject.autoStart", true);
    if (subjectAutoStart && workspaceRoot) {
      await launcher.ensureSubject(gatewayUrl, workspaceRoot);
    }
  }

  context.subscriptions.push(
    commands.registerCommand("ghrah.openDashboard", () => {
      openDashboard();
    }),
    commands.registerCommand("ghrah.startCluster", async () => {
      if (launcher) {
        await launcher.startCluster();
      }
    }),
    commands.registerCommand("ghrah.stopCluster", async () => {
      if (launcher) {
        await launcher.stopCluster();
      }
    }),
  );
}

export function deactivate() {
  panel?.dispose();
  launcher?.stopAll();
}

function openDashboard() {
  if (panel) {
    panel.reveal(ViewColumn.One);
    return;
  }

  panel = window.createWebviewPanel("ghrah-dashboard", "Ghrah Dashboard", ViewColumn.One, {
    enableScripts: true,
    retainContextWhenHidden: true,
  });

  panel.webview.html = getWebviewContent();

  panel.onDidDispose(() => {
    panel = undefined;
  });
}

function getWebviewContent(): string {
  return /* html */ `
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Ghrah Dashboard</title>
    </head>
    <body>
      <div id="app">
        <p>Loading Ghrah Observer...</p>
        <p>In development mode, the SPA runs at <a href="http://localhost:5173">http://localhost:5173</a>.</p>
      </div>
    </body>
    </html>
  `;
}
