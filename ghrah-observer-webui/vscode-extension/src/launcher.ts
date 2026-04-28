import { type ChildProcess, spawn } from "node:child_process";

export interface LaunchOptions {
  launchMethod: string;
  binaryPath: string;
}

export class Launcher {
  private gatewayProcess: ChildProcess | null = null;
  private subjectProcess: ChildProcess | null = null;

  async ensureGateway(url: string, opts: LaunchOptions): Promise<void> {
    if (await this.isReachable(url)) {
      return;
    }

    if (opts.launchMethod === "binary" && opts.binaryPath) {
      this.gatewayProcess = spawn(opts.binaryPath, [], { stdio: "pipe" });
    } else {
      this.gatewayProcess = spawn("uv", ["run", "ghrah-gateway"], {
        stdio: "pipe",
        cwd: this.findProjectRoot(),
      });
    }

    this.gatewayProcess.on("error", (err) => {
      console.error("Gateway process error:", err);
    });

    await this.waitForReachable(url, 30_000);
  }

  async ensureSubject(gatewayUrl: string, workspaceRoot: string): Promise<void> {
    this.subjectProcess = spawn("uv", ["run", "ghrah-subject", "--workspace-root", workspaceRoot], {
      stdio: "pipe",
      cwd: this.findProjectRoot(),
    });

    this.subjectProcess.on("error", (err) => {
      console.error("Subject process error:", err);
    });

    await this.waitForReachable(gatewayUrl, 30_000);
  }

  async stopAll(): Promise<void> {
    this.stopProcess(this.gatewayProcess);
    this.gatewayProcess = null;
    this.stopProcess(this.subjectProcess);
    this.subjectProcess = null;
  }

  isRunning(): { gateway: boolean; subject: boolean } {
    return {
      gateway: this.gatewayProcess !== null && !this.gatewayProcess.killed,
      subject: this.subjectProcess !== null && !this.subjectProcess.killed,
    };
  }

  async startCluster(): Promise<void> {
    // TODO: send init_cluster command via WebSocket
  }

  async stopCluster(): Promise<void> {
    // TODO: send shutdown_cluster command via WebSocket
  }

  private async isReachable(url: string): Promise<boolean> {
    try {
      const wsUrl = new URL(url);
      const response = await fetch(`http://${wsUrl.host}/health`, {
        signal: AbortSignal.timeout(3000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  private async waitForReachable(url: string, timeout: number): Promise<void> {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (await this.isReachable(url)) return;
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error(`Gateway not reachable at ${url} after ${timeout}ms`);
  }

  private stopProcess(proc: ChildProcess | null) {
    if (proc && !proc.killed) {
      proc.kill("SIGTERM");
    }
  }

  private findProjectRoot(): string {
    return process.env["GHRAH_PROJECT_ROOT"] ?? process.cwd();
  }
}
