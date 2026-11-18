"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, isProcessing, type MeetingSummary } from "@/lib/api";
import { dateTime, humanDuration } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";
import { UploadForm } from "./UploadForm";

export function Dashboard() {
  const [meetings, setMeetings] = useState<MeetingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMeetings(await api.listMeetings());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0); // muat awal (di callback, bukan langsung di effect)
    return () => clearTimeout(t);
  }, [load]);

  const anyBusy = meetings?.some((m) => isProcessing(m.status));
  useEffect(() => {
    if (!anyBusy) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [anyBusy, load]);

  return (
    <div className="grid gap-8 md:grid-cols-[minmax(0,360px)_1fr]">
      <UploadForm onUploaded={(m) => setMeetings((prev) => [m, ...(prev ?? [])])} />

      <section>
        <h2 className="mb-3 text-lg font-semibold">Daftar meeting</h2>
        {error && (
          <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            Gagal memuat: {error}
          </p>
        )}
        {meetings === null && !error && <p className="text-sm text-neutral-500">Memuat…</p>}
        {meetings?.length === 0 && (
          <p className="rounded-xl border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-500 dark:border-neutral-700">
            Belum ada meeting. Upload rekaman pertama kamu.
          </p>
        )}
        <ul className="divide-y divide-neutral-200 rounded-2xl border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
          {meetings?.map((m) => (
            <li key={m.id}>
              <Link href={`/meetings/${m.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-900">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{m.title}</p>
                  <p className="truncate text-xs text-neutral-500">
                    {dateTime(m.created_at)} · {humanDuration(m.duration_sec)}
                    {m.speaker_count != null && ` · ${m.speaker_count} pembicara`}
                    {isProcessing(m.status) && m.status_detail && ` · ${m.status_detail}`}
                  </p>
                </div>
                <StatusBadge status={m.status} />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
