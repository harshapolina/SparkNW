export function applyDarkMode(on: boolean) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", on);
  document.documentElement.dataset.theme = on ? "dark" : "light";
}
