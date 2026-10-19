import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";

const NONCE = 12;
const TAG = 16;

type Secrets = Record<string, string>;

export type Keychain = {
  read: () => Promise<string | null>;
  write: (hex: string) => Promise<void>;
};

export function systemKeychain(service: string, account: string): Keychain {
  const entry = async () => {
    const { AsyncEntry } = await import("@napi-rs/keyring");
    return new AsyncEntry(service, account);
  };
  return {
    read: async () => {
      try {
        return (await (await entry()).getPassword()) ?? null;
      } catch (error) {
        throw new Error(`cannot read the vault key from the system keychain: ${String(error)}`);
      }
    },
    write: async (hex) => {
      try {
        await (await entry()).setPassword(hex);
      } catch (error) {
        throw new Error(`cannot store the vault key in the system keychain: ${String(error)}`);
      }
    },
  };
}

export function setAside(path: string) {
  if (!existsSync(path)) {
    return;
  }
  try {
    renameSync(path, `${path}.lost`);
  } catch (error) {
    throw new Error(`cannot set the old vault aside: ${String(error)}`);
  }
}

export function fromHex(text: string): Buffer | null {
  return /^[0-9a-f]{64}$/i.test(text) ? Buffer.from(text, "hex") : null;
}

function read(path: string, key: Buffer): Secrets {
  let sealed: Buffer;
  try {
    sealed = readFileSync(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return {};
    }
    throw new Error(`cannot read the vault: ${String(error)}`);
  }
  if (sealed.length < NONCE + TAG) {
    throw new Error("the vault file is damaged");
  }
  let plain: Buffer;
  try {
    const decipher = createDecipheriv("aes-256-gcm", key, sealed.subarray(0, NONCE));
    decipher.setAuthTag(sealed.subarray(sealed.length - TAG));
    plain = Buffer.concat([decipher.update(sealed.subarray(NONCE, sealed.length - TAG)), decipher.final()]);
  } catch {
    throw new Error("the vault cannot be opened with the key of this computer");
  }
  try {
    return JSON.parse(plain.toString("utf8")) as Secrets;
  } catch {
    throw new Error("the vault file is damaged");
  }
}

function write(path: string, key: Buffer, secrets: Secrets) {
  const nonce = randomBytes(NONCE);
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  const body = Buffer.concat([cipher.update(JSON.stringify(secrets), "utf8"), cipher.final()]);
  try {
    writeFileSync(`${path}.tmp`, Buffer.concat([nonce, body, cipher.getAuthTag()]));
    renameSync(`${path}.tmp`, path);
  } catch (error) {
    throw new Error(`cannot write the vault: ${String(error)}`);
  }
}

export class Vault {
  readonly path: string;
  readonly #master: () => Promise<Buffer>;
  #unlocked: Promise<{ key: Buffer; secrets: Secrets }> | null = null;

  constructor(path: string, master: Buffer | Keychain) {
    this.path = path;
    this.#master = Buffer.isBuffer(master) ? async () => master : () => this.#masterKey(master);
  }

  async #masterKey(keychain: Keychain): Promise<Buffer> {
    const hex = await keychain.read();
    if (hex !== null) {
      const key = fromHex(hex);
      if (!key) {
        throw new Error("the vault key in the system keychain is damaged");
      }
      return key;
    }
    const key = randomBytes(32);
    await keychain.write(key.toString("hex"));
    setAside(this.path);
    return key;
  }

  #unlock() {
    this.#unlocked ??= this.#master().then((key) => ({ key, secrets: read(this.path, key) }));
    this.#unlocked.catch(() => {
      this.#unlocked = null;
    });
    return this.#unlocked;
  }

  async get(name: string): Promise<string | null> {
    const { secrets } = await this.#unlock();
    return secrets[name] ?? null;
  }

  async set(name: string, value: string | null) {
    const unlocked = await this.#unlock();
    if ((unlocked.secrets[name] ?? null) === value) {
      return;
    }
    const next = { ...unlocked.secrets };
    if (value === null) {
      delete next[name];
    } else {
      next[name] = value;
    }
    write(this.path, unlocked.key, next);
    unlocked.secrets = next;
  }

  remove(name: string) {
    return this.set(name, null);
  }
}
