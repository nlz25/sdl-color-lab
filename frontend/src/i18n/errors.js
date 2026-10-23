import { messages, translate } from "./messages.js";

const rules = [
  [/CSV 须包含波长|仅支持.*(?:xlsx|xls)/, "error.spectrumFormat"],
  [/请上传只有波长、吸光度两列的单孔 CSV/, "error.singleCsv"],
  [/请上传两列光谱 CSV/, "error.csvFormat"],
  [/上传文件为空/, "error.empty"],
  [/超过 25 MB/, "error.large"],
  [/完整覆盖.*380.*780|Spectrum must cover the complete/, "error.range"],
  [/波长间距不能超过|wavelength.*(?:gap|spacing).*10|Wavelength spacing/i, "error.spacing"],
  [/严格递增|不能重复|Wavelengths must be strictly/i, "error.order"],
  [/缺失或不是有效数字|不是有效数字|必须是有限数值|NaN|无穷大|finite one-dimensional arrays/, "error.numeric"],
  [/吸光度包含负值/, "error.negative"],
  [/至少需要两个波长|数量必须一致/, "error.points"],
  [/CSV 第 (\d+) 行必须恰好/, "error.columns", (match) => ({ row: match[1] })],
  [/请先在本机.*OPENAI_API_KEY/, "error.key"],
  [/模型连接检查失败（(.+?)）/, "error.model", (match) => ({ detail: match[1] })],
  [/模型标识必须/, "error.modelId"],
  [/API 地址须为/, "error.endpoint"],
  [/请先完成模型连接检查|请先对所选模型.*连接检查/, "error.preflight"],
  [/正在处理另一项操作|另一进程正在操作|工作流仍被锁定/, "error.busy"],
  [/实验不存在|实验目录不存在/, "error.missingSession"],
  [/上传文件不存在/, "error.missingUpload"],
  [/同一条光谱/, "error.sameCalibration"],
  [/新实验不使用基色标定/, "error.noCalibration"],
  [/校验失败|哈希与解析结果不一致|颜色结果与原始光谱不一致|光谱来源校验失败/, "error.source"],
  [/不同测量，不能覆盖|已有待提交测量归档|Conflicting measurement/, "error.conflict"],
  [/(?:必须上传当前孔|当前待测孔|当前文件缺少)\s*([A-H]\d{1,2})/, "error.well", (match) => ({ well: match[1] })],
  [/页面来源与本地服务不一致，请通过\s*(\S+)\s*重新/, "error.origin", (match) => ({ url: match[1] })],
  [/请求缺少页面来源.*请通过\s*(\S+)\s*重新/, "error.noOrigin", (match) => ({ url: match[1] })],
  [/拒绝跨站操作/, "error.crossSite"],
  [/实验记录已保留/, "error.saved"],
  [/请求格式有误，请检查：(.*)/, "error.input", (match) => ({ fields: match[1] })],
  [/十二次实验已经完成|不能生成第七轮/, "error.finished"],
  [/当前实验已固定模型/, "error.lockedMethod"],
  [/当前方法已切换|当前轮次已推进/, "error.staleMethod"],
  [/请对实验固定的 GPT 模型/, "error.fixedModel"],
  [/请先生成当前配方|当前没有待执行配方/, "error.startRecipe"],
  [/无法自动打开 CSV 文件夹/, "error.openFolder"],
  [/实际测量时间|归档测量时间|填写时间|重试的测量时间|completed_at_utc/, "error.invalidTime"],
  [/Failed to fetch|Load failed|NetworkError|fetch failed/i, "error.network"],
  [/(?:Request failed|请求未完成)\s*\((\d+)\)/, "error.request", (match) => ({ status: match[1] })],
];

export function localizeError(source, language = "en") {
  const text = String(source);
  if (messages.en[text]) return { message: translate(language, text) };
  for (const [pattern, key, params] of rules) {
    const match = text.match(pattern);
    if (match) return { message: translate(language, key, params?.(match)), details: text };
  }
  if (language === "en") {
    const unwrapped = text.replace(/^操作未完成，请核对输入：/, "");
    if (!/[\u4e00-\u9fff]/.test(unwrapped)) return { message: unwrapped };
  } else if (/[\u4e00-\u9fff]/.test(text)) return { message: text };
  return { message: translate(language, "error.generic"), details: text };
}
