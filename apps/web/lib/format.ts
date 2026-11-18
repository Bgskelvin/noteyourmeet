export function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function humanDuration(sec: number | null | undefined): string {
  if (sec == null) return "–";
  const m = Math.round(sec / 60);
  if (m < 1) return `${Math.round(sec)} dtk`;
  if (m < 60) return `${m} menit`;
  return `${Math.floor(m / 60)} jam ${m % 60} menit`;
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

const SPEAKER_COLORS = [
  { dot: "bg-sky-500", text: "text-sky-700 dark:text-sky-300", soft: "bg-sky-50 dark:bg-sky-950/40" },
  { dot: "bg-amber-500", text: "text-amber-700 dark:text-amber-300", soft: "bg-amber-50 dark:bg-amber-950/40" },
  { dot: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-300", soft: "bg-emerald-50 dark:bg-emerald-950/40" },
  { dot: "bg-rose-500", text: "text-rose-700 dark:text-rose-300", soft: "bg-rose-50 dark:bg-rose-950/40" },
  { dot: "bg-violet-500", text: "text-violet-700 dark:text-violet-300", soft: "bg-violet-50 dark:bg-violet-950/40" },
  { dot: "bg-teal-500", text: "text-teal-700 dark:text-teal-300", soft: "bg-teal-50 dark:bg-teal-950/40" },
  { dot: "bg-orange-500", text: "text-orange-700 dark:text-orange-300", soft: "bg-orange-50 dark:bg-orange-950/40" },
  { dot: "bg-fuchsia-500", text: "text-fuchsia-700 dark:text-fuchsia-300", soft: "bg-fuchsia-50 dark:bg-fuchsia-950/40" },
];

export function speakerColor(label: string) {
  let n = 0;
  for (const ch of label) n = n * 26 + (ch.charCodeAt(0) - 64);
  return SPEAKER_COLORS[(n - 1 + SPEAKER_COLORS.length) % SPEAKER_COLORS.length];
}
