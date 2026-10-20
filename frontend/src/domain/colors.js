export const rgbCss = (rgb) => `rgb(${rgb.map((v) => Math.max(0, Math.min(255, Math.round(v)))).join(",")})`;
export const rgbHex = (rgb) => `#${rgb.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("")}`;
export const hexRgb = (value) => [1, 3, 5].map((start) => parseInt(value.slice(start, start + 2), 16));

