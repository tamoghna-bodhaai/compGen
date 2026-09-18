"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function LegacyHashRedirect() {
  const router = useRouter();
  useEffect(() => {
    const legacy = window.location.hash.replace(/^#/, "");
    if (/^\/(question-bank|new-paper)$/.test(legacy) || /^\/papers\/[^/]+$/.test(legacy)) {
      window.history.replaceState(null, "", window.location.pathname);
      router.replace(legacy);
    }
  }, [router]);
  return null;
}
