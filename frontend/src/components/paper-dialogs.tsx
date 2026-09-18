"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { BrandingConfig, BrandingProfile, Paper, SeedQuestion } from "@/lib/types";
import { Dialog } from "@/components/dialog";
import { MathContent } from "@/components/math-content";
import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import s from "@/styles/ui.module.css";

export type EditorDialog = "source" | "manual" | "branding" | null;

async function imageAsDataUrl(file: File | null) {
  if (!file?.size) return null;
  if (file.size > 750 * 1024) throw new Error("Use a logo smaller than 750 KB.");
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The selected logo could not be read."));
    reader.readAsDataURL(file);
  });
}

export function PaperDialogs({ kind, paper, onClose, onChanged, toast }: { kind: EditorDialog; paper: Paper; onClose: () => void; onChanged: () => Promise<void>; toast: (message: string, tone?: "default" | "error") => void }) {
  const [sourceQuestions, setSourceQuestions] = useState<SeedQuestion[]>([]);
  const [sourceFilter, setSourceFilter] = useState("");
  const [profiles, setProfiles] = useState<BrandingProfile[]>([]);
  const [branding, setBranding] = useState<BrandingConfig>(paper.branding_config || {});
  const [profileName, setProfileName] = useState("");
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (kind === "source" && !sourceQuestions.length) api.questions(new URLSearchParams({ limit: "100" })).then((result) => setSourceQuestions(result.items)).catch((error) => toast(error.message, "error"));
    if (kind === "branding") { setBranding(paper.branding_config || {}); api.brandingProfiles().then((result) => setProfiles(result.items)).catch((error) => toast(error.message, "error")); }
  }, [kind, paper.branding_config, sourceQuestions.length, toast]);

  const filteredSources = useMemo(() => { const query = sourceFilter.toLowerCase(); return sourceQuestions.filter((question) => !query || `${question.primary_concept || ""} ${question.question_json.stem}`.toLowerCase().includes(query)); }, [sourceFilter, sourceQuestions]);

  async function addSource(question: SeedQuestion) {
    setSubmitting(true);
    try {
      await api.post(`/papers/${paper.id}/questions/manual`, { question_type: "single_correct_mcq", stem: question.question_json.stem, options: question.question_json.options || [], correct_answer: null, solution: null, difficulty: question.difficulty, marks: question.marks || 3, primary_concept: question.primary_concept || null, secondary_concepts: question.secondary_concepts || [], estimated_time_minutes: question.expected_time_minutes || 3, section_id: null });
      await onChanged(); onClose(); toast("Source question added. Verify the answer before export.");
    } catch (caught) { toast(caught instanceof Error ? caught.message : "Couldn’t add the source question.", "error"); }
    finally { setSubmitting(false); }
  }

  async function addManual(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSubmitting(true); const values = new FormData(event.currentTarget);
    try {
      await api.post(`/papers/${paper.id}/questions/manual`, { question_type: "single_correct_mcq", stem: String(values.get("stem") || "").trim(), options: [0, 1, 2, 3].map((index) => String(values.get(`option${index}`) || "").trim()), correct_answer: String(values.get("correct_answer") || "").trim() || null, solution: null, difficulty: Number(values.get("difficulty")), marks: Number(values.get("marks")), primary_concept: null, secondary_concepts: [], estimated_time_minutes: null, section_id: String(values.get("section_id") || "") || null });
      await onChanged(); onClose(); toast("Manual question added.");
    } catch (caught) { toast(caught instanceof Error ? caught.message : "Couldn’t add the question.", "error"); }
    finally { setSubmitting(false); }
  }

  async function saveBranding(saveProfile: boolean) {
    if (saveProfile && !profileName.trim()) { toast("Enter a profile name before saving reusable branding.", "error"); return; }
    setSubmitting(true);
    try {
      const logo_data_url = await imageAsDataUrl(logoFile) || branding.logo_data_url || null;
      const nextBranding = { ...branding, logo_data_url, duration_minutes: Number(branding.duration_minutes) || null, total_marks: Number(branding.total_marks) || null, instructions: branding.instructions || [] };
      await api.updatePaper(paper.id, { branding_config: nextBranding });
      if (saveProfile) await api.saveBrandingProfile({ name: profileName.trim(), branding_config: nextBranding });
      await onChanged(); onClose(); toast("Branding saved for future exports.");
    } catch (caught) { toast(caught instanceof Error ? caught.message : "Couldn’t save branding.", "error"); }
    finally { setSubmitting(false); }
  }

  const patchBranding = <K extends keyof BrandingConfig>(key: K, value: BrandingConfig[K]) => setBranding((current) => ({ ...current, [key]: value }));
  return <>
    <Dialog open={kind === "source"} title="Seed question bank" subtitle="Add a classified seed question without inventing an answer." onClose={onClose} wide><div className={s.modalBody}><Field label="Filter questions"><Input value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} placeholder="Search a concept or question text" /></Field><div className={s.sourceList}>{filteredSources.map((question) => <article className={s.sourceItem} key={question.id}><div className={s.chipRow}><span className={s.chip}>Source Q{question.source_reference?.match(/question (\d+)/i)?.[1] || ""}</span><span className={s.chip}>Difficulty {question.difficulty}/5</span><span className={s.chip}>{question.primary_concept || "Classified seed"}</span></div><MathContent as="p" value={question.question_json.stem} /><footer><span>{question.question_json.options?.length || 0} options · answer not verified</span><Button tone="primary" size="small" disabled={submitting} onClick={() => void addSource(question)}>Add to paper</Button></footer></article>)}</div></div></Dialog>

    <Dialog open={kind === "manual"} title="Add manual question" subtitle="Single-correct MCQ with four choices." onClose={onClose}><form className={`${s.modalBody} ${s.formGrid}`} onSubmit={addManual}><Field label="Question stem"><Textarea name="stem" required placeholder="Write the question stem" /></Field><Field label="Options"><div className={s.optionFields}>{["A", "B", "C", "D"].map((letter, index) => <label key={letter}><span>{letter}</span><Input name={`option${index}`} required /></label>)}</div></Field><div className={s.twoCol}><Field label="Correct answer"><Input name="correct_answer" placeholder="A, B, C, or D" /></Field><Field label="Section"><Select name="section_id"><option value="">Unsectioned</option>{paper.sections.map((section) => <option key={section.id} value={section.id}>{section.title}</option>)}</Select></Field></div><div className={s.twoCol}><Field label="Difficulty"><Input type="number" name="difficulty" min={1} max={5} defaultValue={3} /></Field><Field label="Marks"><Input type="number" name="marks" min={1} max={100} defaultValue={4} /></Field></div><div className={s.modalActions}><Button type="button" onClick={onClose}>Cancel</Button><Button tone="primary" type="submit" disabled={submitting}>{submitting ? "Adding…" : "Add question"}</Button></div></form></Dialog>

    <Dialog open={kind === "branding"} title="Branding, header & footer" subtitle="Saved branding is included in DOCX and PDF exports." onClose={onClose} wide><div className={`${s.modalBody} ${s.formGrid}`}><div className={s.brandingIntro}>{branding.logo_data_url ? <img src={branding.logo_data_url} alt="Current academy logo" /> : <span className={s.logoPlaceholder}>Logo</span>}<div><strong>{branding.institution_name || "Paper branding"}</strong><small>Configure your academy identity and document chrome.</small></div></div><div className={s.twoCol}><Field label="Use a saved profile"><Select value="" onChange={(event) => { const profile = profiles.find((item) => item.id === event.target.value); if (profile) setBranding(profile.branding_config); }}><option value="">Current paper branding</option>{profiles.map((profile) => <option value={profile.id} key={profile.id}>{profile.name}</option>)}</Select></Field><Field label="Save as reusable profile"><Input value={profileName} onChange={(event) => setProfileName(event.target.value)} placeholder="e.g. Apex Academy standard" /></Field></div><div className={s.twoCol}><Field label="Academy / institution name"><Input value={branding.institution_name || ""} onChange={(event) => patchBranding("institution_name", event.target.value)} /></Field><Field label="Logo"><Input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setLogoFile(event.target.files?.[0] || null)} /></Field></div><Field label="Address"><Textarea value={branding.address || ""} onChange={(event) => patchBranding("address", event.target.value)} /></Field><div className={s.twoCol}><Field label="Phone / email"><Input value={branding.contact || ""} onChange={(event) => patchBranding("contact", event.target.value)} /></Field><Field label="Duration (minutes)"><Input type="number" min={1} value={branding.duration_minutes || ""} onChange={(event) => patchBranding("duration_minutes", Number(event.target.value) || null)} /></Field></div><div className={s.twoCol}><Field label="Total marks"><Input type="number" min={1} value={branding.total_marks || ""} onChange={(event) => patchBranding("total_marks", Number(event.target.value) || null)} /></Field><Field label="Watermark"><Input value={branding.watermark_text || ""} onChange={(event) => patchBranding("watermark_text", event.target.value)} /></Field></div><Field label="Header text"><Input value={branding.header_text || ""} onChange={(event) => patchBranding("header_text", event.target.value)} /></Field><Field label="Footer text"><Input value={branding.footer_text || ""} onChange={(event) => patchBranding("footer_text", event.target.value)} /></Field><Field label="Instructions (one per line)"><Textarea value={(branding.instructions || []).join("\n")} onChange={(event) => patchBranding("instructions", event.target.value.split("\n").map((line) => line.trim()).filter(Boolean))} /></Field><div className={s.modalActions}><Button onClick={onClose}>Cancel</Button><Button disabled={submitting} onClick={() => void saveBranding(true)}>Save as profile</Button><Button tone="primary" disabled={submitting} onClick={() => void saveBranding(false)}>{submitting ? "Saving…" : "Save branding"}</Button></div></div></Dialog>
  </>;
}
