import { app, shell } from "electron";
import { autoUpdater } from "electron-updater";
import type { UpdateState } from "./bridge";

export const RELEASES = "https://github.com/bstcoc/relay/releases/latest/download";

const POLL = 30 * 60_000;

export class Updates {
  state: UpdateState = { status: "idle", version: null, percent: null, manual: process.platform === "darwin" };
  readonly #publish: (state: UpdateState) => void;

  constructor(publish: (state: UpdateState) => void) {
    this.#publish = publish;
  }

  #set(next: Partial<UpdateState>) {
    this.state = { ...this.state, ...next };
    this.#publish(this.state);
  }

  start() {
    if (!app.isPackaged) {
      return;
    }
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = !this.state.manual;
    autoUpdater.on("update-available", (update) => {
      if (this.state.status === "idle" || this.state.version !== update.version) {
        this.#set({ status: "available", version: update.version, percent: null });
      }
    });
    autoUpdater.on("download-progress", (progress) => this.#set({ percent: Math.round(progress.percent) }));
    autoUpdater.on("update-downloaded", (update) => this.#set({ status: "ready", version: update.version, percent: 100 }));
    autoUpdater.on("error", () => {
      if (this.state.status === "downloading") {
        this.#set({ status: "available", percent: null });
      }
    });
    this.#check();
    setInterval(() => this.#check(), POLL);
  }

  #check() {
    if (this.state.status === "downloading" || this.state.status === "ready") {
      return;
    }
    void autoUpdater.checkForUpdates().catch(() => undefined);
  }

  async download() {
    if (this.state.status !== "available") {
      return;
    }
    if (this.state.manual) {
      await shell.openExternal(`${RELEASES}/Relay-macOS-AppleSilicon.dmg`);
      return;
    }
    this.#set({ status: "downloading", percent: 0 });
    await autoUpdater.downloadUpdate().catch(() => this.#set({ status: "available", percent: null }));
  }

  install(beforeQuit: () => void) {
    if (this.state.status !== "ready") {
      return;
    }
    beforeQuit();
    autoUpdater.quitAndInstall(true, true);
  }
}
