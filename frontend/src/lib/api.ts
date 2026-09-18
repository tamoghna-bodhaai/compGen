import type {
  BrandingProfile,
  CatalogRow,
  IngestionJob,
  Paper,
  PaperSummary,
  SeedQuestion,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers || {}),
    },
  });
  if (!response.ok) {
    let message = "Something went wrong.";
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail || message;
    } catch {
      // The API sometimes returns an empty body for transport failures.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  papers: (signal?: AbortSignal) => apiRequest<{ items: PaperSummary[] }>("/papers", { signal }),
  paper: (id: string) => apiRequest<Paper>(`/papers/${id}`),
  createPaper: (body: unknown) => apiRequest<Paper>("/papers", { method: "POST", body: JSON.stringify(body) }),
  updatePaper: (id: string, body: unknown) => apiRequest<Paper>(`/papers/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  catalog: () => apiRequest<{ items: CatalogRow[] }>("/questions/catalog"),
  ingestionJobs: (signal?: AbortSignal) => apiRequest<{ items: IngestionJob[] }>("/questions/ingestion-jobs", { signal }),
  ingest: (body: FormData) => apiRequest<{ job: IngestionJob }>("/questions/ingest", { method: "POST", body }),
  questions: (query: URLSearchParams) => apiRequest<{ items: SeedQuestion[]; total: number; offset: number }>(`/questions?${query}`),
  question: (id: string) => apiRequest<SeedQuestion>(`/questions/${id}`),
  brandingProfiles: () => apiRequest<{ items: BrandingProfile[] }>("/branding-profiles"),
  saveBrandingProfile: (body: unknown) => apiRequest<BrandingProfile>("/branding-profiles", { method: "POST", body: JSON.stringify(body) }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) }),
  put: <T>(path: string, body: unknown) => apiRequest<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
};

export async function downloadPaper(paper: Paper | PaperSummary, format: "pdf" | "docx", variant: "question_paper" | "answer_key") {
  const response = await fetch(`/api/papers/${paper.id}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format, variant }),
  });
  if (!response.ok) {
    let message = "Export failed.";
    try { message = ((await response.json()) as { detail?: string }).detail || message; } catch { /* empty response */ }
    throw new ApiError(message, response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${paper.title}.${format}`;
  anchor.click();
  URL.revokeObjectURL(url);
}
