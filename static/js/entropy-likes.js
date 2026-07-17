(function () {
  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute("content");
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function showToast(message, isError) {
    var box = document.getElementById("like-toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "like-toast";
      box.className =
        "fixed bottom-6 left-1/2 z-[60] hidden -translate-x-1/2 border px-4 py-2 text-sm";
      document.body.appendChild(box);
    }
    box.textContent = message;
    box.classList.remove("hidden", "border-white", "text-white", "border-red-400", "text-red-300");
    if (isError) {
      box.classList.add("border-red-400", "text-red-300", "bg-black");
    } else {
      box.classList.add("border-white", "text-white", "bg-black");
    }
    clearTimeout(box._hideTimer);
    box._hideTimer = setTimeout(function () {
      box.classList.add("hidden");
    }, 3200);
  }

  function updateLikeButton(btn, liked) {
    var label = btn.getAttribute("data-like-label");
    var unlikeLabel = btn.getAttribute("data-unlike-label");
    if (label && unlikeLabel) {
      btn.textContent = liked ? unlikeLabel : label;
    } else {
      btn.textContent = liked ? "−" : "+";
    }
    btn.setAttribute("data-liked", liked ? "true" : "false");
    btn.setAttribute("aria-pressed", liked ? "true" : "false");
  }

  async function toggleLike(btn) {
    if (btn.disabled) return;
    var url = btn.getAttribute("data-like-url");
    if (!url) return;

    btn.disabled = true;
    try {
      var response = await fetch(url, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCsrfToken(),
          Accept: "application/json",
        },
        credentials: "same-origin",
      });
      var data = await response.json();
      if (!response.ok || !data.ok) {
        showToast(data.error || "Не удалось поставить лайк.", true);
        return;
      }

      var countEl = document.querySelector(
        '[data-like-count-for="' + btn.getAttribute("data-like-id") + '"]'
      );
      if (countEl && typeof data.like_count === "number") {
        countEl.textContent = data.like_count;
      }

      updateLikeButton(btn, data.liked);
      if (data.message) showToast(data.message, false);
    } catch (err) {
      showToast("Ошибка сети. Попробуйте ещё раз.", true);
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-like-url]");
    if (!btn) return;
    event.preventDefault();
    toggleLike(btn);
  });
})();
