/** Spark is dark-only. Kept so existing imports stay safe. */
export function applyDarkMode(_on?: boolean) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.add("dark");
  document.documentElement.dataset.theme = "dark";
}
