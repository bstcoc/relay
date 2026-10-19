export type Answer<T> = { value: T } | { error: string };

export type FileFilter = { name: string; extensions: string[] };

export type UpdateState = {
  status: "idle" | "available" | "downloading" | "ready";
  version: string | null;
  percent: number | null;
  manual: boolean;
};

export type Bridge = {
  invoke: (command: string, args: Record<string, unknown>) => Promise<Answer<unknown>>;
  openUrl: (url: string) => Promise<Answer<null>>;
  pickFile: (filters: FileFilter[]) => Promise<string | null>;
  onUpdate: (listener: (state: UpdateState) => void) => () => void;
};

export const CHANNELS = {
  invoke: "relay:invoke",
  openUrl: "relay:open-url",
  pickFile: "relay:pick-file",
  update: "relay:update",
} as const;
