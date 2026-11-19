import { redirect } from "next/navigation";

// Halaman lama "Kosakata & koreksi" kini digabung ke "Periksa & Kamus"
export default function OldGlossaryPage() {
  redirect("/kamus");
}
