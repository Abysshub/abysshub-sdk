// Node's fs and path modules, which Node, Bun and Deno all serve. They are imported
// by a non-literal specifier so the library needs no @types/node, and loads in
// places that have neither.

export interface NodeFS {
  readFile(path: string): Promise<Uint8Array>;
  writeFile(path: string, data: Uint8Array): Promise<void>;
  mkdir(path: string, options: { recursive: true }): Promise<unknown>;
}

export interface NodePath {
  join(...paths: string[]): string;
  dirname(path: string): string;
  resolve(...paths: string[]): string;
  relative(from: string, to: string): string;
  isAbsolute(path: string): boolean;
}

const FS: string = "node:fs/promises";
const PATH: string = "node:path";

export function nodeFS(): Promise<NodeFS> {
  return import(FS);
}

export function nodePath(): Promise<NodePath> {
  return import(PATH);
}
