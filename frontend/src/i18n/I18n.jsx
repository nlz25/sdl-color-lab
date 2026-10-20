import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { translate } from "./messages.js";

const English = { language: "en", t: (key, values) => translate("en", key, values) };
const I18nContext = createContext(English);

export function I18nProvider({ children, initialLanguage = "en" }) {
  const [language, setLanguage] = useState(initialLanguage === "zh" ? "zh" : "en");
  const value = useMemo(() => ({ language, setLanguage, t: (key, values) => translate(language, key, values) }), [language]);
  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    document.title = translate(language, "app.title");
  }, [language]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);

export function LanguageSwitch() {
  const { language, setLanguage, t } = useI18n();
  return <div className="language-switch" role="group" aria-label={t("nav.language")}>
    <button type="button" lang="en" aria-label="English" title="English" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
    <button type="button" lang="zh-CN" aria-label="中文" title="中文" aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>ZH</button>
  </div>;
}
