import { Suspense } from "react";
import { ReviewView } from "@/components/ReviewView";

export const metadata = { title: "Periksa transkrip · NoteYourMeet" };

export default function ReviewPage() {
  return (
    <Suspense fallback={<p className="text-neutral-500">Memuat…</p>}>
      <ReviewView />
    </Suspense>
  );
}
