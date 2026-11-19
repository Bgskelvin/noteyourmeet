"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type CorrectionRule, type GlossaryTerm, type ReviewStats, type Suggestions } from "@/lib/api";

const card = "space-y-3 rounded-2xl border border-neutral-200 p-5 dark:border-neutral-800";
const input = "min-w-0 flex-1 rounded-lg border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700";
const primaryBtn = "rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40";
const smallBtn = "rounded-md border border-neutral-300 px-2 py-0.5 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800";

export function GlossaryManager() {
  const [terms, setTerms] = useState<GlossaryTerm[] | null>(null);
  const [rules, setRules] = useState<CorrectionRule[] | null>(null);
  const [sug, setSug] = useState<Suggestions | null>(null);
  const [review, setReview] = useState<ReviewStats | null>(null);
  const [termInput, setTermInput] = useState("");
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [t, r, s, rv] = await Promise.all([
        api.listGlossary(),
        api.listCorrections(),
        api.suggestions(),
        api.reviewStats(),
      ]);
      setTerms(t);
      setRules(r);
      setSug(s);
      setReview(rv);
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

  const suggestionCount = (sug?.terms.length ?? 0) + (sug?.rules.length ?? 0);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Kosakata &amp; koreksi</h1>
        <p className="mt-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
          Tempat sistem <strong>belajar dari koreksimu</strong>. Kosakata membantu Whisper menulis nama &amp; istilah dengan
          benar; memori koreksi otomatis membetulkan kata yang sering salah dengar. Keduanya berlaku untuk meeting yang
          diproses berikutnya.
        </p>
      </div>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}

      {/* ---------- Periksa transkrip ---------- */}
      <section className={card}>
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="font-semibold">Periksa transkrip</h2>
          <span className="text-xs text-neutral-500">cara terbaik mengajari sistem</span>
        </div>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Dengarkan kalimat per kalimat, perbaiki kata yang salah atau terlewat, dan beri nama pembicara — semua di satu
          layar. Setiap perbaikan kata bisa langsung diingat untuk meeting berikutnya.
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
                  <Link href={`/meetings/${mt.id}/periksa`} className={pct === 100 ? smallBtn : "rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700"}>
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
            <p className="mt-1.5">
              Saat cukup, ekspor dengan <code className="rounded bg-neutral-200 px-1 dark:bg-neutral-800">python -m app.dataset export --dest …</code> untuk
              melatih ulang Whisper dengan suara &amp; istilah tim sendiri.
            </p>
          </div>
        )}
      </section>

      {/* ---------- Saran ---------- */}
      <section className={card}>
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="font-semibold">Saran dari koreksimu {suggestionCount > 0 && <span className="text-blue-600">({suggestionCount})</span>}</h2>
          <span className="text-xs text-neutral-500">dipelajari dari kalimat yang kamu edit</span>
        </div>
        {sug === null && !error && <p className="text-sm text-neutral-500">Memuat…</p>}
        {sug && suggestionCount === 0 && (
          <p className="text-sm text-neutral-500">
            Belum ada saran. Saat kamu memperbaiki kata di transkrip (✎ Edit), nama &amp; istilah baru serta pola
            &ldquo;salah → benar&rdquo; akan muncul di sini.
          </p>
        )}
        {!!sug?.terms.length && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">Istilah baru → Kosakata tim</p>
            <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {sug.terms.map((s) => (
                <li key={s.term} className="flex items-center gap-3 py-1.5 text-sm">
                  <span className="font-medium">{s.term}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-neutral-500" title={s.example}>
                    {s.count}× · “{s.example}”
                  </span>
                  <button className={smallBtn} disabled={saving} onClick={() => act(() => api.addGlossary(s.term))}>
                    + Tambah
                  </button>
                  <button className={smallBtn} disabled={saving} title="Abaikan saran ini" onClick={() => act(() => api.dismissSuggestion("term", s.term))}>
                    Abaikan
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {!!sug?.rules.length && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
              Pola salah → benar → Memori koreksi <span className="normal-case">(cek dulu: kata umum seperti “tuh” jangan diganti otomatis)</span>
            </p>
            <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {sug.rules.map((s) => (
                <li key={`${s.find}→${s.replace}`} className="flex items-center gap-3 py-1.5 text-sm">
                  <span>
                    <span className="text-red-600 line-through decoration-1 dark:text-red-400">{s.find}</span> →{" "}
                    <span className="font-medium text-emerald-700 dark:text-emerald-400">{s.replace}</span>
                  </span>
                  <span className="min-w-0 flex-1 truncate text-xs text-neutral-500" title={s.example}>
                    {s.count}× · “{s.example}”
                  </span>
                  <button className={smallBtn} disabled={saving} onClick={() => act(() => api.addCorrection(s.find, s.replace))}>
                    + Ingat
                  </button>
                  <button className={smallBtn} disabled={saving} title="Abaikan saran ini" onClick={() => act(() => api.dismissSuggestion("rule", `${s.find}→${s.replace}`))}>
                    Abaikan
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* ---------- Kosakata ---------- */}
      <section className={card}>
        <h2 className="font-semibold">Kosakata tim</h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Nama orang, singkatan, produk, istilah internal. Whisper memprioritaskan ejaan ini saat mengubah suara jadi teks.
        </p>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (termInput.trim()) act(async () => (await api.addGlossary(termInput), setTermInput("")));
          }}
        >
          <input className={input} placeholder="mis. ALC, CS ALC, Rio, Canva (pisahkan dengan koma)" value={termInput} onChange={(e) => setTermInput(e.target.value)} disabled={saving} />
          <button className={primaryBtn} disabled={saving || !termInput.trim()}>
            Tambah
          </button>
        </form>
        {terms?.length === 0 && <p className="text-sm text-neutral-500">Belum ada kosakata.</p>}
        {!!terms?.length && (
          <>
            <ul className="flex flex-wrap gap-2">
              {terms.map((t) => (
                <li key={t.id} className="flex items-center gap-1 rounded-full border border-neutral-300 py-1 pl-3 pr-1 text-sm dark:border-neutral-700">
                  {t.term}
                  <button
                    className="flex h-5 w-5 items-center justify-center rounded-full text-neutral-500 hover:bg-neutral-200 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                    onClick={() => act(() => api.deleteGlossary(t.id))}
                    aria-label={`Hapus ${t.term}`}
                    title="Hapus"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
            <p className="text-xs text-neutral-500">{terms.length} kata. Usahakan ringkas (maks. ± 60 kata) — terlalu banyak justru kurang efektif.</p>
          </>
        )}
      </section>

      {/* ---------- Memori koreksi ---------- */}
      <section className={card}>
        <h2 className="font-semibold">Memori koreksi</h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Kata yang sering salah dengar dan penggantinya. Diterapkan <strong>otomatis</strong> ke setiap transkrip baru (tanda
          <span className="mx-1 text-[10px] font-medium uppercase tracking-wide text-sky-600 dark:text-sky-400">otomatis</span>di
          kalimat). Untuk meeting lama, buka meeting → <em>Ganti kata</em> → <em>Terapkan memori koreksi</em>.
        </p>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (find.trim() && replace.trim())
              act(async () => {
                await api.addCorrection(find, replace);
                setFind("");
                setReplace("");
              });
          }}
        >
          <input className={input} placeholder="Kata salah, mis. CSILC" value={find} onChange={(e) => setFind(e.target.value)} disabled={saving} />
          <span className="self-center text-neutral-400">→</span>
          <input className={input} placeholder="Kata benar, mis. CS ALC" value={replace} onChange={(e) => setReplace(e.target.value)} disabled={saving} />
          <button className={primaryBtn} disabled={saving || !find.trim() || !replace.trim()}>
            Simpan
          </button>
        </form>
        {rules?.length === 0 && <p className="text-sm text-neutral-500">Belum ada. Gunakan “Ganti kata” di transkrip dengan opsi “Ingat koreksi ini”.</p>}
        {!!rules?.length && (
          <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {rules.map((r) => (
              <li key={r.id} className={`flex items-center gap-3 py-2 text-sm ${r.enabled ? "" : "opacity-50"}`}>
                <label className="flex items-center" title={r.enabled ? "Aktif — klik untuk menonaktifkan" : "Nonaktif — klik untuk mengaktifkan"}>
                  <input type="checkbox" checked={r.enabled} disabled={saving} onChange={(e) => act(() => api.setCorrectionEnabled(r.id, e.target.checked))} />
                </label>
                <span className="flex-1">
                  <span className="text-red-600 line-through decoration-1 dark:text-red-400">{r.find}</span> →{" "}
                  <span className="font-medium text-emerald-700 dark:text-emerald-400">{r.replace}</span>
                </span>
                <span className="text-xs text-neutral-500">dipakai {r.times_applied}×</span>
                <button className={smallBtn} disabled={saving} onClick={() => confirm(`Hapus koreksi "${r.find} → ${r.replace}"?`) && act(() => api.deleteCorrection(r.id))}>
                  Hapus
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
