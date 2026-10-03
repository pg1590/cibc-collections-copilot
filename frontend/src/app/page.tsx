"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { session, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready) router.replace(session ? "/overview" : "/login");
  }, [ready, session, router]);
  return <p className="sr-only" role="status">Opening Collections Copilot…</p>;
}
