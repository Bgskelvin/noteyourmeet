"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  isProcessing,
  LANGUAGES,
  languageLabel,
  type MeetingDetail,
  type ProcessingInfo,
  type Segment,
  type Speaker,
} from "@/lib/api";
import { clock, dateTime, humanDuration, speakerColor } from "@/lib/format";
import { buildMatcher, countMatches } from "@/lib/textmatch";
import { PIPELINE_STEPS, StatusBadge } from "./StatusBadge";

export function MeetingView() {
  const { id } = useParams<{ id: string }>();
  const meetingId = Number(id);
  const router = useRouter();
  const [m, setM] = useState<MeetingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setM(await api.getMeeting(meetingId));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [meetingId]);

  useEffect(() => {
    const t = setTimeout(load, 0); // muat awal (di callback, bukan langsung di effect)
    return () => clearTimeout(t);
  }, [load]);

  const busy = m ? isProcessing(m.status) : false;
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [busy, load]);

  async function run<T>(fn: () => Promise<T>) {
    try {
      return await fn();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  if (error && !m) return <p className="text-red-600">Gagal memuat meeting: {error}</p>;
  if (!m) return <p className="text-neutral-500">Memuat…</p>;

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← Semua meeting
      </Link>

      <header className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <EditableTitle
            value={m.title}
            onSave={(t) => run(async () => setM({ ...m, ...(await api.renameMeeting(m.id, t)) }))}
          />
          <p className="mt-1 text-sm text-neutral-500">
            {dateTime(m.created_at)} · {humanDuration(m.duration_sec)} · {m.original_filename}
            {m.language && ` · bahasa: ${languageLabel(m.language)}`}
            {m.language && m.requested_language === "auto" && " (terdeteksi otomatis)"}
          </p>
        </div>
        <StatusBadge status={m.status} />
        {busy && (
          <CancelControl
            m={m}
            onCancel={(force) =>
              confirm(
                force
                  ? "Worker belum merespons. Paksa batalkan? Jika worker ternyata masih jalan, GPU-nya baru bebas setelah worker selesai/ditutup."
                  : "Batalkan proses meeting ini? Hasil yang sudah setengah jalan tidak disimpan.",
              ) &&
              run(async () => {
                await api.cancel(m.id, force);
                await load();
              })
            }
          />
        )}
        {(m.status === "DONE" || m.status === "FAILED" || m.status === "CANCELLED") && (
          <ReprocessControl
            m={m}
            onReprocess={(lang) =>
              (m.status !== "DONE" || confirm("Proses ulang? Nama pembicara & koreksi manual akan hilang.")) &&
              run(async () => {
                await api.retry(m.id, lang);
                await load();
              })
            }
          />
        )}
        {!busy && (
          <button
            className="rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40"
            onClick={() =>
              confirm("Hapus meeting ini beserta file audionya? Tidak bisa dibatalkan.") &&
              run(async () => {
                await api.deleteMeeting(m.id);
                router.push("/");
              })
            }
          >
            Hapus
          </button>
        )}
      </header>

      {busy && <ProgressPanel m={m} />}
      {m.status === "FAILED" && (
        <div className="rounded-xl bg-red-50 p-4 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-300">
          <p className="font-medium">Proses gagal</p>
          <p className="mt-1 font-mono text-xs whitespace-pre-wrap">{m.error_message}</p>
        </div>
      )}
      {m.status === "CANCELLED" && (
        <div className="rounded-xl bg-neutral-100 p-4 text-sm text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
          <p className="font-medium">Proses dibatalkan</p>
          <p className="mt-1">Pilih bahasa lalu klik “Proses lagi” untuk memulai ulang, atau “Hapus” jika tidak diperlukan.</p>
        </div>
      )}
      {m.status === "DONE" && <TranscriptWorkspace m={m} setM={setM} run={run} />}
      {!busy && m.processing_info && <ProcessingInfoPanel info={m.processing_info} />}
    </div>
  );
}

