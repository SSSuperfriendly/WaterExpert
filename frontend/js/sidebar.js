import {
  SIDEBAR_BREAKPOINT_PX,
  SIDEBAR_COLLAPSED_KEY,
  SIDEBAR_WIDTH_KEY,
  SIDEBAR_WIDTH_MIN_PX,
  SIDEBAR_WIDTH_MAX_PX,
  SIDEBAR_DRAG_THRESHOLD_PX,
  getElement,
} from "./base.js";

export function closeSidebar() {
  document.body.classList.remove("sidebar-open");
}

export function clampSidebarWidth(width) {
  return Math.min(
    SIDEBAR_WIDTH_MAX_PX,
    Math.max(SIDEBAR_WIDTH_MIN_PX, Math.round(Number(width) || SIDEBAR_WIDTH_MIN_PX))
  );
}

export function setSidebarWidth(width) {
  document.documentElement.style.setProperty("--sidebar-width", `${clampSidebarWidth(width)}px`);
}

export function getStoredSidebarWidth() {
  try {
    const storedWidth = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
    return storedWidth ? clampSidebarWidth(storedWidth) : null;
  } catch {
    return null;
  }
}

export function persistSidebarWidth(width) {
  try {
    window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(clampSidebarWidth(width)));
  } catch {
    // ignore storage failures
  }
}

export function persistSidebarCollapsed(collapsed) {
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    // ignore storage failures
  }
}

function bindCollapsedTitles() {
  document.querySelectorAll(".side-link").forEach((link) => {
    const label = link.querySelector(".side-link-text")?.textContent?.trim();
    if (label) {
      link.title = label;
      link.setAttribute("aria-label", label);
    }
  });
}

export function updateSidebarControls() {
  const sidebarEdgeToggle = getElement("sidebarEdgeToggle");
  if (!sidebarEdgeToggle) {
    return;
  }

  if (window.innerWidth <= SIDEBAR_BREAKPOINT_PX) {
    sidebarEdgeToggle.dataset.state = "expanded";
    sidebarEdgeToggle.setAttribute("aria-pressed", "false");
    sidebarEdgeToggle.setAttribute("aria-label", "侧栏缩放与折叠");
    sidebarEdgeToggle.title = "侧栏缩放与折叠";
    return;
  }

  const collapsed = document.body.classList.contains("sidebar-collapsed");
  sidebarEdgeToggle.dataset.state = collapsed ? "collapsed" : "expanded";
  sidebarEdgeToggle.setAttribute("aria-pressed", collapsed ? "true" : "false");
  sidebarEdgeToggle.setAttribute("aria-label", collapsed ? "展开侧栏" : "折叠侧栏");
  sidebarEdgeToggle.title = collapsed ? "展开侧栏" : "折叠侧栏";
  const srOnly = sidebarEdgeToggle.querySelector(".sr-only");
  if (srOnly) {
    srOnly.textContent = collapsed ? "展开侧栏" : "折叠侧栏";
  }
}

export function toggleSidebar() {
  if (window.innerWidth <= SIDEBAR_BREAKPOINT_PX) {
    document.body.classList.toggle("sidebar-open");
    return;
  }
  const nextCollapsed = !document.body.classList.contains("sidebar-collapsed");
  document.body.classList.toggle("sidebar-collapsed", nextCollapsed);
  persistSidebarCollapsed(nextCollapsed);
  updateSidebarControls();
}

export function initSidebar() {
  const storedWidth = getStoredSidebarWidth();
  if (storedWidth) {
    setSidebarWidth(storedWidth);
  }

  try {
    const collapsed = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
    if (collapsed && window.innerWidth > SIDEBAR_BREAKPOINT_PX) {
      document.body.classList.add("sidebar-collapsed");
    }
  } catch {
    // ignore storage failures
  }

  bindCollapsedTitles();
  updateSidebarControls();

  const sidebarToggleMobile = getElement("sidebarToggleMobile");
  if (sidebarToggleMobile) {
    sidebarToggleMobile.addEventListener("click", toggleSidebar);
  }

  const sidebarEdgeToggle = getElement("sidebarEdgeToggle");
  if (sidebarEdgeToggle) {
    sidebarEdgeToggle.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleSidebar();
      }
    });

    sidebarEdgeToggle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || window.innerWidth <= SIDEBAR_BREAKPOINT_PX) {
        return;
      }

      const startX = event.clientX;
      const startWidth =
        parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width")) ||
        SIDEBAR_WIDTH_MIN_PX;
      let dragged = false;

      const finishInteraction = () => {
        document.body.classList.remove("sidebar-resizing");
        if (typeof sidebarEdgeToggle.releasePointerCapture === "function" && event.pointerId !== undefined) {
          try {
            sidebarEdgeToggle.releasePointerCapture(event.pointerId);
          } catch {
            // ignore release failures
          }
        }
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
        window.removeEventListener("pointercancel", handlePointerUp);
      };

      const handlePointerMove = (moveEvent) => {
        const deltaX = moveEvent.clientX - startX;
        if (!dragged && Math.abs(deltaX) >= SIDEBAR_DRAG_THRESHOLD_PX) {
          dragged = true;
          document.body.classList.remove("sidebar-collapsed");
          persistSidebarCollapsed(false);
          updateSidebarControls();
        }
        if (!dragged) {
          return;
        }
        document.body.classList.add("sidebar-resizing");
        setSidebarWidth(startWidth + deltaX);
      };

      const handlePointerUp = (upEvent) => {
        finishInteraction();
        if (upEvent.type === "pointercancel") {
          return;
        }
        const deltaX = upEvent.clientX - startX;
        if (!dragged && Math.abs(deltaX) < SIDEBAR_DRAG_THRESHOLD_PX) {
          toggleSidebar();
          return;
        }
        const appliedWidth =
          parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width")) ||
          startWidth;
        persistSidebarWidth(appliedWidth);
      };

      event.preventDefault();
      if (typeof sidebarEdgeToggle.setPointerCapture === "function" && event.pointerId !== undefined) {
        try {
          sidebarEdgeToggle.setPointerCapture(event.pointerId);
        } catch {
          // ignore capture failures
        }
      }
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp, { once: true });
      window.addEventListener("pointercancel", handlePointerUp, { once: true });
    });
  }

  const sidebarScrim = getElement("sidebarScrim");
  if (sidebarScrim) {
    sidebarScrim.addEventListener("click", closeSidebar);
  }

  window.addEventListener("resize", () => {
    if (window.innerWidth > SIDEBAR_BREAKPOINT_PX) {
      closeSidebar();
    }
    updateSidebarControls();
  });
}
