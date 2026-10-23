import { useCallback, useEffect, useRef, useState } from "react";
import { spectraApi } from "../../api/spectra.js";

/** Extract only the current well; ambiguous scans require an explicit choice. */
export function useSpectrumSelection({ expectedWell, defaultWell, target, onReady }) {
  const [upload, setUpload] = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState("");
  const [selectedBlockId, setSelectedBlockId] = useState("");
  const uploadRequest = useRef({ revision: 0, controller: null });
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const well = expectedWell || defaultWell;
  const blocks = (upload?.blocks || []).filter((item) => item.orientation === "csv" || item.wells?.includes(well));
  const block = blocks.length === 1 ? blocks[0] : blocks.find((item) => item.block_id === selectedBlockId) || null;
  const selectionKey = JSON.stringify([upload?.upload_id, block, well, target || null]);
  const spectrum = extracted?.key === selectionKey ? extracted.spectrum : null;

  const installUpload = useCallback((item) => {
    setUpload(item); setExtracted(null); setSelectedBlockId("");
    setError(item.blocks?.length ? "" : "error.noScans");
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
    if (!/\.(csv|xlsx|xls)$/i.test(file.name)) {
      setError("error.spectrumFormat");
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
    onReadyRef.current?.(spectrum?.ready_for_rgb ? { upload_id: upload.upload_id, block, well, spectrum } : null);
  }, [selectionKey, spectrum]);

  return { upload, spectrum, blocks, block, selectedBlockId, selectBlock: setSelectedBlockId,
    normalizedUrl: spectrum ? spectraApi.normalizedUrl(upload.upload_id, block, well) : null,
    working: uploading || parsing, error, uploadFile };
}
