export type ThemeChoice = "light" | "dark" | "system";
const KEY = "tf-theme";

export function readTheme(): ThemeChoice {
  try {
    const v = window.localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    // storage unavailable
  }
  return "system";
}

export function applyTheme(choice: ThemeChoice): void {
  const dark =
    choice === "dark" ||
    (choice === "system" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  try {
    window.localStorage.setItem(KEY, choice);
  } catch {
    // ignore
  }
}
