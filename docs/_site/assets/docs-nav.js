(function () {
  function slugify(text) {
    return text
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-");
  }

  function ensureId(heading, usedIds) {
    if (heading.id) {
      usedIds.add(heading.id);
      return heading.id;
    }

    var base = slugify(heading.textContent || "") || "section";
    var candidate = base;
    var index = 2;

    while (usedIds.has(candidate)) {
      candidate = base + "-" + index;
      index += 1;
    }

    heading.id = candidate;
    usedIds.add(candidate);
    return candidate;
  }

  function setActive(items, id) {
    items.forEach(function (item) {
      item.link.classList.toggle("is-active", item.heading.id === id);
    });
  }

  function initPageSections() {
    var activeNavLink = document.querySelector("[data-active-nav-link]");
    var sidebarSections = document.querySelector("[data-page-sections]");
    var sectionNav = document.querySelector("[data-section-nav]");
    var content = document.querySelector(".content");

    if (!activeNavLink || !sidebarSections || !sectionNav || !content) {
      return;
    }

    var headings = Array.prototype.slice.call(content.querySelectorAll("h2"));

    if (!headings.length) {
      return;
    }

    var usedIds = new Set(
      Array.prototype.map.call(document.querySelectorAll("[id]"), function (node) {
        return node.id;
      })
    );

    var items = headings
      .map(function (heading) {
        ensureId(heading, usedIds);

        var text = (heading.textContent || "").trim();
        if (!text) {
          return null;
        }

        var link = document.createElement("a");
        link.className = "section-link level-" + heading.tagName.toLowerCase();
        link.href = "#" + heading.id;
        link.textContent = text;
        sectionNav.appendChild(link);

        return { heading: heading, link: link };
      })
      .filter(Boolean);

    if (!items.length) {
      return;
    }

    activeNavLink.setAttribute("aria-current", "page");
    sidebarSections.hidden = false;

    activeNavLink.addEventListener("click", function (event) {
      event.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    function getCurrentHeadingId() {
      var offset = 72;
      var current = items[0].heading.id;

      items.forEach(function (item) {
        if (item.heading.getBoundingClientRect().top - offset <= 0) {
          current = item.heading.id;
        }
      });

      return current;
    }

    function syncActiveHeading() {
      setActive(items, getCurrentHeadingId());
    }

    items.forEach(function (item) {
      item.link.addEventListener("click", function () {
        setActive(items, item.heading.id);
      });
    });

    window.addEventListener("scroll", syncActiveHeading, { passive: true });
    window.addEventListener("resize", syncActiveHeading);
    window.addEventListener("load", syncActiveHeading);
    window.addEventListener("hashchange", syncActiveHeading);
    window.requestAnimationFrame(syncActiveHeading);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPageSections);
  } else {
    initPageSections();
  }
})();
