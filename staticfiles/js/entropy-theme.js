(function () {
  var STORAGE_KEY = "entropy-site-theme";
  var TRANSITION_CLASS = "entropy-theming";

  function applyTheme(mode) {
    var html = document.documentElement;
    html.setAttribute("data-site-theme", mode);
    localStorage.setItem(STORAGE_KEY, mode);
  }

  function getStoredTheme() {
    return localStorage.getItem(STORAGE_KEY);
  }

  function initTheme() {
    var stored = getStoredTheme();
    if (stored === "light" || stored === "dark") {
      applyTheme(stored);
      return;
    }
    var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(prefersDark ? "dark" : "light");
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute("data-site-theme") || "light";
    var next = current === "dark" ? "light" : "dark";

    // Add transition class for smooth theme switching
    var html = document.documentElement;
    html.classList.add(TRANSITION_CLASS);
    applyTheme(next);

    // Remove transition class after animations complete
    clearTimeout(html._themeTimer);
    html._themeTimer = setTimeout(function () {
      html.classList.remove(TRANSITION_CLASS);
    }, 300);
  }

  // Listen for system theme changes when no user preference is stored
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
    if (getStoredTheme() !== null) return; // user has a preference saved
    var html = document.documentElement;
    html.classList.add(TRANSITION_CLASS);
    applyTheme(e.matches ? "dark" : "light");
    clearTimeout(html._themeTimer);
    html._themeTimer = setTimeout(function () {
      html.classList.remove(TRANSITION_CLASS);
    }, 300);
  });

  initTheme();

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("site-theme-toggle");
    if (btn) btn.addEventListener("click", toggleTheme);
  });
})();
