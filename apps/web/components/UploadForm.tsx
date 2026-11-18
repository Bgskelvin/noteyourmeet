"use client";

import { useEffect, useRef, useState } from "react";
import { LANGUAGES, uploadMeeting, type MeetingSummary } from "@/lib/api";

const ACCEPT = "audio/*,video/*,.m4a,.mp3,.aac,.wav,.ogg,.opus,.flac,.webm,.mp4,.mkv,.mov,.3gp,.amr,.wma";
const LANG_KEY = "nym:lastLanguage";

export function UploadForm({ onUploaded }: { onUploaded: (m: MeetingSummary) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [minSp, setMinSp] = useState("");
  const [maxSp, setMaxSp] = useState("");
  const [language, setLanguage] = useState("id");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const abortRef = useRef<(() => void) | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Ingat bahasa terakhir yang dipilih (hanya kenyamanan; aman bila storage tidak tersedia)
  useEffect(() => {
    const t = setTimeout(() => {
      try {
        const saved = localStorage.getItem(LANG_KEY);
        if (saved && LANGUAGES.some((l) => l.code === saved)) setLanguage(saved);
      } catch {}
    }, 0);
    return () => clearTimeout(t);
  }, []);

  function chooseLanguage(code: string) {
    setLanguage(code);
    try {
      localStorage.setItem(LANG_KEY, code);
    } catch {}
  }

  function pick(f: File | undefined) {
    if (!f) return;
    setFile(f);
    setError(null);
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title);
    if (minSp) fd.append("min_speakers", minSp);
    if (maxSp) fd.append("max_speakers", maxSp);
    fd.append("language", language);
    setError(null);
    setProgress(0);
    const { promise, abort } = uploadMeeting(fd, setProgress);
    abortRef.current = abort;
    try {
      const m = await promise;
      onUploaded(m);
      setFile(null);
      setTitle("");
      setMinSp("");
      setMaxSp("");
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setProgress(null);
      abortRef.current = null;
    }
  }

  const uploading = progress !== null;
  const input = "w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900";

  return (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-neutral-200 p-5 dark:border-neutral-800">
      <h2 className="text-lg font-semibold">Meeting baru</h2>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          pick(e.dataTransfer.files[0]);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-4 py-8 text-center transition ${
          drag ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30" : "border-neutral-300 dark:border-neutral-700"
        }`}
      >
        <input ref={inputRef} type="file" accept={ACCEPT} className="sr-only" onChange={(e) => pick(e.target.files?.[0])} disabled={uploading} />
        {file ? (
          <>
            <span className="font-medium">{file.name}</span>
            <span className="text-xs text-neutral-500">{(file.size / 1024 / 1024).toFixed(1)} MB · klik untuk ganti</span>
          </>
        ) : (
          <>
            <span className="font-medium">Tarik file rekaman ke sini, atau klik untuk memilih</span>
            <span className="text-xs text-neutral-500">m4a, mp3, wav, ogg, opus, mp4, dll.</span>
          </>
        )}
      </label>

      <div>
        <label className="mb-1 block text-sm font-medium">Judul</label>
        <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="mis. Rapat mingguan" disabled={uploading} />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium" htmlFor="upload-language">
          Bahasa rekaman
        </label>
        <select
          id="upload-language"
          className={input}
          value={language}
          onChange={(e) => chooseLanguage(e.target.value)}
          disabled={uploading}
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
        {language === "auto" && (
          <p className="mt-1 text-xs text-neutral-500">Bahasa ditebak dari 30 detik pertama. Pilih manual jika hasilnya salah.</p>
        )}
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Perkiraan jumlah peserta <span className="font-normal text-neutral-500">(opsional, membantu akurasi)</span>
        </label>
        <div className="flex items-center gap-2">
          <input className={input} type="number" min={1} max={50} placeholder="min" value={minSp} onChange={(e) => setMinSp(e.target.value)} disabled={uploading} />
          <span className="text-neutral-500">–</span>
          <input className={input} type="number" min={1} max={50} placeholder="maks" value={maxSp} onChange={(e) => setMaxSp(e.target.value)} disabled={uploading} />
        </div>
      </div>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}

      {uploading ? (
        <div className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
            <div className="h-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="flex justify-between text-sm">
            <span>Mengunggah… {progress}%</span>
            <button type="button" className="text-red-600 hover:underline" onClick={() => abortRef.current?.()}>
              Batal
            </button>
          </div>
        </div>
      ) : (
        <button
          type="submit"
          disabled={!file}
          className="w-full rounded-lg bg-blue-600 px-4 py-2.5 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Upload & proses
        </button>
      )}
    </form>
  );
}
