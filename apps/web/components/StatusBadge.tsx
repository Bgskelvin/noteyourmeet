import type { MeetingStatus } from "@/lib/api";

const LABEL: Record<MeetingStatus, string> = {
  QUEUED: "Antre",
  PREPROCESSING: "Konversi audio",
  TRANSCRIBING: "Transkripsi",
  ANALYZING: "Analisis",
  DONE: "Selesai",
  FAILED: "Gagal",
  CANCELLED: "Dibatalkan",
};

const STYLE: Record<MeetingStatus, string> = {
  QUEUED: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
  PREPROCESSING: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  TRANSCRIBING: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  ANALYZING: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  DONE: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  CANCELLED: "bg-neutral-200 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
};

export function StatusBadge({ status }: { status: MeetingStatus }) {
  const busy = !["DONE", "FAILED", "CANCELLED", "QUEUED"].includes(status);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLE[status]}`}>
      {busy && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {LABEL[status]}
    </span>
  );
}

export const PIPELINE_STEPS: { key: MeetingStatus; label: string }[] = [
  { key: "QUEUED", label: "Antre" },
  { key: "PREPROCESSING", label: "Konversi audio" },
  { key: "TRANSCRIBING", label: "Suara → teks & deteksi pembicara" },
  { key: "ANALYZING", label: "Statistik pembicara" },
  { key: "DONE", label: "Selesai" },
];
