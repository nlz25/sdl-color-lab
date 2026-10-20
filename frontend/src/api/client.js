/** All browser requests stay on the frontend origin; Vite proxies /api in dev. */
export const apiUrl = (path) => `/api${path}`;

export async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: options.body instanceof FormData
      ? options.headers
      : { "Content-Type": "application/json", ...options.headers },
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = result.detail || result.error || `Request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return result;
}

export const post = (path, body = {}, options = {}) =>
  request(path, { ...options, method: "POST", body: JSON.stringify(body) });
