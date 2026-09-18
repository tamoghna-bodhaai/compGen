import { PaperEditorScreen } from "@/components/paper-editor-screen";

export default async function PaperPage({ params }: { params: Promise<{ paperId: string }> }) {
  const { paperId } = await params;
  return <PaperEditorScreen paperId={decodeURIComponent(paperId)} />;
}
