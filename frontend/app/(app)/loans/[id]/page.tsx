"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Loan, LoanPayment, montra } from "@/lib/api";
import { PageHeader } from "@/components/shell";
import { formatDate, formatMoney } from "@/lib/format";
import { Button, Card, EmptyState, Skeleton, StatusChip } from "@/components/ui";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-white/5 py-3 last:border-0">
      <span className="text-sm text-content-secondary">{label}</span>
      <span className="tabular text-sm font-medium text-content-primary">{value}</span>
    </div>
  );
}

export default function LoanDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [loan, setLoan] = useState<Loan | null>(null);
  const [payments, setPayments] = useState<LoanPayment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([montra.loan(id), montra.loanPayments(id)])
      .then(([l, p]) => {
        setLoan(l);
        setPayments(p);
      })
      .catch(() => setLoan(null))
      .finally(() => setLoading(false));
  }, [id]);

  async function archive() {
    await montra.archiveLoan(id);
    router.push("/loans");
    router.refresh();
  }

  if (loading) {
    return (
      <>
        <PageHeader title="Loan" icon="handshake" />
        <Skeleton className="h-56 w-full" />
      </>
    );
  }

  if (!loan) {
    return (
      <>
        <PageHeader title="Loan" icon="handshake" />
        <EmptyState title="Loan not found" message="It may have been removed." />
      </>
    );
  }

  const owed = loan.direction === "PAYABLE";
  const money = (v: string) => formatMoney(v, loan.currency);

  return (
    <>
      <PageHeader title={loan.name} icon="handshake" />

      <Card className="mb-4">
        <div className="flex items-center gap-2">
          <p className="text-xs uppercase tracking-wide text-content-muted">
            {owed ? "Outstanding" : "Still owed to you"}
          </p>
          <StatusChip tone={owed ? "expense" : "income"}>
            {owed ? "I owe" : "Owed to me"}
          </StatusChip>
        </div>
        <p className="tabular mt-1 text-value sm:text-value-lg">
          {money(loan.outstanding_principal)}
        </p>
        <div
          role="progressbar"
          aria-valuenow={Math.round(Number(loan.percent_paid ?? 0))}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Principal repaid"
          className="mt-4 h-2 w-full overflow-hidden rounded-full bg-white/8"
        >
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: `${Math.min(Number(loan.percent_paid ?? 0), 100)}%` }}
          />
        </div>
        <p className="mt-1.5 text-xs text-content-muted">
          {loan.percent_paid ?? "0"}% of {money(loan.original_principal)} cleared
        </p>
      </Card>

      {loan.status === "ACTIVE" && (
        <div className="mb-6 flex flex-wrap gap-3">
          <Button onClick={() => router.push(`/loans/${id}/pay`)}>
            {owed ? "Record payment" : "Record repayment"}
          </Button>
          <Button variant="destructive" onClick={archive}>
            Archive
          </Button>
        </div>
      )}

      <Card className="mb-6">
        <p className="mb-1 text-xs uppercase tracking-wide text-content-muted">Details</p>
        {loan.counterparty && <Row label="Counterparty" value={loan.counterparty} />}
        <Row label="Original principal" value={money(loan.original_principal)} />
        <Row label="Principal cleared" value={money(loan.principal_paid)} />
        {loan.interest_rate && <Row label="Interest rate" value={`${loan.interest_rate}%`} />}
        <Row label="Started" value={loan.start_date} />
        {loan.end_date && <Row label="Ends" value={loan.end_date} />}
        {loan.expected_payment_amount && (
          <Row
            label="Expected payment"
            value={`${money(loan.expected_payment_amount)}${
              loan.payment_frequency ? ` · ${loan.payment_frequency.toLowerCase()}` : ""
            }`}
          />
        )}
        {loan.next_payment_date && <Row label="Next payment" value={loan.next_payment_date} />}
      </Card>

      <h2 className="mb-3 text-section">Payment history</h2>
      {payments.length === 0 ? (
        <EmptyState
          title="No payments yet"
          message="Recorded payments and how they split will appear here."
        />
      ) : (
        <Card>
          {payments.map((p) => (
            <div key={p.id} className="border-b border-white/5 py-3 last:border-0">
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-sm text-content-primary">
                  {formatDate(`${p.payment_date}T00:00:00`)}
                </span>
                <span className="tabular text-sm font-semibold text-content-primary">
                  {money(p.total_amount)}
                </span>
              </div>
              {/* The split is the point: only principal moved the loan. */}
              <p className="mt-1 text-xs text-content-secondary">
                {money(p.principal_amount)} principal
                {Number(p.interest_amount) > 0 && ` · ${money(p.interest_amount)} interest`}
                {Number(p.fee_amount) > 0 && ` · ${money(p.fee_amount)} fees`}
              </p>
            </div>
          ))}
        </Card>
      )}
    </>
  );
}
