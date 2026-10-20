import { useCallback, useEffect, useRef, useState } from "react";
import { spectraApi } from "../../api/spectra.js";

/** One CSV is one spectrum; the upload card fixes its reagent/current well. */
export function useSpectrumSelection({ expectedWell, defaultWell, target, onReady }) {
  const [upload, setUpload] = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState("");
  const uploadRequest = useRef({ revision: 0, controller: null });
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const well = expectedWell || defaultWell;
  const block = upload?.blocks?.length === 1 ? upload.blocks[0] : null;
  const selectionKey = JSON.stringify([upload?.upload_id, block, well, target || null]);
  const spectrum = extracted?.key === selectionKey ? extracted.spectrum : null;

  const installUpload = useCallback((item) => {
    setUpload(item); setExtracted(null);
    setError(item.blocks?.length === 1 ? "" : "请上传只有波长、吸光度两列的单孔 CSV。");
  }, []);

  useEffect(() => () => {
    uploadRequest.current.revision += 1;
    uploadRequest.current.controller?.abort();
  }, []);

  async function uploadFile(file) {
    if (!file) return;
    uploadRequest.current.controller?.abort();
    const revision = ++uploadRequest.current.revision;
    setUpload(null); setExtracted(null); setError("");
    setUploading(false);
    if (!/\.csv$/i.test(file.name)) {
      setError("请上传两列光谱 CSV，例如 base_Blue.csv。");
      return;
    }
    const controller = new AbortController();
    uploadRequest.current.controller = controller;
    setUploading(true);
    try {
      const item = await spectraApi.upload(file, { signal: controller.signal });
      if (revision === uploadRequest.current.revision) installUpload(item);
    } catch (exc) {
      if (revision === uploadRequest.current.revision) setError(exc.message);
    } finally {
      if (revision === uploadRequest.current.revision) setUploading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    if (!upload || !block || !well) { setParsing(false); return; }
    setParsing(true); setError("");
    spectraApi.extract(upload.upload_id, {
      block, well, expected_well: expectedWell || undefined, target_rgb: target || undefined,
    }, { signal: controller.signal }).then((value) => {
      if (current) setExtracted({ key: selectionKey, spectrum: value });
    }).catch((exc) => {
      if (current) setError(exc.message);
    }).finally(() => {
      if (current) setParsing(false);
    });
    return () => { current = false; controller.abort(); };
  }, [selectionKey]);

  useEffect(() => {
    onReadyRef.current?.(spectrum ? { upload_id: upload.upload_id, block, well, spectrum } : null);
  }, [selectionKey, spectrum]);

  return { upload, spectrum, working: uploading || parsing, error, uploadFile };
}
