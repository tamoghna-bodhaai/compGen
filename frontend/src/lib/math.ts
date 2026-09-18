export function normaliseLatex(value = "") {
  return String(value)
    .replaceAll("\\\\", "\\")
    .replaceAll("\\u0000", "")
    .replaceAll("\u0000", "")
    .replace(/\f(?=rac\b)/g, String.raw`\f`)
    .replace(/\t(?=(?:an|ext)\b)/g, String.raw`\t`)
    .replace(/\u0008(?=(?:egin|ox|inom)\b)/g, String.raw`\b`)
    .replace(/\r(?=ight\b)/g, String.raw`\r`)
    .replace(/\u0007(?=sqrt(?:\b|\d))/g, "\\")
    .replace(/[\u0001-\u0008\u000b-\u001f](?=[A-Za-z])/g, "\\");
}
