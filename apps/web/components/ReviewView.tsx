"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type LearnResult, type MeetingDetail, type Segment, type Speaker } from "@/lib/api";
import { clock, speakerColor } from "@/lib/format";

/**
 * Mode Periksa: satu kalimat sekali tampil. Dengarkan → perbaiki kata → beri nama pembicara → "Benar, lanjut".
 * Setiap kalimat yang disetujui ditandai "sudah diperiksa" (bahan set uji & data latihan),
 * dan setiap kata yang diperbaiki bisa langsung diingat sebagai memori koreksi.
 */
export function ReviewView() {
  const { id } = useParams<{ id: string }>();
  const meetingId = Number(id);
  const [m, setM] = useState<MeetingDetail | null>(null);
  const [idx, setIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.getMeeting(meetingId);
      setM(d);
      // Mulai dari kalimat pertama yang belum diperiksa
      const first = d.segments.findIndex((s) => !s.reviewed_at);
      setIdx(first >= 0 ? first : 0);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [meetingId]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  if (error) return <p className="text-red-600">Gagal memuat: {error}</p>;
  if (!m) return <p className="text-neutral-500">Memuat…</p>;
  if (m.status !== "DONE")
    return (
      <p className="text-neutral-500">
        Meeting ini belum selesai diproses. <Link href={`/meetings/${m.id}`} className="underline">Kembali</Link>
      </p>
    );
  if (m.segments.length === 0) return <p className="text-neutral-500">Tidak ada kalimat untuk diperiksa.</p>;

  return <ReviewWorkspace m={m} setM={setM} idx={idx} setIdx={setIdx} />;
}

function ReviewWorkspace({
  m, setM, idx, setIdx,
}: {
  m: MeetingDetail;
  setM: (m: MeetingDetail) => void;
  idx: number;
  setIdx: (i: number) => void;
}) {
  const segs = m.segments;
  const seg = segs[Math.min(idx, segs.length - 1)];
  const speakers = useMemo(() => new Map(m.speakers.map((s) => [s.id, s])), [m.speakers]);
  const speaker = speakers.get(seg.speaker_id ?? -1);
  const reviewedCount = segs.filter((s) => s.reviewed_at).length;
  const allDone = reviewedCount === segs.length;

  const audioRef = useRef<HTMLAudioElement>(null);
  const stopAtRef = useRef<number | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState(seg.text);
  const [autoplay, setAutoplay] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [sel, setSel] = useState<{ start: number; end: number; text: string } | null>(null);

  // Kalimat berganti → isi ulang teks & putar audionya
  const [shownId, setShownId] = useState(seg.id);
  if (shownId !== seg.id) {
    setShownId(seg.id);
    setDraft(seg.text);
    setSel(null);
  }

  const play = useCallback((s: Segment) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = Math.max(0, s.start_ms / 1000 - 0.2);
    stopAtRef.current = s.end_ms / 1000 + 0.3;
    a.play().catch(() => {});
  }, []);

  useEffect(() => {
    if (autoplay) play(seg);
    taRef.current?.focus();
  }, [seg, autoplay, play]);

  async function act<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    try {
      return await fn();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function flash(msg: string) {
    setNotice(msg);
    setTimeout(() => setNotice(null), 3000);
  }

  function go(to: number) {
    setIdx(Math.max(0, Math.min(segs.length - 1, to)));
  }

  function nextUnreviewed(after: number, list: Segment[]) {
    const n = list.findIndex((s, i) => i > after && !s.reviewed_at);
    return n >= 0 ? n : Math.min(after + 1, list.length - 1);
  }

  async function confirmAndNext() {
    const text = draft.trim();
    if (!text) return;
    const updated = await act(async () => {
      if (text !== seg.text) return api.editSegment(seg.id, text); // edit = otomatis diperiksa
      const s = await api.reviewSegment(seg.id, true);
      return { ...m, segments: segs.map((x) => (x.id === s.id ? s : x)) };
    });
    if (!updated) return;
    setM(updated);
    go(nextUnreviewed(idx, updated.segments));
  }

  async function unreview() {
    const s = await act(() => api.reviewSegment(seg.id, false));
    if (s) setM({ ...m, segments: segs.map((x) => (x.id === s.id ? s : x)) });
  }

  function onSelect() {
    const ta = taRef.current;
    if (!ta) return;
    let { selectionStart: a, selectionEnd: b } = ta;
    // Buang spasi & tanda baca di tepi seleksi ("CSILC," → "CSILC"); abaikan seleksi tanpa huruf/angka
    const edge = /[\s.,!?;:"'()[\]…“”‘’]/;
    while (a < b && edge.test(draft[a])) a++;
    while (b > a && edge.test(draft[b - 1])) b--;
    const text = draft.slice(a, b);
    setSel(b > a && /[\p{L}\p{N}]/u.test(text) ? { start: a, end: b, text } : null);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      {/* Kepala: judul + progres */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Link href={`/meetings/${m.id}`} className="text-sm text-neutral-500 hover:underline">
            ← {m.title}
          </Link>
          <span className="text-sm text-neutral-500">
            {reviewedCount} / {segs.length} kalimat diperiksa
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${(reviewedCount / segs.length) * 100}%` }} />
        </div>
      </div>

      {allDone && (
        <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
          🎉 Semua kalimat di meeting ini sudah diperiksa. Terima kasih — data ini sekarang bisa dipakai untuk set uji &amp;
          latihan model. <Link href="/kamus" className="underline">Lihat ringkasannya</Link>.
        </div>
      )}

      <audio
        ref={audioRef}
        src={api.audioUrl(m.id)}
        preload="auto"
        controls
        className="w-full"
        onTimeUpdate={(e) => {
          if (stopAtRef.current != null && e.currentTarget.currentTime >= stopAtRef.current) {
            e.currentTarget.pause();
            stopAtRef.current = null;
          }
        }}
      />

      {/* Konteks sebelumnya */}
      {idx > 0 && <ContextLine seg={segs[idx - 1]} speaker={speakers.get(segs[idx - 1].speaker_id ?? -1)} onClick={() => go(idx - 1)} />}

      {/* Kartu kalimat yang sedang diperiksa */}
      <div className={`space-y-3 rounded-2xl border-2 p-5 ${seg.reviewed_at ? "border-emerald-400 dark:border-emerald-700" : "border-blue-400 dark:border-blue-700"}`}>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-mono text-xs text-neutral-500">
            #{idx + 1} · {clock(seg.start_ms)}–{clock(seg.end_ms)}
          </span>
          <button className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800" onClick={() => play(seg)} title="Alt+P">
            ▶ Putar ulang
          </button>
          <label className="flex items-center gap-1 text-xs text-neutral-500">
            <input type="checkbox" checked={autoplay} onChange={(e) => setAutoplay(e.target.checked)} /> putar otomatis
          </label>
          {seg.reviewed_at && (
            <span className="ml-auto text-xs text-emerald-600 dark:text-emerald-400">
              ✓ sudah diperiksa ·{" "}
              <button className="underline" onClick={unreview} disabled={busy}>
                batalkan tanda
              </button>
            </span>
          )}
        </div>

        <SpeakerBox
          key={`${seg.id}-${speaker?.id}`}
          m={m}
          seg={seg}
          speaker={speaker}
          busy={busy}
          onRename={async (sp, name) => {
            const up = await act(() => api.renameSpeaker(sp.id, name));
            if (up) {
              setM({ ...m, speakers: m.speakers.map((x) => (x.id === up.id ? up : x)) });
              flash(`Semua kalimat “${sp.display_name}” sekarang atas nama ${up.display_name}.`);
            }
          }}
          onReassign={async (spId) => {
            const d = await act(() => api.reassignSegment(seg.id, spId));
            if (d) setM(d);
          }}
        />

        <textarea
          ref={taRef}
          rows={Math.min(8, Math.max(3, Math.ceil(draft.length / 70)))}
          className="w-full rounded-lg border border-neutral-300 bg-transparent px-3 py-2 text-lg leading-relaxed outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-neutral-700"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onSelect={onSelect}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              confirmAndNext();
            } else if (e.key === "Escape") {
              setDraft(seg.text);
            } else if (e.altKey && e.key.toLowerCase() === "p") {
              e.preventDefault();
              play(seg);
            } else if (e.altKey && e.key === "ArrowRight") {
              e.preventDefault();
              go(idx + 1);
            } else if (e.altKey && e.key === "ArrowLeft") {
              e.preventDefault();
              go(idx - 1);
            }
          }}
        />
        {seg.original_text && seg.original_text !== draft && (
          <p className="text-xs text-neutral-500">
            Teks asli AI: <span className="italic">{seg.original_text}</span>
          </p>
        )}

        {sel ? (
          <WordFix
            key={`${sel.start}-${sel.end}-${sel.text}`}
            m={m}
            sel={sel}
            busy={busy}
            onApply={async ({ replacement, wholeMeeting, mode }) => {
              // mode: "learn" = perbaiki & ingat · "confirm" = ingat walau kata umum · "local" = kalimat ini saja
              const before = draft.slice(0, sel.start);
              const after = draft.slice(sel.end);
              const newDraft = `${before}${replacement}${after}`;
              const wholeWord = !/[\p{L}\p{N}]$/u.test(before) && !/^[\p{L}\p{N}]/u.test(after);
              let result: LearnResult | null = null;
              if (mode !== "local") {
                setBusy(true);
                try {
                  result = await api.learn({
                    find: sel.text, replace: replacement, meeting_id: m.id, apply_to_meeting: wholeMeeting,
                    whole_word: wholeWord, confirm_common: mode === "confirm",
                  });
                  if (wholeMeeting && result.segments_changed) setM(await api.getMeeting(m.id));
                } catch (e) {
                  if (e instanceof ApiError && e.status === 409) return "common";
                  alert((e as Error).message);
                  return "error";
                } finally {
                  setBusy(false);
                }
              }
              setDraft(newDraft);
              setSel(null);
              flash(
                [
                  `“${sel.text}” → “${replacement}”`,
                  result && wholeMeeting && result.segments_changed ? `diganti di ${result.segments_changed} kalimat` : null,
                  result ? "diingat di Kamus tim" : "hanya di kalimat ini",
                  result?.glossary_added ? "🎧 dikenali Whisper mulai meeting berikutnya" : null,
                ].filter(Boolean).join(" · "),
              );
              taRef.current?.focus();
              return "ok";
            }}
            onCancel={() => setSel(null)}
          />
        ) : (
          <p className="text-xs text-neutral-500">
            💡 Ada kata yang salah? <strong>Blok/seleksi kata itu</strong> di kotak teks untuk memperbaikinya sekaligus
            mengajari sistem. Kata yang terlewat? Ketik langsung di kotak teks.
          </p>
        )}

        {notice && <p className="rounded-lg bg-sky-50 px-3 py-2 text-sm text-sky-800 dark:bg-sky-950/40 dark:text-sky-300">{notice}</p>}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            className="rounded-lg bg-emerald-600 px-5 py-2.5 font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={confirmAndNext}
            disabled={busy || !draft.trim()}
          >
            {draft.trim() !== seg.text ? "Simpan & lanjut" : "✓ Benar, lanjut"} <span className="text-xs opacity-75">(Enter)</span>
          </button>
          <button className="rounded-lg border border-neutral-300 px-3 py-2.5 text-sm hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-900" onClick={() => go(idx - 1)} disabled={idx === 0} title="Alt+←">
            ← Sebelumnya
          </button>
          <button className="rounded-lg border border-neutral-300 px-3 py-2.5 text-sm hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-900" onClick={() => go(idx + 1)} disabled={idx >= segs.length - 1} title="Alt+→">
            Lewati →
          </button>
          {draft !== seg.text && (
            <button className="text-sm text-neutral-500 underline" onClick={() => setDraft(seg.text)}>
              batalkan perubahan (Esc)
            </button>
          )}
        </div>
      </div>

      {/* Konteks berikutnya */}
      {idx < segs.length - 1 && <ContextLine seg={segs[idx + 1]} speaker={speakers.get(segs[idx + 1].speaker_id ?? -1)} onClick={() => go(idx + 1)} />}

      <p className="text-center text-xs text-neutral-500">
        Tips: tulis persis seperti yang diucapkan (termasuk “gak”, “udah”, campuran Inggris) — jangan dirapikan.
        Pintasan: Enter = benar/lanjut · Shift+Enter = baris baru · Esc = batalkan · Alt+P = putar ulang · Alt+←/→ = pindah
      </p>
    </div>
  );
}

function ContextLine({ seg, speaker, onClick }: { seg: Segment; speaker: Speaker | undefined; onClick: () => void }) {
  const c = speakerColor(speaker?.label ?? "A");
  return (
    <button onClick={onClick} className="block w-full rounded-lg px-4 py-2 text-left text-sm text-neutral-500 hover:bg-neutral-50 dark:hover:bg-neutral-900">
      <span className={`mr-2 text-xs font-semibold ${c.text}`}>{speaker?.display_name ?? "?"}</span>
      {seg.reviewed_at && <span className="mr-1 text-emerald-500">✓</span>}
      {seg.text}
    </button>
  );
}

function SpeakerBox({
  m, seg, speaker, busy, onRename, onReassign,
}: {
  m: MeetingDetail;
  seg: Segment;
  speaker: Speaker | undefined;
  busy: boolean;
  onRename: (sp: Speaker, name: string) => void;
  onReassign: (speakerId: number) => void;
}) {
  const unnamed = !speaker || /^Pembicara [A-Z]+$/.test(speaker.display_name);
  const [editing, setEditing] = useState(unnamed);
  const [name, setName] = useState(unnamed ? "" : speaker?.display_name ?? "");
  const c = speakerColor(speaker?.label ?? "A");
  const named = m.speakers.filter((s) => s.id !== speaker?.id);

  return (
    <div className={`space-y-2 rounded-lg px-3 py-2 ${c.soft}`}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`h-2.5 w-2.5 rounded-full ${c.dot}`} />
        <span className={`font-semibold ${c.text}`}>{speaker?.display_name ?? "?"}</span>
        {!editing && speaker && (
          <button className="text-xs text-neutral-500 underline" onClick={() => setEditing(true)}>
            ganti nama
          </button>
        )}
        {named.length > 0 && (
          <select
            className="ml-auto max-w-48 rounded border border-neutral-300 bg-[var(--background)] px-1.5 py-0.5 text-xs dark:border-neutral-700"
            value=""
            disabled={busy}
            onChange={(e) => e.target.value && onReassign(Number(e.target.value))}
            title="Kalimat ini sebenarnya diucapkan orang lain"
          >
            <option value="">Bukan dia? Pindahkan ke…</option>
            {named.map((s) => (
              <option key={s.id} value={s.id}>
                {s.display_name}
              </option>
            ))}
          </select>
        )}
      </div>
      {editing && speaker && (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) {
              onRename(speaker, name.trim());
              setEditing(false);
            }
          }}
        >
          <span className="text-sm">{unnamed ? "🎙️ Siapa yang bicara ini?" : "Nama baru:"}</span>
          <input
            className="min-w-32 flex-1 rounded-lg border border-neutral-300 bg-[var(--background)] px-2 py-1 text-sm dark:border-neutral-700"
            placeholder="mis. Budi"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
          />
          <button className="rounded-lg bg-blue-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-40" disabled={busy || !name.trim()}>
            Simpan
          </button>
          <button type="button" className="text-xs text-neutral-500 underline" onClick={() => setEditing(false)}>
            nanti saja
          </button>
          <span className="basis-full text-xs text-neutral-500">
            Berlaku untuk semua kalimat {speaker.display_name} di meeting ini ({speaker.turn_count}× bicara). Kalimat ini:
            “{seg.text.slice(0, 60)}{seg.text.length > 60 ? "…" : ""}”
          </span>
        </form>
      )}
    </div>
  );
}

type FixMode = "learn" | "confirm" | "local";

function WordFix({
  m, sel, busy, onApply, onCancel,
}: {
  m: MeetingDetail;
  sel: { start: number; end: number; text: string };
  busy: boolean;
  onApply: (o: { replacement: string; wholeMeeting: boolean; mode: FixMode }) => Promise<"ok" | "common" | "error">;
  onCancel: () => void;
}) {
  const [replacement, setReplacement] = useState(sel.text);
  const [wholeMeeting, setWholeMeeting] = useState(true);
  const [askCommon, setAskCommon] = useState(false);
  const occurrences = useMemo(() => {
    const esc = sel.text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(?<![\\p{L}\\p{N}_])${esc}(?![\\p{L}\\p{N}_])`, "giu");
    return m.segments.reduce((n, s) => n + (s.text.match(re)?.length ?? 0), 0);
  }, [m.segments, sel.text]);
  const value = replacement.trim();
  const changed = !!value && value !== sel.text;

  async function submit(mode: FixMode) {
    if (!changed) return;
    const r = await onApply({ replacement: value, wholeMeeting: mode === "local" ? false : wholeMeeting, mode });
    if (r === "common") setAskCommon(true);
  }

  return (
    <form
      className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30"
      onSubmit={(e) => {
        e.preventDefault();
        submit("learn");
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span>
          Perbaiki <span className="font-semibold text-red-600 line-through decoration-1 dark:text-red-400">{sel.text}</span> menjadi
        </span>
        <input
          autoFocus
          className="min-w-32 flex-1 rounded-lg border border-neutral-300 bg-[var(--background)] px-2 py-1 dark:border-neutral-700"
          value={replacement}
          onChange={(e) => {
            setReplacement(e.target.value);
            setAskCommon(false);
          }}
          onFocus={(e) => e.currentTarget.select()}
          onKeyDown={(e) => e.key === "Escape" && onCancel()}
          disabled={busy}
        />
        <button className="rounded-lg bg-amber-600 px-3 py-1 font-medium text-white disabled:opacity-40" disabled={busy || !changed}>
          Perbaiki
        </button>
        <button type="button" className="text-xs text-neutral-500 underline" onClick={onCancel}>
          batal
        </button>
      </div>

      {askCommon ? (
        <div className="space-y-2 rounded-md bg-amber-100 p-2 text-xs text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
          <p>
            ⚠️ <strong>“{sel.text}”</strong> adalah kata yang sangat umum. Kalau diingat, <em>semua</em> “{sel.text}” di meeting
            berikutnya ikut berubah menjadi “{value}” — bisa merusak kalimat lain.
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded bg-amber-700 px-2.5 py-1 font-medium text-white" disabled={busy} onClick={() => submit("local")}>
              Perbaiki kalimat ini saja (disarankan)
            </button>
            <button type="button" className="rounded border border-amber-700 px-2.5 py-1" disabled={busy} onClick={() => submit("confirm")}>
              Tetap ingat untuk semua meeting
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-700 dark:text-neutral-300">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={wholeMeeting} onChange={(e) => setWholeMeeting(e.target.checked)} /> Ganti juga di
            seluruh meeting ini ({occurrences}×)
          </label>
          <span className="text-neutral-500">
            Otomatis diingat di <strong>Kamus tim</strong>; nama/singkatan juga 🎧 dikenali Whisper.
          </span>
        </div>
      )}
    </form>
  );
}
