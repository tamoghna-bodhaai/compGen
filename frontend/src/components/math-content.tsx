"use client";

import katex from "katex";
import { normaliseLatex } from "@/lib/math";

function escapeHtml(value: string) {
  return value.replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char] || char);
}

export function renderMathHtml(value = "") {
  const source = normaliseLatex(value);
  const delimiters = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+\$)/g;
  let result = "";
  let cursor = 0;
  for (const match of source.matchAll(delimiters)) {
    result += escapeHtml(source.slice(cursor, match.index)).replaceAll("\n", "<br>");
    const token = match[0];
    let tex = token;
    let displayMode = false;
    if (token.startsWith("$$")) { tex = token.slice(2, -2); displayMode = true; }
    else if (token.startsWith("\\[")) { tex = token.slice(2, -2); displayMode = true; }
    else if (token.startsWith("\\(")) tex = token.slice(2, -2);
    else tex = token.slice(1, -1);
    try { result += katex.renderToString(tex, { throwOnError: false, displayMode, output: "html" }); }
    catch { result += escapeHtml(token); }
    cursor = (match.index || 0) + token.length;
  }
  return result + escapeHtml(source.slice(cursor)).replaceAll("\n", "<br>");
}

export function MathContent({ value, className = "", as: Tag = "span" }: { value?: string | null; className?: string; as?: "span" | "div" | "p" }) {
  return <Tag className={`mathContent ${className}`} dangerouslySetInnerHTML={{ __html: renderMathHtml(value || "") }} />;
}
