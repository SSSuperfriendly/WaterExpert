import { fetchJson } from "./api.js";
import { initThemeToggle } from "./theme.js";
import { redirectIfAuthenticated, saveProfile } from "./session.js";

let demoHint = null;

function setLoginPending(pending) {
  const submitButton = document.getElementById("loginSubmitButton");
  const fillDemoButton = document.getElementById("fillDemoButton");
  if (!submitButton) {
    return;
  }
  submitButton.disabled = pending;
  submitButton.classList.toggle("is-loading", pending);
  submitButton.textContent = pending ? "正在登录..." : "进入系统";
  if (fillDemoButton) {
    fillDemoButton.disabled = pending;
  }
}

function setLoginError(message) {
  const errorBox = document.getElementById("loginError");
  const username = document.getElementById("loginUsername");
  const password = document.getElementById("loginPassword");
  if (errorBox) {
    errorBox.textContent = message;
    errorBox.classList.toggle("is-visible", Boolean(message));
  }
  [username, password].forEach((input) => {
    input?.classList.toggle("is-invalid", Boolean(message));
  });
}

function setLoginStatus(message) {
  const statusBox = document.getElementById("loginStatus");
  if (statusBox) {
    statusBox.textContent = message;
    statusBox.classList.toggle("is-visible", Boolean(message));
  }
}

function fillDemoCredentials() {
  if (!demoHint) {
    return;
  }
  const username = document.getElementById("loginUsername");
  const password = document.getElementById("loginPassword");
  if (username) {
    username.value = demoHint.username;
  }
  if (password) {
    password.value = demoHint.password;
  }
  setLoginError("");
}

async function loadHint() {
  try {
    demoHint = await fetchJson("/api/v1/auth/hint");
    const hintBox = document.getElementById("loginHint");
    if (hintBox) {
      hintBox.textContent = `演示账号：${demoHint.username}。如需快速体验，可点击“一键进入系统”。`;
    }
  } catch {
    // ignore hint failures
  }
}

async function fillDemoAndSubmit() {
  if (!demoHint) {
    return;
  }
  fillDemoCredentials();
  document.getElementById("loginForm")?.requestSubmit();
}

function bindPasswordToggle() {
  const passwordInput = document.getElementById("loginPassword");
  const toggleButton = document.getElementById("passwordToggleButton");
  if (!passwordInput || !toggleButton) {
    return;
  }
  toggleButton.addEventListener("click", () => {
    const nextType = passwordInput.type === "password" ? "text" : "password";
    passwordInput.type = nextType;
    const revealed = nextType === "text";
    toggleButton.classList.toggle("is-revealed", revealed);
    toggleButton.setAttribute("aria-label", revealed ? "隐藏密码" : "显示密码");
    toggleButton.title = revealed ? "隐藏密码" : "显示密码";
  });
}

async function handleLogin(event) {
  event.preventDefault();
  const username = document.getElementById("loginUsername")?.value || "";
  const password = document.getElementById("loginPassword")?.value || "";
  setLoginError("");
  setLoginStatus("");
  setLoginPending(true);
  try {
    const profile = await fetchJson("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    saveProfile(profile);
    setLoginStatus("登录成功，正在进入系统首页...");
    await new Promise((resolve) => window.setTimeout(resolve, 300));
    window.location.replace("/ui/index.html");
  } catch (error) {
    setLoginError(`登录失败：${error.message}`);
  } finally {
    setLoginPending(false);
  }
}

if (!redirectIfAuthenticated()) {
  initThemeToggle();
  bindPasswordToggle();
  loadHint();
  document.getElementById("loginForm")?.addEventListener("submit", handleLogin);
  document.getElementById("fillDemoButton")?.addEventListener("click", () => {
    fillDemoAndSubmit().catch(() => {
      fillDemoCredentials();
    });
  });
}
