import React from "react";
import ErrorNotice from "../components/ErrorNotice.jsx";
import ExperimentPage from "../features/experiment/ExperimentPage.jsx";
import SetupPage from "../features/setup/SetupPage.jsx";
import { sessionLabel } from "../domain/experiment.js";
import { I18nProvider, LanguageSwitch, useI18n } from "../i18n/I18n.jsx";
import { useSessionNavigation } from "./useSessionNavigation.js";

export default function App({ initialLanguage = "en" }) {
  return <I18nProvider initialLanguage={initialLanguage}><AppShell /></I18nProvider>;
}

function AppShell() {
  const { t } = useI18n();
  const { bootstrap, snapshot, setSnapshot, error, loading, sessionId, selectSession, created, retrySelected } = useSessionNavigation();
  const records = bootstrap?.sessions || [];
  const desktopFiles = bootstrap?.capabilities?.open_local_folder !== false;
  const selected = records.find((item) => item.id === sessionId);
  return <div className="app-shell">
    <header className="app-header">
      <a className="brand" href="/" onClick={(event) => { event.preventDefault(); selectSession(""); }}><span className="brand-dots"><i /><i /><i /></span>{t("nav.brand")}</a>
      <div className="header-right">
        <div className="session-navigation">
          <select aria-label={t("nav.select")} title={selected ? sessionLabel(selected) : t("nav.new")} value={sessionId} onChange={(event) => selectSession(event.target.value)}>
            <option value="">{t("nav.new")}</option>
            {records.map((item) => <option key={item.id} value={item.id}>{sessionLabel(item)}</option>)}
            {sessionId && !records.some((item) => item.id === sessionId) && <option value={sessionId}>{sessionId}</option>}
          </select>
        </div>
        <LanguageSwitch />
      </div>
    </header>
    <ErrorNotice>{error}</ErrorNotice>
    {loading || (!bootstrap && !error) ? <div className="loading"><span className="spinner" />{t("app.loading")}</div> : snapshot ? <ExperimentPage key={snapshot.id} snapshot={snapshot} setSnapshot={setSnapshot} desktopFiles={desktopFiles} /> : sessionId ? <main className="session-recovery"><h1>{t("app.recoveryTitle")}</h1><p>{t("app.recoveryHint")}</p><div><button className="primary" onClick={retrySelected}>{t("app.reload")}</button><button className="text-button" onClick={() => selectSession("")}>{t("nav.new")}</button></div></main> : bootstrap ? <SetupPage key="new" bootstrap={bootstrap} onCreated={created} /> : <div className="loading">{t("app.unavailable")}</div>}
    <footer className="app-footer"><span>GPT-6 × BO-EI</span><span>{t(desktopFiles ? "app.saved" : "app.savedServer")}</span></footer>
  </div>;
}
