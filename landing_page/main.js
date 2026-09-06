(function () {
  "use strict";

  /* ===========================================================
     Mobile menu
     =========================================================== */
  var burgerBtn = document.getElementById("burgerBtn");
  var overlay = document.getElementById("overlay");
  var mobileMenu = document.getElementById("mobileMenu");
  var body = document.body;

  function openMenu() {
    burgerBtn.setAttribute("aria-expanded", "true");
    burgerBtn.setAttribute("aria-label", "Close menu");
    overlay.hidden = false;
    mobileMenu.hidden = false;
    body.classList.add("menu-open");
  }

  function closeMenu() {
    burgerBtn.setAttribute("aria-expanded", "false");
    burgerBtn.setAttribute("aria-label", "Open menu");
    overlay.hidden = true;
    mobileMenu.hidden = true;
    body.classList.remove("menu-open");
  }

  function isMenuOpen() {
    return burgerBtn.getAttribute("aria-expanded") === "true";
  }

  burgerBtn.addEventListener("click", function () {
    if (isMenuOpen()) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  overlay.addEventListener("click", closeMenu);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && isMenuOpen()) {
      closeMenu();
    }
  });

  mobileMenu.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", closeMenu);
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth > 720 && isMenuOpen()) {
      closeMenu();
    }
  });

  /* ===========================================================
     Stats count-up (easeOutCubic, staggered, once via IO)
     =========================================================== */
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function formatValue(value, decimals, suffix) {
    return value.toFixed(decimals) + suffix;
  }

  function animateStat(el, index) {
    var target = parseFloat(el.getAttribute("data-target"));
    var suffix = el.getAttribute("data-suffix") || "";
    var decimals = parseInt(el.getAttribute("data-decimals"), 10) || 0;
    var duration = 1500 + index * 80;
    var startOffset = 480 + index * 90;

    setTimeout(function () {
      var startTime = null;

      function step(timestamp) {
        if (startTime === null) startTime = timestamp;
        var elapsed = timestamp - startTime;
        var progress = Math.min(elapsed / duration, 1);
        var eased = easeOutCubic(progress);
        var current = target * eased;
        el.textContent = formatValue(current, decimals, suffix);

        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          el.textContent = formatValue(target, decimals, suffix);
        }
      }

      requestAnimationFrame(step);
    }, startOffset);
  }

  var statValues = document.querySelectorAll(".stat-value");
  var statsContainer = document.querySelector(".stats");
  var hasAnimated = false;

  if ("IntersectionObserver" in window && statsContainer) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting && !hasAnimated) {
            hasAnimated = true;
            statValues.forEach(function (el, i) {
              animateStat(el, i);
            });
            observer.disconnect();
          }
        });
      },
      { threshold: 0.25 }
    );

    observer.observe(statsContainer);
  } else {
    /* Fallback: no IO support */
    statValues.forEach(function (el, i) {
      animateStat(el, i);
    });
  }

  /* Respect reduced motion: jump straight to final values */
  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  if (prefersReducedMotion) {
    statValues.forEach(function (el) {
      var target = parseFloat(el.getAttribute("data-target"));
      var suffix = el.getAttribute("data-suffix") || "";
      var decimals = parseInt(el.getAttribute("data-decimals"), 10) || 0;
      el.textContent = formatValue(target, decimals, suffix);
    });
    if (typeof observer !== "undefined") observer.disconnect();
  }
})();
