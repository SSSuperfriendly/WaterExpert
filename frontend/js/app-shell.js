import { initSidebar } from "./sidebar.js";
import { initThemeToggle } from "./theme.js";
import { bindLogout, renderSessionProfile, requireSession } from "./session.js";

export function initAuthenticatedShell() {
  const profile = requireSession();
  if (!profile) {
    return null;
  }
  initThemeToggle();
  initSidebar();
  bindLogout();
  renderSessionProfile();
  return profile;
}
