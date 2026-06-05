export function buildApiUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  return `${url.pathname}${url.search}`;
}

async function parseErrorResponse(response) {
  let detail = `${response.status} ${response.statusText}`;
  try {
    const payload = await response.json();
    detail = payload.detail || JSON.stringify(payload);
  } catch {
    // ignore
  }
  return detail;
}

export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await parseErrorResponse(response));
  }
  return response.json();
}

export async function fetchBlob(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await parseErrorResponse(response));
  }
  return response.blob();
}

export async function fetchJsonSafe(label, url, options = {}) {
  try {
    return { label, ok: true, data: await fetchJson(url, options) };
  } catch (error) {
    return { label, ok: false, error: error.message };
  }
}
