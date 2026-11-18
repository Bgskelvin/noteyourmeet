"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type GlossaryTerm } from "@/lib/api";

export function GlossaryManager() {
  const [terms, setTerms] = useState<GlossaryTerm[] | null>(null);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setTerms(await api.listGlossary());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setSaving(true);
    try {
      setTerms(await api.addGlossary(input));
      setInput("");
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(t: GlossaryTerm) {
    try {
      await api.deleteGlossary(t.id);
      setTerms((prev) => prev?.filter((x) => x.id !== t.id) ?? null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Kosakata tim</h1>
        <p className="mt-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
          Daftar nama orang, singkatan, nama produk, dan istilah internal yang sering muncul di meeting. Whisper akan
          <strong> memprioritaskan ejaan ini</strong> saat mengubah suara jadi teks, jadi kata seperti “ALC” tidak lagi
          ditulis “ILC”. Berlaku untuk meeting yang diproses <strong>setelah</strong> kata ditambahkan — untuk meeting
          lama, klik <em>Proses ulang</em> (koreksi manual di meeting itu akan hilang).
        </p>
      </div>

      <form onSubmit={add} className="flex gap-2">
        <input
          className="min-w-0 flex-1 rounded-lg border border-neutral-300 bg-transparent px-3 py-2 text-sm dark:border-neutral-700"
          placeholder="mis. ALC, CS ALC, Rio, Canva (pisahkan dengan koma)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={saving}
        />
        <button
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
          disabled={saving || !input.trim()}
        >
          Tambah
        </button>
      </form>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}
      {terms === null && !error && <p className="text-sm text-neutral-500">Memuat…</p>}
      {terms?.length === 0 && (
        <p className="rounded-xl border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-500 dark:border-neutral-700">
          Belum ada kosakata. Tambahkan nama &amp; istilah yang sering salah ditulis.
        </p>
      )}
      {!!terms?.length && (
        <ul className="flex flex-wrap gap-2">
          {terms.map((t) => (
            <li
              key={t.id}
              className="flex items-center gap-1 rounded-full border border-neutral-300 py-1 pl-3 pr-1 text-sm dark:border-neutral-700"
            >
              {t.term}
              <button
                className="flex h-5 w-5 items-center justify-center rounded-full text-neutral-500 hover:bg-neutral-200 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                onClick={() => remove(t)}
                aria-label={`Hapus ${t.term}`}
                title="Hapus"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {!!terms?.length && <p className="text-xs text-neutral-500">{terms.length} kata. Usahakan ringkas (maks. ± 60 kata) — terlalu banyak justru kurang efektif.</p>}
    </div>
  );
}
