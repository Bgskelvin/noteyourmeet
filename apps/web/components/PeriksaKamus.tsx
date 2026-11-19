"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type DictionaryEntry, type ReviewStats, type Suggestions } from "@/lib/api";

const card = "space-y-3 rounded-2xl border border-neutral-200 p-5 dark:border-neutral-800";
const input = "min-w-0 flex-1 rounded-lg border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700";
const primaryBtn = "rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40";
const smallBtn = "rounded-md border border-neutral-300 px-2 py-0.5 text-xs hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800";

/** Satu halaman untuk mengajari sistem: periksa transkrip, saran dari editan, dan Kamus tim. */
export function PeriksaKamus() {
  const [dict, setDict] = useState<DictionaryEntry[] | null>(null);
  const [sug, setSug] = useState<Suggestions | null>(null);
  const [review, setReview] = useState<ReviewStats | null>(null);
  const [word, setWord] = useState("");
  const [variants, setVariants] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, s, r] = await Promise.all([api.dictionary(), api.suggestions(), api.reviewStats()]);
      setDict(d);
      setSug(s);
      setReview(r);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setSaving(true);
    try {
      await fn();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  /** Simpan "salah → benar"; untuk kata sangat umum minta konfirmasi dulu. */
  async function learn(find: string, replace: string) {
    try {
      await api.learn({ find, replace });
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 409)) throw e;
      if (!confirm(`"${find}" adalah kata yang sangat umum — semua "${find}" di meeting berikutnya akan diganti. Tetap simpan?`)) return;
      await api.learn({ find, replace, confirm_common: true });
    }
  }

  const suggestionCount = (sug?.terms.length ?? 0) + (sug?.rules.length ?? 0);
  const q = filter.trim().toLowerCase();
  const shown = dict?.filter((e) => !q || e.word.toLowerCase().includes(q) || e.variants.some((v) => v.find.toLowerCase().includes(q)));

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Periksa &amp; Kamus</h1>
        <p className="mt-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
          Tempat sistem <strong>belajar dari koreksimu</strong>. Periksa transkrip kalimat per kalimat — setiap kata yang kamu
          perbaiki otomatis masuk <strong>Kamus tim</strong> dan dipakai di meeting berikutnya.
        </p>
      </div>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}

      {/* ---------- Periksa transkrip ---------- */}
      <section className={card}>
        <h2 className="font-semibold">1. Periksa transkrip</h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Dengarkan kalimat per kalimat, perbaiki kata yang salah/terlewat, dan beri nama pembicara — semua di satu layar.
        </p>
        {review && review.meetings.length === 0 && <p className="text-sm text-neutral-500">Belum ada meeting yang selesai diproses.</p>}
        {!!review?.meetings.length && (
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {review.meetings.map((mt) => {
              const pct = Math.round((mt.reviewed_segments / Math.max(1, mt.total_segments)) * 100);
              return (
                <li key={mt.id} className="flex items-center gap-3 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{mt.title}</p>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="h-1.5 w-32 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
                        <div className="h-full bg-emerald-500" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs text-neutral-500">
                        {mt.reviewed_segments}/{mt.total_segments} kalimat ({pct}%)
                      </span>
                    </div>
                  </div>
                  <Link
                    href={`/meetings/${mt.id}/periksa`}
                    className={pct === 100 ? smallBtn : "rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700"}
                  >
                    {pct === 0 ? "Mulai periksa" : pct === 100 ? "Selesai ✓" : "Lanjutkan →"}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        {review && (
          <div className="rounded-lg bg-neutral-50 p-3 text-xs text-neutral-600 dark:bg-neutral-900 dark:text-neutral-400">
            <div className="mb-1 flex justify-between">
              <span>
                <strong>Data latihan model:</strong> {review.training.usable_minutes} menit terperiksa dari target{" "}
                {review.training.target_hours} jam
              </span>
              <span>{review.training.progress_pct}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
              <div className="h-full bg-violet-500" style={{ width: `${Math.min(100, review.training.progress_pct)}%` }} />
            </div>
          </div>
        )}
      </section>

      {/* ---------- Saran ---------- */}
      {sug && suggestionCount > 0 && (
        <section className={card}>
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="font-semibold">
              Saran dari editanmu <span className="text-blue-600">({suggestionCount})</span>
            </h2>
            <span className="text-xs text-neutral-500">dari kalimat yang kamu edit manual</span>
          </div>
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {sug.terms.map((s) => (
              <li key={`t-${s.term}`} className="flex items-center gap-3 py-1.5 text-sm">
                <span className="font-medium">{s.term}</span>
                <span className="text-xs text-neutral-500">nama/istilah baru</span>
                <span className="min-w-0 flex-1 truncate text-xs text-neutral-500" title={s.example}>
                  “{s.example}”
                </span>
                <button className={smallBtn} disabled={saving} onClick={() => act(() => api.addGlossary(s.term))}>
                  + Kamus
                </button>
                <button className={smallBtn} disabled={saving} onClick={() => act(() => api.dismissSuggestion("term", s.term))}>
                  Abaikan
                </button>
              </li>
            ))}
            {sug.rules.map((s) => (
              <li key={`r-${s.find}→${s.replace}`} className="flex items-center gap-3 py-1.5 text-sm">
                <span>
                  <span className="text-red-600 line-through decoration-1 dark:text-red-400">{s.find}</span> →{" "}
                  <span className="font-medium text-emerald-700 dark:text-emerald-400">{s.replace}</span>
                </span>
                <span className="min-w-0 flex-1 truncate text-xs text-neutral-500" title={s.example}>
                  {s.count}× · “{s.example}”
                </span>
                <button className={smallBtn} disabled={saving} onClick={() => act(() => learn(s.find, s.replace))}>
                  + Kamus
                </button>
                <button className={smallBtn} disabled={saving} onClick={() => act(() => api.dismissSuggestion("rule", `${s.find}→${s.replace}`))}>
                  Abaikan
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------- Kamus tim ---------- */}
      <section className={card}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold">2. Kamus tim {dict && <span className="font-normal text-neutral-500">({dict.length} kata)</span>}</h2>
          <span className="text-xs text-neutral-500">🎧 = dikenali Whisper saat mendengar · ← = salah dengar yang otomatis dibetulkan</span>
        </div>

        <form
          className="space-y-2 rounded-lg bg-neutral-50 p-3 dark:bg-neutral-900"
          onSubmit={(e) => {
            e.preventDefault();
            const w = word.trim();
            if (!w) return;
            const vs = variants.split(",").map((v) => v.trim()).filter(Boolean);
            act(async () => {
              if (vs.length) for (const v of vs) await learn(v, w);
              else await api.addGlossary(w);
              setWord("");
              setVariants("");
            });
          }}
        >
          <p className="text-xs text-neutral-500">
            Tambah manual — mis. nama klien baru <em>sebelum</em> meeting-nya diproses:
          </p>
          <div className="flex flex-wrap gap-2">
            <input className={input} placeholder="Kata yang benar, mis. CS ALC" value={word} onChange={(e) => setWord(e.target.value)} disabled={saving} />
            <input className={input} placeholder="Salah dengar (opsional), mis. CSILC, CS ILC" value={variants} onChange={(e) => setVariants(e.target.value)} disabled={saving} />
            <button className={primaryBtn} disabled={saving || !word.trim()}>
              Tambah
            </button>
          </div>
        </form>

        {dict && dict.length > 8 && (
          <input className={`${input} w-full`} placeholder="Cari di kamus…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        )}
        {dict?.length === 0 && (
          <p className="text-sm text-neutral-500">
            Kamus masih kosong. Isi otomatis saat kamu memperbaiki kata di <strong>Periksa transkrip</strong>, atau tambah manual di atas.
          </p>
        )}
        {!!shown?.length && (
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {shown.map((e) => (
              <DictionaryRow key={e.word} e={e} saving={saving} act={act} />
            ))}
          </ul>
        )}
        {dict && dict.filter((e) => e.glossary_id).length > 60 && (
          <p className="text-xs text-amber-600">
            Lebih dari 60 kata 🎧 — Whisper hanya membaca sebagian. Matikan 🎧 untuk kata yang jarang muncul.
          </p>
        )}
      </section>
    </div>
  );
}

function DictionaryRow({ e, saving, act }: { e: DictionaryEntry; saving: boolean; act: (fn: () => Promise<unknown>) => void }) {
  const used = e.variants.reduce((n, v) => n + v.times_applied, 0);
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5 text-sm">
      <button
        className={`rounded-md px-1.5 py-0.5 text-xs ${e.glossary_id ? "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300" : "text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800"}`}
        disabled={saving}
        title={e.glossary_id ? "Dikenali Whisper saat mendengar — klik untuk mematikan" : "Klik agar Whisper memprioritaskan kata ini saat mendengar"}
        onClick={() => act(() => (e.glossary_id ? api.deleteGlossary(e.glossary_id) : api.addGlossary(e.word)))}
      >
        🎧 {e.glossary_id ? "on" : "off"}
      </button>
      <span className="font-semibold">{e.word}</span>
      <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
        {e.variants.map((v) => (
          <span
            key={v.rule_id}
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
              v.enabled ? "border-neutral-300 dark:border-neutral-700" : "border-dashed border-neutral-300 opacity-50 dark:border-neutral-700"
            }`}
          >
            <button
              className="text-red-600 line-through decoration-1 dark:text-red-400"
              disabled={saving}
              title={v.enabled ? `Otomatis dibetulkan (${v.times_applied}×) — klik untuk menonaktifkan` : "Nonaktif — klik untuk mengaktifkan"}
              onClick={() => act(() => api.setCorrectionEnabled(v.rule_id, !v.enabled))}
            >
              {v.find}
            </button>
            <button className="text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100" disabled={saving} aria-label={`Hapus ${v.find}`} onClick={() => act(() => api.deleteCorrection(v.rule_id))}>
              ×
            </button>
          </span>
        ))}
      </span>
      {used > 0 && <span className="text-xs text-neutral-500">dibetulkan {used}×</span>}
      <button
        className={smallBtn}
        disabled={saving}
        onClick={() => confirm(`Hapus "${e.word}" beserta semua variasi salah dengarnya dari Kamus?`) && act(() => api.deleteDictionaryWord(e.word))}
      >
        Hapus
      </button>
    </li>
  );
}
