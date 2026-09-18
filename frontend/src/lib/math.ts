export function normaliseLatex(value = "") {
  return String(value)
    .replaceAll("\\\\", "\\")
    .replace(/\f(?=rac\b)/g, String.raw`\f`)
    .replace(/\t(?=(?:an|ext)\b)/g, String.raw`\t`)
    .replace(/\u0008(?=(?:egin|ox)\b)/g, String.raw`\b`)
    .replace(/\r(?=ight\b)/g, String.raw`\r`)
    .replace(/\u0007(?=sqrt(?:\b|\d))/g, "\\");
}
