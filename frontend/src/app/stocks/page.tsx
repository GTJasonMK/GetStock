"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import StocksPanel from "@/components/panels/StocksPanel";

function StocksPageInner() {
  const params = useSearchParams();
  const code = params.get("code") || "";
  return <StocksPanel initialCode={code} />;
}

export default function StocksPage() {
  return (
    <div className="h-[100dvh] bg-[var(--bg-primary)]">
      <Suspense fallback={<div className="p-6 text-gray-400">加载中...</div>}>
        <StocksPageInner />
      </Suspense>
    </div>
  );
}
