import React from "react";
import { useI18n } from "../../i18n/I18n.jsx";

export default function MeasurementRequirements() {
  const { t } = useI18n();
  return <div className="measurement-requirements">
    <span>{t("measurement.reader")}: <b>Tecan Infinite 200 Pro</b></span>
    <span>{t("measurement.scanRange")}: <b>380–780 nm</b></span>
    <span>{t("measurement.scanStep")}: <b>{t("measurement.stepValue")}</b></span>
  </div>;
}
