import { Suspense } from "react";
import { MeetingView } from "@/components/MeetingView";

export default function MeetingPage() {
  return (
    <Suspense fallback={<p className="text-neutral-500">Memuat…</p>}>
      <MeetingView />
    </Suspense>
  );
}
