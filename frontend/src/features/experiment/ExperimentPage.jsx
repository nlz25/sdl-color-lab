import React, { useState } from "react";
import { METHODS, allRows } from "../../domain/experiment.js";
import { sessionsApi } from "../../api/sessions.js";
import { useI18n } from "../../i18n/I18n.jsx";
import ErrorNotice from "../../components/ErrorNotice.jsx";
import OpentronsDownloads from "../../components/OpentronsDownloads.jsx";
import IterationChart from "../chart/IterationChart.jsx";
import SessionDetails from "./SessionDetails.jsx";
import RecipePanel from "./RecipePanel.jsx";
import MeasurementPanel from "./MeasurementPanel.jsx";
import RoundResults from "./RoundResults.jsx";
import { useExperiment } from "./useExperiment.js";

export default function ExperimentPage({ snapshot, setSnapshot, desktopFiles = true }) {
  const { t } = useI18n();
  const [filter, setFilter] = useState("all");
  const rows = allRows(snapshot);
  const { method, round, well, complete, pending, working, error, feedback, mutate, onFeedback, submitMeasurement } = useExperiment({ snapshot, setSnapshot });
  const model = method === "llm" ? snapshot.config.model : METHODS.bo;
  return <main className="experiment">
    {snapshot.validation?.measurement_source === "synthetic" && <div className="validation-note"><span className="tiny-dot" />{t(snapshot.validation.gpt_status === "deferred" ? "experiment.virtualTestDeferred" : "experiment.virtualTest")}</div>}
    <IterationChart rows={rows} target={snapshot.config.target_rgb} plateId={snapshot.config.plate_id} budget={snapshot.config.budget} method={method} filter={filter} onFilter={setFilter} />
    <RoundResults rows={rows} filter={filter} modelId={snapshot.config.model} />
    <section className="action-panel">
      {method && <div className="action-title"><div><span className={"method-line " + method} /><h2>{model}</h2><span className="round-label">{t("experiment.round", { round })}</span></div><span className="well-pill">{t("experiment.well", { well })}</span></div>}
      {!complete && <p className="micro method-fixed-note">{t("experiment.locked")}</p>}
      {method && !complete && !pending && <div className="generate-row"><div><h3>{t("experiment.generateTitle")}</h3><p>{t("experiment.generateHint")}</p></div>
        <button className="primary" disabled={Boolean(working) || snapshot.invalid_response_pending} onClick={() => mutate("propose")}>{t(working === "propose" ? "experiment.generating" : "experiment.generate")}<span>→</span></button>
      </div>}
      {snapshot.invalid_response_pending && <div className="retry-row"><span>{t("experiment.invalid")}</span><button className="secondary small" disabled={Boolean(working)} onClick={() => mutate("retry-invalid")}>{t("experiment.retryInvalid")}</button></div>}
      {method && pending && <>
        <RecipePanel key={`${method}/${round}`} pending={pending} sessionId={snapshot.id} recipeFile={snapshot.opentrons_files?.[method]} desktopFiles={desktopFiles} />
        <MeasurementPanel sessionId={snapshot.id} method={method} round={round} well={well} target={snapshot.config.target_rgb} working={working} stagedMeasurement={snapshot.staged_measurement} onFeedback={onFeedback} feedback={feedback} submitMeasurement={submitMeasurement} />
        {pending.reasoning && <details className="reasoning"><summary>{t("experiment.reasoning")}</summary><p>{method === "bo" && snapshot.config.initialization_mode === "cold_start" && round === 1 ? t("experiment.boFirstReasoning") : pending.reasoning}</p></details>}
      </>}
      <div className={complete ? "generate-row experiment-records" : "experiment-records"}>
        {complete && <div><h2>{t("experiment.methodComplete", { method: model })}</h2><p>{t("experiment.finishedHint")}</p></div>}
        <a className="secondary" href={sessionsApi.archiveUrl(snapshot.id)}>{t("experiment.download")}</a>
      </div>
      {!pending && <OpentronsDownloads desktopFiles={desktopFiles} />}
      <ErrorNotice>{error}</ErrorNotice>
    </section>
    <SessionDetails snapshot={snapshot} />
  </main>;
}
