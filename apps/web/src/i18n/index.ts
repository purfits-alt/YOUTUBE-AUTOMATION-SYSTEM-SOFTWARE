import en from "./en.json";

type Vars = Record<string, string | number>;

const missing = new Set<string>();

function lookup(path: string): unknown {
  let node: unknown = en;
  for (const part of path.split(".")) {
    if (node === null || typeof node !== "object" || !(part in node)) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

/** Translate a dotted key from en.json. `{name}` placeholders are replaced from `vars`. */
export function t(path: string, vars?: Vars): string {
  const value = lookup(path);
  if (typeof value !== "string") {
    if (!missing.has(path)) {
      missing.add(path);
      console.warn(`i18n: missing key ${path}`);
    }
    return path;
  }
  if (!vars) return value;
  return value.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

export function hasKey(path: string): boolean {
  return typeof lookup(path) === "string";
}
