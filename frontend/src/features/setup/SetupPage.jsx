import React from "react";
import { rgbHex, hexRgb } from "../../domain/colors.js";
import { useI18n } from "../../i18n/I18n.jsx";
import ErrorNotice from "../../components/ErrorNotice.jsx";
import MethodPicker from "../../components/MethodPicker.jsx";
import OpentronsDownloads from "../../components/OpentronsDownloads.jsx";
import { METHODS } from "../../domain/experiment.js";
import { useInitialization } from "./useInitialization.js";

export default function SetupPage({ bootstrap, onCreated }) {
  const { t } = useI18n();
  const { method, setMethod, target, setTarget, working, error, model, ready, start } = useInitialization({ bootstrap, onCreated });
  return <main className="setup">
    <div className="section-heading"><div><h1>{t("setup.title")}</h1><p>{t("setup.subtitle")}</p></div>
    </div>
    <p className="micro cold-start-note">{t("setup.coldStart")}</p>
    <MethodPicker method={method} onChange={setMethod} disabled={Boolean(working)} />
    <div className="setup-section"><span className="eyebrow">{t("setup.targetSection")}</span>
      <div className="target-form">
        <label className="colour-picker"><input aria-label={t("setup.target")} type="color" value={rgbHex(target)} onChange={(event) => setTarget(hexRgb(event.target.value))} disabled={Boolean(working)} /><span>{t("setup.target")}</span></label>
        <div className="rgb-inputs">{["R", "G", "B"].map((channel, i) => <label key={channel}>{channel}<input aria-label={t("setup.targetChannel", { channel })} type="number" min="0" max="255" value={target[i]} onChange={(event) => setTarget(target.map((v, j) => i === j ? Math.max(0, Math.min(255, Math.round(Number(event.target.value)))) : v))} disabled={Boolean(working)} /></label>)}</div>
      </div>
    </div>
    <p className="micro">{method === "llm" ? model.model || "GPT-6" : "BO-EI"} · {t("setup.volume")}</p>
    {method === "llm" && !model.api_key_configured && !model.error && <p className="micro">{t("setup.configure")}</p>}
    {method === "llm" && <ErrorNotice>{model.error}</ErrorNotice>}
    <ErrorNotice>{error}</ErrorNotice>
    <OpentronsDownloads />
    <div className="setup-footer"><small>{t("setup.budget")}</small><button className="primary" onClick={start} disabled={!ready || Boolean(working)}>{t(working === "start" ? "setup.starting" : "setup.start", { method: METHODS[method] })}<span>→</span></button></div>
  </main>;
}
