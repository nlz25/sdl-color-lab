import React from "react";
import { METHODS } from "../domain/experiment.js";
import { useI18n } from "../i18n/I18n.jsx";

export default function MethodPicker({ method, onChange, disabled = false }) {
  const { t } = useI18n();
  return <div className="method-picker">
    <span className="micro">{t("setup.method")}</span>
    <div className="segmented" role="group" aria-label={t("setup.method")}>
      {Object.entries(METHODS).map(([key, label]) => <button key={key} type="button"
        className={method === key ? "selected" : ""} aria-pressed={method === key}
        disabled={disabled} onClick={() => onChange(key)}>
        {label}
      </button>)}
    </div>
  </div>;
}
