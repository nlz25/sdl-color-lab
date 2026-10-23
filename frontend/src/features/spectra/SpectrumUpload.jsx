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
  const { upload, spectrum, blocks, block, selectedBlockId, selectBlock, normalizedUrl, working, error, uploadFile } = useSpectrumSelection({ expectedWell, defaultWell, target, onReady });
  const display = spectrum?.color?.rgb;
  return <div className={"upload-box " + (compact ? "compact " : "") + (spectrum ? "has-spectrum" : "")}>
    <div className="upload-heading">
      <span className="reagent-dot" style={{ background: display ? rgbCss(display) : SWATCHES[name] || "#d8dddf" }} />
      <b>{title}</b>{spectrum?.ready_for_rgb && <span className="ready-mark" aria-label={t("upload.parsed")}>✓</span>}
    </div>
    <input ref={fileRef} aria-label={t("upload.file", { name: title })} className="file-input" type="file" accept=".csv,.xlsx,.xls" onChange={(event) => { uploadFile(event.target.files?.[0]); event.target.value = ""; }} disabled={disabled || working} />
    <button type="button" className="upload-button" disabled={disabled || working} onClick={() => fileRef.current.click()}>
      {working ? t("upload.reading") : upload ? filename(upload.filename) : t("upload.choose")}
    </button>
    {upload && blocks.length > 1 && <label className="scan-selector">{t("upload.scan")}
      <select aria-label={t("upload.scan")} value={selectedBlockId} onChange={(event) => selectBlock(event.target.value)} disabled={disabled || working}>
        <option value="">{t("upload.selectScan")}</option>
        {blocks.map((item) => <option key={item.block_id} value={item.block_id}>{item.sheet === "__csv__" ? t("upload.csvScan") : item.sheet} · {t("upload.scanRow", { row: item.header_row + 1 })}</option>)}
      </select>
    </label>}
    {upload && !blocks.length && <p className="spectrum-warning">{t("upload.missingWell", { well: expectedWell || defaultWell })}</p>}
    {spectrum && <div className="spectrum-preview">
      {display && <div><Swatch rgb={display} /><span>RGB {display.join(", ")}{spectrum.delta_e_2000 !== undefined && <b> · ΔE₀₀ {format(spectrum.delta_e_2000)}</b>}</span></div>}
      <small>{t("upload.measured")}: {(spectrum.original_wavelength_range_nm || spectrum.wavelength_range_nm).join("–")} nm · {spectrum.sampling_interval_nm == null ? t("upload.variableStep", { step: spectrum.max_sampling_interval_nm }) : t("upload.step", { step: spectrum.sampling_interval_nm })} · {t("upload.points", { count: spectrum.original_sample_count || spectrum.sample_count })}</small>
      {spectrum.instrument && <small>{t("measurement.reader")}: {spectrum.instrument}</small>}
      {Boolean(spectrum.ignored_outside_colour_band?.length) && <small>{t("upload.ignored", { count: spectrum.ignored_outside_colour_band.length })}</small>}
      {normalizedUrl && <a className="text-link normalized-download" href={normalizedUrl} download>{t("upload.normalized")}</a>}
    </div>}
    {spectrum && !spectrum.ready_for_rgb && <div className="spectrum-warning" role="status"><b>{t("upload.notReady")}</b><ErrorNotice>{spectrum.conversion_error}</ErrorNotice><small>{t("upload.noExtrapolation")}</small></div>}
    <ErrorNotice>{error}</ErrorNotice>
  </div>;
}
