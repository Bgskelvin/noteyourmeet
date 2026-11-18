export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type MeetingStatus =
  | "QUEUED"
  | "PREPROCESSING"
  | "TRANSCRIBING"
  | "ANALYZING"
  | "DONE"
  | "FAILED"
  | "CANCELLED";

export interface MeetingSummary {
  id: number;
  title: string;
  status: MeetingStatus;
  status_detail: string | null;
  cancel_requested_at: string | null;
  error_message: string | null;
  original_filename: string;
  duration_sec: number | null;
  speaker_count: number | null;
  created_at: string;
}

export interface Speaker {
  id: number;
  label: string;
  display_name: string;
  talk_time_ms: number;
  turn_count: number;
  word_count: number;
}

export interface Segment {
  id: number;
  speaker_id: number | null;
  start_ms: number;
  end_ms: number;
  text: string;
  /** Terisi bila kalimat sudah diedit manual (berisi teks asli dari AI). */
  original_text: string | null;
}

export interface MeetingDetail extends MeetingSummary {
  language: string | null;
  requested_language: string | null;
  min_speakers: number | null;
  max_speakers: number | null;
  processing_started_at: string | null;
  processing_finished_at: string | null;
  speakers: Speaker[];
  segments: Segment[];
}

export interface GlossaryTerm {
  id: number;
  term: string;
}

export interface ReplaceRequest {
  find: string;
  replace: string;
  match_case?: boolean;
  whole_word?: boolean;
  dry_run?: boolean;
}

export const isProcessing = (s: MeetingStatus) => s !== "DONE" && s !== "FAILED" && s !== "CANCELLED";

/** Pilihan bahasa rekaman. Kode lain (mis. "ms", "ja") tetap diterima API. */
export const LANGUAGES = [
  { code: "id", label: "Bahasa Indonesia" },
  { code: "en", label: "English" },
  { code: "auto", label: "Deteksi otomatis" },
] as const;

export const languageLabel = (code: string | null | undefined) =>
  LANGUAGES.find((l) => l.code === code)?.label ?? code ?? "–";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
    } catch {}
    throw new Error(msg);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  listMeetings: () => request<MeetingSummary[]>("/meetings"),
  getMeeting: (id: number) => request<MeetingDetail>(`/meetings/${id}`),
  renameMeeting: (id: number, title: string) =>
    request<MeetingSummary>(`/meetings/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  cancel: (id: number, force = false) =>
    request<MeetingSummary>(`/meetings/${id}/cancel${force ? "?force=true" : ""}`, { method: "POST" }),
  retry: (id: number, language?: string) =>
    request<MeetingSummary>(`/meetings/${id}/retry`, {
      method: "POST",
      body: JSON.stringify(language ? { language } : {}),
    }),
  deleteMeeting: (id: number) => request<void>(`/meetings/${id}`, { method: "DELETE" }),
  renameSpeaker: (id: number, display_name: string) =>
    request<Speaker>(`/speakers/${id}`, { method: "PATCH", body: JSON.stringify({ display_name }) }),
  mergeSpeakers: (meetingId: number, source_ids: number[], target_id: number) =>
    request<MeetingDetail>(`/meetings/${meetingId}/speakers/merge`, {
      method: "POST",
      body: JSON.stringify({ source_ids, target_id }),
    }),
  reassignSegment: (segmentId: number, speakerId: number) =>
    request<MeetingDetail>(`/segments/${segmentId}/speaker?speaker_id=${speakerId}`, { method: "POST" }),
  editSegment: (segmentId: number, text: string) =>
    request<MeetingDetail>(`/segments/${segmentId}`, { method: "PATCH", body: JSON.stringify({ text }) }),
  replaceText: (meetingId: number, body: ReplaceRequest) =>
    request<{ matches: number; segments_changed: number }>(`/meetings/${meetingId}/replace`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listGlossary: () => request<GlossaryTerm[]>("/glossary"),
  addGlossary: (term: string) =>
    request<GlossaryTerm[]>("/glossary", { method: "POST", body: JSON.stringify({ term }) }),
  deleteGlossary: (id: number) => request<void>(`/glossary/${id}`, { method: "DELETE" }),
  audioUrl: (id: number) => `${API_URL}/meetings/${id}/audio`,
};

/** Upload dengan progress bar (fetch belum mendukung progress upload). */
export function uploadMeeting(
  form: FormData,
  onProgress: (pct: number) => void,
): { promise: Promise<MeetingSummary>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<MeetingSummary>((resolve, reject) => {
    xhr.open("POST", `${API_URL}/meetings`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let body: { detail?: unknown } & Partial<MeetingSummary> = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as MeetingSummary);
      else reject(new Error(typeof body.detail === "string" ? body.detail : `Upload gagal (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Tidak bisa terhubung ke server API. Apakah backend sudah jalan?"));
    xhr.onabort = () => reject(new Error("Upload dibatalkan"));
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
