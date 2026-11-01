(() => {
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pad = (value) => String(value).padStart(2, "0");
  if (!still) {
    for (const digits of document.querySelectorAll("[data-count]")) {
      const target = Number(digits.dataset.count);
      let value = 0;
      digits.textContent = "00";
      const timer = setInterval(() => {
        value += 1;
        digits.textContent = pad(value);
        if (value >= target) clearInterval(timer);
      }, 900 / target);
    }
  }
  for (const button of document.querySelectorAll("[data-copy]")) {
    button.addEventListener("click", async () => {
      const text = document.getElementById(button.dataset.copy).textContent.split("\n").filter((line) => !line.startsWith("#")).join("\n");
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "copied";
        button.dataset.state = "copied";
      } catch {
        button.textContent = "select it";
        button.dataset.state = "failed";
      }
      setTimeout(() => { button.textContent = "copy"; delete button.dataset.state; }, 1600);
    });
  }
})();
