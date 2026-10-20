import React, { useEffect, useRef, useState } from "react";
import { METHODS, NAMES, SUCCESS_THRESHOLD } from "../../domain/experiment.js";
import { format } from "../../domain/format.js";
import { sessionsApi } from "../../api/sessions.js";
import { useI18n } from "../../i18n/I18n.jsx";
import Swatch from "../../components/Swatch.jsx";
import ErrorNotice from "../../components/ErrorNotice.jsx";

export default function SessionDetails({ snapshot }) {
  const { t } = useI18n();
  const [prompt, setPrompt] = useState(null);
  const [error, setError] = useState("");
  const promptRevision = useRef(0);
  useEffect(() => {
    promptRevision.current += 1;
    setPrompt(null); setError("");
  }, [snapshot.id, snapshot.runs?.llm?.history?.length]);
  async function loadPrompt() {
    if (prompt) return;
    const revision = promptRevision.current;
    try {
      const value = await sessionsApi.prompt(snapshot.id);
      if (revision === promptRevision.current) setPrompt(value.messages);
    } catch (exc) { if (revision === promptRevision.current) setError(exc.message); }
  }
  const calibration = snapshot.runs?.llm?.calibration?.data || snapshot.calibration || [];
  return <details className="session-details"><summary>{t("details.title")}</summary>
    {calibration.length > 0 && <div className="detail-calibrations">{calibration.map((row) => <div key={row.name}><Swatch rgb={row.rgb} /><span>{t("reagent." + row.name)}<small>RGB {row.rgb.join(", ")}</small></span></div>)}</div>}
    <p className="micro">{t("details.config", { model: snapshot.active_method === "bo" ? METHODS.bo : snapshot.config.model, id: snapshot.config.plate_id, budget: snapshot.config.budget })}</p>
    <p className="micro">{t(snapshot.config.initialization_mode === "cold_start" ? "details.policy" : "details.legacyPolicy")}</p>
    {snapshot.active_method === "llm" && <div className="detail-actions"><button className="text-button" type="button" onClick={loadPrompt}>{t("details.prompt")}</button></div>}
    <ErrorNotice>{error}</ErrorNotice>
    {prompt && <div className="prompt-preview"><p className="micro">{t("details.original")}</p>{prompt.map((message, i) => <pre key={i}>{message.content}</pre>)}</div>}
    <div className="completion-results">{["llm", "bo"].filter((method) => snapshot.runs[method]?.history?.length > 0).map((method) => {
      const history = snapshot.runs[method].history;
      const best = history.reduce((a, b) => a.delta_e_2000 < b.delta_e_2000 ? a : b);
      const firstSuccess = history.find((row) => row.delta_e_2000 <= SUCCESS_THRESHOLD);
      return <div key={method}><b>{t("details.minimum", { method: METHODS[method], error: format(best.delta_e_2000) })}</b><p>{t("details.best", { round: best.round, threshold: SUCCESS_THRESHOLD, firstSuccess: firstSuccess ? t("chart.round", { round: firstSuccess.round }) : t("details.notReached") })}</p><small>{NAMES.map((name) => t("reagent." + name) + " " + best.recipe[name]).join(" / ")} µL</small></div>;
    })}</div>
  </details>;
}
