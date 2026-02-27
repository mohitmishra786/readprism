import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  const { token } = body;

  if (!token) {
    return NextResponse.json({ error: "No token provided" }, { status: 400 });
  }

  const cookieStore = cookies();
  cookieStore.set("readprism_token", token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: 86400,
    path: "/",
  });

  return NextResponse.json({ ok: true });
}

export async function DELETE() {
  const cookieStore = cookies();
  cookieStore.delete("readprism_token");
  return NextResponse.json({ ok: true });
}
