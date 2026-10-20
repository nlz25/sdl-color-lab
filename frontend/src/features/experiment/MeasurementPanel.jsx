import React from "react";
import SpectrumUpload from "../spectra/SpectrumUpload.jsx";
import { useI18n } from "../../i18n/I18n.jsx";

export default function MeasurementPanel({ sessionId, method, round, well, target, working, stagedMeasurement, onFeedback, feedback, submitMeasurement }) {
  const { t } = useI18n();
  return <div className="feedback-area">
    <div className="feedback-heading"><div><h3>{t("measurement.title")}</h3><p>{t("measurement.hint", { well })}</p></div></div>
    {stagedMeasurement && <p className="micro">{t("measurement.staged")}</p>}
    <SpectrumUpload key={sessionId + "-" + method + "-" + round} title={t("measurement.current")} expectedWell={well} target={target} onReady={onFeedback} disabled={Boolean(working)} compact />
    {feedback && <div className="measurement-confirmation">
      <span className="micro">{t("measurement.binding", { well })}</span>
      <button className="primary" disabled={Boolean(working)} onClick={submitMeasurement}>{t(working === "record" ? "measurement.recording" : "measurement.confirm")}<span>→</span></button>
    </div>}
  </div>;
}
