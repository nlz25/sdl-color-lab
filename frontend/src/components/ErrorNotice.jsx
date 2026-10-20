import React from "react";
import { useI18n } from "../i18n/I18n.jsx";
import { localizeError } from "../i18n/errors.js";

export default function ErrorNotice({ children }) {
  const { language, t } = useI18n();
  if (!children) return null;
  const { message, details } = localizeError(children, language);
  return <div className="error" role="alert">{message}{details && details !== message && <details className="error-details"><summary>{t("error.details")}</summary><pre>{details}</pre></details>}</div>;
}
