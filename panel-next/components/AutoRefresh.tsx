"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AutoRefresh({ interval = 10000 }: { interval?: number }) {
  const router = useRouter();
  useEffect(() => {
    const t = setInterval(() => router.refresh(), interval);
    return () => clearInterval(t);
  }, [router, interval]);
  return null;
}