function ProcessingInfoPanel({ info }: { info: ProcessingInfo }) {
  const t = info.timings_sec ?? {};
  const rows: [string, React.ReactNode][] = [
    ["Versi kode", info.code_version ?? "–"],
    ["Mesin transkripsi", `${info.provider ?? "–"} · ${info.whisper_model ?? "–"} (${info.compute_type ?? "–"}, batch ${info.batch_size ?? "–"}, ${info.device ?? "–"})`],
    ["Bahasa", `diminta: ${languageLabel(info.language_requested)} · terdeteksi: ${languageLabel(info.language_detected)}`],
    ["Model timestamp kata", info.align_model ?? "–"],
    ["Perkiraan peserta", info.min_speakers || info.max_speakers ? `${info.min_speakers ?? "?"}–${info.max_speakers ?? "?"}` : "otomatis"],
    ["Kosakata tim", info.hotwords?.length ? info.hotwords.join(", ") : "(kosong)"],
    ["Aturan pembicara", info.speaker_rules ? `potongan < ${info.speaker_rules.min_run_words} kata / < ${info.speaker_rules.min_run_ms} ms ikut tetangga` : "–"],
    ["Durasi proses", ["preprocess", "transcribe", "analyze"].map((k) => `${k}: ${t[k as keyof typeof t] ?? "–"} dtk`).join(" · ")],
  ];
  return (
    <details className="rounded-xl border border-neutral-200 text-sm dark:border-neutral-800">
      <summary className="cursor-pointer select-none px-4 py-2.5 text-neutral-600 dark:text-neutral-400">
        Detail proses <span className="text-xs">(untuk melacak masalah & membandingkan hasil)</span>
      </summary>
      <dl className="grid gap-x-6 gap-y-1.5 border-t border-neutral-200 px-4 py-3 sm:grid-cols-[max-content_1fr] dark:border-neutral-800">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-neutral-500">{k}</dt>
            <dd className="break-words font-mono text-xs leading-5">{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

const FORCE_AFTER_MS = 60_000;

function CancelControl({ m, onCancel }: { m: MeetingDetail; onCancel: (force: boolean) => void }) {
  // Tombol "Paksa batalkan" baru muncul jika worker belum berhenti 60 dtk setelah diminta
  const [canForce, setCanForce] = useState(false);
  useEffect(() => {
    if (!m.cancel_requested_at) return;
    const wait = Math.max(0, new Date(m.cancel_requested_at).getTime() + FORCE_AFTER_MS - Date.now());
    const t = setTimeout(() => setCanForce(true), wait);
    return () => clearTimeout(t);
  }, [m.cancel_requested_at]);

  const btn = "rounded-lg border px-3 py-1.5 text-sm disabled:cursor-wait disabled:opacity-60";
  if (!m.cancel_requested_at)
    return (
      <button
        className={`${btn} border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900`}
        onClick={() => onCancel(false)}
      >
        Batalkan
      </button>
    );
  return canForce ? (
    <button
      className={`${btn} border-amber-400 text-amber-800 hover:bg-amber-50 dark:border-amber-800 dark:text-amber-300 dark:hover:bg-amber-950/40`}
      onClick={() => onCancel(true)}
    >
      Paksa batalkan
    </button>
  ) : (
    <button className={`${btn} border-neutral-300 dark:border-neutral-700`} disabled>
      Membatalkan…
    </button>
  );
}

function ReprocessControl({ m, onReprocess }: { m: MeetingDetail; onReprocess: (lang: string) => void }) {
  const [lang, setLang] = useState(m.requested_language ?? m.language ?? "id");
  return (
    <div className="flex items-center overflow-hidden rounded-lg border border-neutral-300 text-sm dark:border-neutral-700">
      <select
        aria-label="Bahasa untuk proses ulang"
        className="bg-transparent px-2 py-1.5 outline-none"
        value={lang}
        onChange={(e) => setLang(e.target.value)}
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
        {!LANGUAGES.some((l) => l.code === lang) && <option value={lang}>{lang}</option>}
      </select>
      <button
        className="border-l border-neutral-300 px-3 py-1.5 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900"
        onClick={() => onReprocess(lang)}
      >
        {m.status === "FAILED" ? "Coba lagi" : m.status === "CANCELLED" ? "Proses lagi" : "Proses ulang"}
      </button>
    </div>
  );
}

function EditableTitle({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState(value);
  if (!editing)
    return (
      <h1 className="group cursor-text text-2xl font-semibold" onClick={() => (setV(value), setEditing(true))} title="Klik untuk ganti judul">
        {value} <span className="text-sm font-normal text-neutral-400 opacity-0 group-hover:opacity-100">✎</span>
      </h1>
    );
  const save = () => {
    setEditing(false);
    if (v.trim() && v.trim() !== value) onSave(v.trim());
  };
  return (
    <input
      autoFocus
      className="w-full rounded-lg border border-neutral-300 bg-transparent px-2 py-1 text-2xl font-semibold dark:border-neutral-700"
      value={v}
      onChange={(e) => setV(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => e.key === "Enter" ? save() : e.key === "Escape" && setEditing(false)}
    />
  );
}

function ProgressPanel({ m }: { m: MeetingDetail }) {
  const current = PIPELINE_STEPS.findIndex((s) => s.key === m.status);
  return (
    <div className="rounded-2xl border border-neutral-200 p-5 dark:border-neutral-800">
      <ol className="space-y-3">
        {PIPELINE_STEPS.map((s, i) => (
          <li key={s.key} className="flex items-center gap-3 text-sm">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
                i < current
                  ? "bg-emerald-500 text-white"
                  : i === current
                    ? "animate-pulse bg-blue-600 text-white"
                    : "bg-neutral-200 text-neutral-500 dark:bg-neutral-800"
              }`}
            >
              {i < current ? "✓" : i + 1}
            </span>
            <span className={i === current ? "font-medium" : i > current ? "text-neutral-500" : ""}>{s.label}</span>
            {i === current && m.status_detail && <span className="text-neutral-500">— {m.status_detail}</span>}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-xs text-neutral-500">
        Halaman ini diperbarui otomatis. Perkiraan: 1 jam audio ≈ 20–25 menit di GTX 1660 Ti. Pastikan worker sedang berjalan.
      </p>
    </div>
  );
}

type Run = <T>(fn: () => Promise<T>) => Promise<T | undefined>;

function TranscriptWorkspace({ m, setM, run }: { m: MeetingDetail; setM: (m: MeetingDetail) => void; run: Run }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [nowMs, setNowMs] = useState(0);
  const [follow, setFollow] = useState(true);
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);

  const speakers = useMemo(() => new Map(m.speakers.map((s) => [s.id, s])), [m.speakers]);
  const activeId = useMemo(() => {
    let id: number | null = null;
    for (const s of m.segments) {
      if (s.start_ms <= nowMs) id = s.id;
      else break;
    }
    return id;
  }, [m.segments, nowMs]);

  useEffect(() => {
    if (!follow || activeId == null || audioRef.current?.paused) return;
    document.getElementById(`seg-${activeId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeId, follow]);

  const seek = (ms: number) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = ms / 1000;
    a.play().catch(() => {});
  };

  const [showReplace, setShowReplace] = useState(false);
  const [replaceWith, setReplaceWith] = useState("");
  const [wholeWord, setWholeWord] = useState(true);
  const [addToGlossary, setAddToGlossary] = useState(true);
  const [replacing, setReplacing] = useState(false);

  const q = query.trim().toLowerCase();
  const matcher = useMemo(
    () => (showReplace ? buildMatcher(query, { matchCase: false, wholeWord }) : null),
    [showReplace, query, wholeWord],
  );
  const visible = matcher
    ? m.segments.filter((s) => s.text.search(new RegExp(matcher.source, matcher.flags.replace("g", ""))) >= 0)
    : q
      ? m.segments.filter((s) => s.text.toLowerCase().includes(q))
      : m.segments;
  const matchCount = useMemo(() => countMatches(m.segments.map((s) => s.text), matcher), [m.segments, matcher]);

  async function replaceAll() {
    const find = query.trim();
    const repl = replaceWith.trim();
    if (!find || !matchCount) return;
    if (!confirm(`Ganti ${matchCount} kemunculan "${find}" menjadi "${repl || "(kosong)"}"?`)) return;
    setReplacing(true);
    await run(async () => {
      await api.replaceText(m.id, { find, replace: repl, whole_word: wholeWord });
      if (addToGlossary && repl) await api.addGlossary(repl);
      setM(await api.getMeeting(m.id));
      setQuery(repl);
    });
    setReplacing(false);
  }

  function copyTranscript() {
    const txt = m.segments
      .map((s) => `[${clock(s.start_ms)}] ${speakers.get(s.speaker_id ?? -1)?.display_name ?? "?"}: ${s.text}`)
      .join("\n");
    navigator.clipboard.writeText(`${m.title}\n\n${txt}`).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <SpeakerPanel m={m} setM={setM} run={run} />
      </aside>

      <section className="min-w-0 space-y-3">
        <div className="sticky top-0 z-10 space-y-2 border-b border-neutral-200 bg-[var(--background)] pb-3 pt-2 dark:border-neutral-800">
          <audio
            ref={audioRef}
            src={api.audioUrl(m.id)}
            controls
            preload="metadata"
            className="w-full"
            onTimeUpdate={(e) => setNowMs(e.currentTarget.currentTime * 1000)}
          />
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <input
              className="min-w-40 flex-1 rounded-lg border border-neutral-300 bg-transparent px-3 py-1.5 dark:border-neutral-700"
              placeholder={showReplace ? "Kata yang salah, mis. CSILC" : "Cari di transkrip…"}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              className={`rounded-lg border px-3 py-1.5 ${
                showReplace
                  ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
                  : "border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900"
              }`}
              onClick={() => setShowReplace((v) => !v)}
              aria-pressed={showReplace}
            >
              Ganti kata
            </button>
            <label className="flex items-center gap-1.5 text-neutral-600 dark:text-neutral-400">
              <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Ikuti audio
            </label>
            <button className="rounded-lg border border-neutral-300 px-3 py-1.5 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900" onClick={copyTranscript}>
              {copied ? "Tersalin ✓" : "Salin transkrip"}
            </button>
          </div>
          {showReplace && (
            <div className="space-y-2 rounded-lg bg-neutral-50 p-3 text-sm dark:bg-neutral-900">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-neutral-500">Ganti dengan</span>
                <input
                  className="min-w-40 flex-1 rounded-lg border border-neutral-300 bg-[var(--background)] px-3 py-1.5 dark:border-neutral-700"
                  placeholder="Kata yang benar, mis. CS ALC"
                  value={replaceWith}
                  onChange={(e) => setReplaceWith(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && replaceAll()}
                />
                <button
                  className="rounded-lg bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={!matchCount || replacing}
                  onClick={replaceAll}
                >
                  {replacing ? "Mengganti…" : `Ganti semua (${matchCount})`}
                </button>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600 dark:text-neutral-400">
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={wholeWord} onChange={(e) => setWholeWord(e.target.checked)} /> Kata utuh saja
                </label>
                <label className="flex items-center gap-1.5" title="Agar Whisper menulis kata ini dengan benar di meeting berikutnya">
                  <input type="checkbox" checked={addToGlossary} onChange={(e) => setAddToGlossary(e.target.checked)} /> Tambahkan kata
                  yang benar ke Kosakata tim
                </label>
              </div>
            </div>
          )}
          {q && <p className="text-xs text-neutral-500">{showReplace ? `${matchCount} kemunculan di ${visible.length} kalimat` : `${visible.length} hasil`}</p>}
        </div>

        <ol className="space-y-1">
          {visible.map((s) => (
            <SegmentRow
              key={s.id}
              seg={s}
              speaker={speakers.get(s.speaker_id ?? -1)}
              speakers={m.speakers}
              active={s.id === activeId}
              onSeek={() => seek(s.start_ms)}
              onReassign={(spId) => run(async () => setM(await api.reassignSegment(s.id, spId)))}
              onEdit={(text) =>
                run(async () => {
                  setM(await api.editSegment(s.id, text));
                  return true; // run() mengembalikan undefined bila gagal
                })
              }
            />
          ))}
        </ol>
        {m.segments.length === 0 && <p className="text-sm text-neutral-500">Tidak ada ucapan yang terdeteksi.</p>}
      </section>
    </div>
  );
}

function SegmentRow({
  seg, speaker, speakers, active, onSeek, onReassign, onEdit,
}: {
  seg: Segment;
  speaker: Speaker | undefined;
  speakers: Speaker[];
  active: boolean;
  onSeek: () => void;
  onReassign: (speakerId: number) => void;
  onEdit: (text: string) => Promise<unknown>;
}) {
  const [picking, setPicking] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(seg.text);
  const [saving, setSaving] = useState(false);
  const c = speakerColor(speaker?.label ?? "A");

  async function save(text: string) {
    const t = text.trim();
    if (!t || t === seg.text) return setEditing(false);
    setSaving(true);
    try {
      if (await onEdit(t)) setEditing(false); // gagal → tetap di mode edit agar ketikan tidak hilang
    } finally {
      setSaving(false);
    }
  }

  return (
    <li id={`seg-${seg.id}`} className={`group flex gap-3 rounded-lg px-3 py-2 ${active ? c.soft : "hover:bg-neutral-50 dark:hover:bg-neutral-900/60"}`}>
      <button onClick={onSeek} className="w-14 shrink-0 pt-0.5 text-left font-mono text-xs text-neutral-500 hover:text-blue-600" title="Putar dari sini">
        {clock(seg.start_ms)}
      </button>
      <div className="min-w-0 flex-1">
        {picking ? (
          <select
            autoFocus
            className="mb-1 rounded border border-neutral-300 bg-transparent text-xs dark:border-neutral-700"
            defaultValue={seg.speaker_id ?? undefined}
            onBlur={() => setPicking(false)}
            onChange={(e) => {
              setPicking(false);
              onReassign(Number(e.target.value));
            }}
          >
            {speakers.map((s) => (
              <option key={s.id} value={s.id}>{s.display_name}</option>
            ))}
          </select>
        ) : (
          <button className={`mb-0.5 flex items-center gap-1.5 text-xs font-semibold ${c.text}`} onClick={() => setPicking(true)} title="Klik untuk ganti pembicara kalimat ini">
            <span className={`h-2 w-2 rounded-full ${c.dot}`} />
            {speaker?.display_name ?? "?"}
          </button>
        )}
        {editing ? (
          <div className="space-y-2">
            <textarea
              autoFocus
              rows={Math.min(8, Math.max(2, Math.ceil(draft.length / 80)))}
              className="w-full rounded-lg border border-blue-400 bg-transparent px-2 py-1.5 leading-relaxed outline-none focus:ring-2 focus:ring-blue-500/30"
              value={draft}
              disabled={saving}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setEditing(false);
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  save(draft);
                }
              }}
            />
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <button className="rounded bg-blue-600 px-2.5 py-1 font-medium text-white hover:bg-blue-700 disabled:opacity-50" disabled={saving} onClick={() => save(draft)}>
                {saving ? "Menyimpan…" : "Simpan"}
              </button>
              <button className="rounded px-2.5 py-1 hover:bg-neutral-100 dark:hover:bg-neutral-800" onClick={() => setEditing(false)}>
                Batal
              </button>
              {seg.original_text && (
                <button className="rounded px-2.5 py-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800" disabled={saving} onClick={() => save(seg.original_text!)}>
                  Kembalikan teks asli
                </button>
              )}
              <span className="text-neutral-500">Enter = simpan · Shift+Enter = baris baru · Esc = batal</span>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-2">
            <p className="flex-1 cursor-pointer leading-relaxed" onClick={onSeek}>
              {seg.text}
              {seg.original_text && (
                <span className="ml-1.5 align-middle text-[10px] font-medium uppercase tracking-wide text-amber-600 dark:text-amber-400" title={`Teks asli: ${seg.original_text}`}>
                  diedit
                </span>
              )}
            </p>
            <button
              className="shrink-0 rounded px-1.5 py-0.5 text-xs text-neutral-500 opacity-0 hover:bg-neutral-200 hover:text-neutral-800 focus:opacity-100 group-hover:opacity-100 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
              title="Perbaiki teks kalimat ini"
              onClick={() => {
                setDraft(seg.text);
                setEditing(true);
              }}
            >
              ✎ Edit
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

function SpeakerPanel({ m, setM, run }: { m: MeetingDetail; setM: (m: MeetingDetail) => void; run: Run }) {
  const total = m.speakers.reduce((a, s) => a + s.talk_time_ms, 0) || 1;
  const sorted = [...m.speakers].sort((a, b) => b.talk_time_ms - a.talk_time_ms);
  return (
    <div className="rounded-2xl border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-semibold">Pembicara</h2>
        <span className="text-sm text-neutral-500">{m.speaker_count ?? m.speakers.length} terdeteksi</span>
      </div>
      <ul className="space-y-4">
        {sorted.map((s) => (
          <SpeakerRow
            key={s.id}
            s={s}
            pct={(s.talk_time_ms / total) * 100}
            others={m.speakers.filter((o) => o.id !== s.id)}
            onRename={(name) =>
              run(async () => {
                const up = await api.renameSpeaker(s.id, name);
                setM({ ...m, speakers: m.speakers.map((x) => (x.id === up.id ? up : x)) });
              })
            }
            onMerge={(targetId) =>
              run(async () => setM(await api.mergeSpeakers(m.id, [s.id], targetId)))
            }
          />
        ))}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-neutral-500">
        Klik nama untuk mengganti. Jika satu orang terdeteksi sebagai dua pembicara, gunakan “Gabungkan ke…”.
        Klik nama di transkrip untuk memindah satu kalimat ke pembicara lain.
      </p>
    </div>
  );
}

function SpeakerRow({
  s, pct, others, onRename, onMerge,
}: {
  s: Speaker;
  pct: number;
  others: Speaker[];
  onRename: (name: string) => void;
  onMerge: (targetId: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(s.display_name);
  const c = speakerColor(s.label);
  const save = () => {
    setEditing(false);
    if (name.trim() && name.trim() !== s.display_name) onRename(name.trim());
  };
  return (
    <li className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${c.dot}`} />
        {editing ? (
          <input
            autoFocus
            className="min-w-0 flex-1 rounded border border-neutral-300 bg-transparent px-1.5 py-0.5 text-sm dark:border-neutral-700"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => e.key === "Enter" ? save() : e.key === "Escape" && (setName(s.display_name), setEditing(false))}
          />
        ) : (
          <button className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline" onClick={() => (setName(s.display_name), setEditing(true))}>
            {s.display_name}
          </button>
        )}
        <span className="text-sm tabular-nums text-neutral-500">{pct.toFixed(0)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
        <div className={`h-full ${c.dot}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex items-center justify-between gap-2 text-xs text-neutral-500">
        <span>
          {clock(s.talk_time_ms)} · {s.turn_count}× bicara · {s.word_count} kata
        </span>
        {others.length > 0 && (
          <select
            className="max-w-28 rounded border border-neutral-300 bg-transparent text-xs dark:border-neutral-700"
            value=""
            onChange={(e) => {
              const target = others.find((o) => o.id === Number(e.target.value));
              if (target && confirm(`Gabungkan "${s.display_name}" ke "${target.display_name}"?`)) onMerge(target.id);
            }}
          >
            <option value="">Gabungkan ke…</option>
            {others.map((o) => (
              <option key={o.id} value={o.id}>{o.display_name}</option>
            ))}
          </select>
        )}
      </div>
    </li>
  );
}
