import React, { useRef } from "react";
import { SWATCHES } from "../../domain/experiment.js";
import { rgbCss } from "../../domain/colors.js";
import { filename, format } from "../../domain/format.js";
import { useI18n } from "../../i18n/I18n.jsx";
import Swatch from "../../components/Swatch.jsx";
import ErrorNotice from "../../components/ErrorNotice.jsx";
import { useSpectrumSelection } from "./useSpectrumSelection.js";

export default function SpectrumUpload({ title, name, expectedWell, defaultWell, target, onReady, disabled, compact = false }) {
  const { t } = useI18n();
  const fileRef = useRef(null);
  const { upload, spectrum, working, error, uploadFile } = useSpectrumSelection({ expectedWell, defaultWell, target, onReady });
  const display = spectrum?.color?.rgb;
  return <div className={"upload-box " + (compact ? "compact " : "") + (spectrum ? "has-spectrum" : "")}>
    <div className="upload-heading">
      <span className="reagent-dot" style={{ background: display ? rgbCss(display) : SWATCHES[name] || "#d8dddf" }} />
      <b>{title}</b>{spectrum && <span className="ready-mark" aria-label={t("upload.parsed")}>✓</span>}
    </div>
    <input ref={fileRef} aria-label={t("upload.file", { name: title })} className="file-input" type="file" accept=".csv" onChange={(event) => { uploadFile(event.target.files?.[0]); event.target.value = ""; }} disabled={disabled || working} />
    <button type="button" className="upload-button" disabled={disabled || working} onClick={() => fileRef.current.click()}>
      {working ? t("upload.reading") : upload ? filename(upload.filename) : t("upload.choose")}
    </button>
    {spectrum && <div className="spectrum-preview">
      <div><Swatch rgb={display} /><span>RGB {display.join(", ")}{spectrum.delta_e_2000 !== undefined && <b> · ΔE₀₀ {format(spectrum.delta_e_2000)}</b>}</span></div>
      <small>{spectrum.wavelength_nm?.[0]}–{spectrum.wavelength_nm?.at(-1)} nm · {t("upload.points", { count: spectrum.sample_count || spectrum.wavelength_nm?.length })}</small>
    </div>}
    <ErrorNotice>{error}</ErrorNotice>
  </div>;
}
