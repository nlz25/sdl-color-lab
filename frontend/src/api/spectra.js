import { apiUrl, post, request } from "./client.js";

export const spectraApi = {
  upload(file, options) {
    const body = new FormData();
    body.append("file", file);
    return request("/uploads", { ...options, method: "POST", body });
  },
  extract: (id, selection, options) =>
    post(`/uploads/${encodeURIComponent(id)}/prepare`, selection, options),
  normalizedUrl: (id, block, well) => apiUrl(`/uploads/${encodeURIComponent(id)}/spectrum.csv?${new URLSearchParams({ block_id: block.block_id, well })}`),
};
