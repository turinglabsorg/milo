// The theme the person chose, set before the page paints; without a choice the system decides.
(() => {
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("milo.theme");
    if (saved === "light" || saved === "dark") root.dataset.theme = saved;
  } catch {}
  // Like an app: Safari zooms on a pinch whatever the page says, so the page cancels it.
  for (const gesture of ["gesturestart", "gesturechange"]) document.addEventListener(gesture, (event) => event.preventDefault(), { passive: false });
  document.addEventListener("click", (event) => {
    if (!event.target.closest?.("[data-theme-toggle]")) return;
    const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    root.dataset.theme = current === "dark" ? "light" : "dark";
    try { localStorage.setItem("milo.theme", root.dataset.theme); } catch {}
  });
})();
