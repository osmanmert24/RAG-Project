import { NextResponse } from "next/server";

// Ayrı bir route handler: next.config.ts'deki genel /api/:path* rewrite'ı büyük
// PDF'lerde ~30sn'de proxy timeout'una takılıyor (embedding uzun sürebiliyor,
// bkz. LEARNING.md Hata Defteri #4). Bu dosya doğrudan backend'e fetch yapar,
// rewrite proxy'sinin süre sınırını devreye sokmadan.
export async function POST(request: Request) {
  const formData = await request.formData();
  const backendRes = await fetch("http://127.0.0.1:8000/upload", {
    method: "POST",
    body: formData,
  });
  const body = await backendRes.text();
  return new NextResponse(body, {
    status: backendRes.status,
    headers: {
      "Content-Type": backendRes.headers.get("Content-Type") ?? "application/json",
    },
  });
}
