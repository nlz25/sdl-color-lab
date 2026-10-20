import { apiUrl, post, request } from "./client.js";

const path = (id) => `/sessions/${encodeURIComponent(id)}`;
export const sessionsApi = {
  bootstrap: (options) => request("/bootstrap", options),
  preflight: () => post("/preflight"),
  create: (body) => post("/sessions", body),
  get: (id, options) => request(path(id), options),
  mutate: (id, action, body = {}) => post(`${path(id)}/${action}`, body),
  prompt: (id) => request(`${path(id)}/prompt`),
  protocolUrl: apiUrl("/opentrons/protocol.py"),
  openRecipeFolder: (id, method, round) => post(`${path(id)}/opentrons/open-folder`, { method, round_number: round }),
  recipeUrl: (id, method, round) => apiUrl(`${path(id)}/robot.csv${method ? `?method=${encodeURIComponent(method)}&round_number=${round}` : ""}`),
  archiveUrl: (id) => apiUrl(`${path(id)}/archive.zip`),
};
