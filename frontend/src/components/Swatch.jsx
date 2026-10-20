import React from "react";
import { rgbCss } from "../domain/colors.js";

export default function Swatch({ rgb, className = "", label }) {
  return <span aria-label={label} className={`swatch ${className}`} style={{ background: rgbCss(rgb) }} />;
}
