"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { PageHeader } from "@/components/shell";
import { TransferForm } from "@/components/transfer-form";

/**
 * Standalone transfer route.
 *
 * Kept because account screens link here with a source pre-selected; the form
 * itself is shared with the Transfer tab on Add.
 */
function Transfer() {
  const params = useSearchParams();
  return (
    <>
      <PageHeader title="Transfer" icon="transfer" />
      <TransferForm defaultSourceId={params.get("from") ?? ""} />
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Transfer />
    </Suspense>
  );
}
