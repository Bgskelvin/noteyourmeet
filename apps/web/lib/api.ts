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
  /** True = diubah otomatis oleh memori koreksi. */
  auto_corrected: boolean | null;
  /** Terisi = sudah diperiksa user (benar / sudah dikoreksi). */
  reviewed_at: string | null;
}

export interface MeetingDetail extends MeetingSummary {
  language: string | null;
  requested_language: string | null;
  processing_info: ProcessingInfo | null;
  min_speakers: number | null;
  max_speakers: number | null;
  processing_started_at: string | null;
  processing_finished_at: string | null;
  speakers: Speaker[];
  segments: Segment[];
}

export interface ProcessingInfo {
  code_version?: string | null;
  provider?: string;
  whisper_model?: string;
  compute_type?: string;
  batch_size?: number;
  device?: string;
  language_requested?: string;
  language_detected?: string;
  align_model?: string;
  hotwords?: string[];
  min_speakers?: number | null;
  max_speakers?: number | null;
  speaker_rules?: { min_run_words: number; min_run_ms: number };
  timings_sec?: { preprocess?: number; transcribe?: number; analyze?: number };
}

export interface CorrectionRule {
  id: number;
  find: string;
  replace: string;
  whole_word: boolean;
  match_case: boolean;
  enabled: boolean;
  times_applied: number;
}

export interface Suggestions {
  terms: { term: string; count: number; example: string }[];
  rules: { find: string; replace: string; count: number; example: string }[];
}

export interface ReviewStats {
  meetings: {
    id: number;
    title: string;
    duration_sec: number | null;
    total_segments: number;
    reviewed_segments: number;
    reviewed_ms: number;
  }[];
  reviewed_ms_total: number;
  reviewed_segments_total: number;
  training: { usable_segments: number; usable_minutes: number; target_hours: number; progress_pct: number };
}

export interface LearnResult {
  rule_id: number;
  /** Kata benar ada di kosakata Whisper (nama/singkatan). */
  heard_by_whisper: boolean;
  glossary_added: boolean;
  matches: number;
  segments_changed: number;
}

export interface DictionaryEntry {
  word: string;
  /** Terisi = dikenali Whisper (hotwords). */
  glossary_id: number | null;
  variants: { rule_id: number; find: string; enabled: boolean; times_applied: number }[];
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
  /** Simpan sebagai memori koreksi untuk meeting berikutnya. */
  remember?: boolean;
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

/** Error dari API, membawa kode status (mis. 409 = perlu konfirmasi). */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

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
    throw new ApiError(msg, res.status);
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
  listCorrections: () => request<CorrectionRule[]>("/corrections"),
  addCorrection: (find: string, replace: string) =>
    request<CorrectionRule>("/corrections", { method: "POST", body: JSON.stringify({ find, replace }) }),
  setCorrectionEnabled: (id: number, enabled: boolean) =>
    request<CorrectionRule>(`/corrections/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  deleteCorrection: (id: number) => request<void>(`/corrections/${id}`, { method: "DELETE" }),
  applyCorrections: (meetingId: number) =>
    request<{ matches: number; segments_changed: number }>(`/meetings/${meetingId}/apply-corrections`, {
      method: "POST",
    }),
  suggestions: () => request<Suggestions>("/suggestions"),
  reviewSegment: (segmentId: number, reviewed = true) =>
    request<Segment>(`/segments/${segmentId}/review`, { method: "POST", body: JSON.stringify({ reviewed }) }),
  reviewStats: () => request<ReviewStats>("/review/stats"),
  /** Satu aksi "Perbaiki": ingat koreksi, nama/singkatan otomatis jadi kosakata Whisper. 409 = kata terlalu umum. */
  learn: (body: {
    find: string;
    replace: string;
    meeting_id?: number;
    apply_to_meeting?: boolean;
    whole_word?: boolean;
    confirm_common?: boolean;
  }) => request<LearnResult>("/learn", { method: "POST", body: JSON.stringify(body) }),
  dictionary: () => request<DictionaryEntry[]>("/dictionary"),
  deleteDictionaryWord: (word: string) =>
    request<void>(`/dictionary?word=${encodeURIComponent(word)}`, { method: "DELETE" }),
  dismissSuggestion: (kind: "term" | "rule", value: string) =>
    request<void>("/suggestions/dismiss", { method: "POST", body: JSON.stringify({ kind, value }) }),
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
