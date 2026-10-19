import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";
import { type Bridge, CHANNELS, type UpdateState } from "./bridge";

const bridge: Bridge = {
  invoke: (command, args) => ipcRenderer.invoke(CHANNELS.invoke, command, args),
  openUrl: (url) => ipcRenderer.invoke(CHANNELS.openUrl, url),
  pickFile: (filters) => ipcRenderer.invoke(CHANNELS.pickFile, filters),
  onUpdate: (listener) => {
    const relay = (_event: IpcRendererEvent, state: UpdateState) => listener(state);
    ipcRenderer.on(CHANNELS.update, relay);
    return () => void ipcRenderer.removeListener(CHANNELS.update, relay);
  },
};

contextBridge.exposeInMainWorld("relay", bridge);
