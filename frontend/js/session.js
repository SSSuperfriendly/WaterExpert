const AUTH_STORAGE_KEY = "waterexpert.auth.profile";

export function getStoredProfile() {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveProfile(profile) {
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(profile));
}

export function clearProfile() {
  try {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    // ignore storage errors
  }
}

export function requireSession() {
  const profile = getStoredProfile();
  if (profile) {
    return profile;
  }
  if (!window.location.pathname.endsWith("/login.html")) {
    window.location.replace("/ui/login.html");
  }
  return null;
}

export function redirectIfAuthenticated() {
  if (getStoredProfile()) {
    window.location.replace("/ui/index.html");
    return true;
  }
  return false;
}

export function renderSessionProfile() {
  const profile = getStoredProfile();
  const label = document.getElementById("accountLabel");
  if (label) {
    label.textContent = profile ? `${profile.username} | ${profile.role}` : "";
  }
}

export function bindLogout() {
  const button = document.getElementById("logoutButton");
  if (!button || button.dataset.bound === "1") {
    return;
  }
  button.dataset.bound = "1";
  button.addEventListener("click", () => {
    clearProfile();
    window.location.replace("/ui/login.html");
  });
}
