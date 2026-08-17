"use client";

import { useQuery } from "@apollo/client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { LogPaymentModal } from "@/components/log-payment-modal";
import { LinesSkeleton, QueryError } from "@/components/query-states";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAccessToken } from "@/lib/auth";
import { INVOICE, ME } from "@/lib/graphql/operations";
import { formatDate } from "@/lib/format-date";

type Charge = {
  id: string;
  category: string;
  amount: string;
  chargeDate: string;
  description: string;
};

type Payment = { id: string; amount: string; paidOn: string };

type InvoiceResult = {
  invoice: {
    id: string;
    billingPeriodStart: string;
    billingPeriodEnd: string;
    baseFee: string;
    refundAmount: string;
    totalDue: string;
    amountPaid: string;
    balanceDue: string;
    status: "UNPAID" | "PARTIAL" | "PAID";
    admission: {
      id: string;
      patient: { id: string; patientId: string; name: string };
    };
    additionalCharges: Charge[];
    payments: Payment[];
  } | null;
};

type MeResult = { me: { id: string; email: string; role: string } };

const STATUS_BADGE: Record<string, string> = {
  UNPAID: "bg-red-100 text-red-800",
  PARTIAL: "bg-amber-100 text-amber-800",
  PAID: "bg-green-100 text-green-800",
};

function money(value: string) {
  return `₹${Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function InvoiceDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string; period: string }>();
  const [showPayment, setShowPayment] = useState(false);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data, loading, error, refetch } = useQuery<InvoiceResult>(INVOICE, {
    variables: { patientId: params.id, period: params.period },
    skip: !hasToken,
  });
  const { data: meData } = useQuery<MeResult>(ME, { skip: !hasToken });

  if (!hasToken || loading) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-4 sm:p-6 lg:p-8">
        <LinesSkeleton lines={8} />
      </main>
    );
  }

  if (error) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-4 sm:p-6 lg:p-8">
        <QueryError message={error.message} onRetry={() => refetch()} />
      </main>
    );
  }

  const invoice = data?.invoice;
  // ADMIN and FINANCE may record payments (NURSE may not).
  const canLogPayment =
    meData?.me.role === "ADMIN" || meData?.me.role === "FINANCE";

  if (!invoice) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-4 sm:p-6 lg:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Invoice not found</CardTitle>
            <CardDescription>
              No invoice exists for this patient and period ({params.period}).
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-2xl p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle>{invoice.admission.patient.name}</CardTitle>
              <CardDescription>
                {invoice.admission.patient.patientId} ·{" "}
                {formatDate(invoice.billingPeriodStart)} → {formatDate(invoice.billingPeriodEnd)}
              </CardDescription>
            </div>
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                STATUS_BADGE[invoice.status]
              }`}
            >
              {invoice.status}
            </span>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Charge breakdown */}
          <section>
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">
              Charges
            </h3>
            <table className="w-full text-sm">
              <tbody>
                <tr className="border-b">
                  <td className="py-2">Monthly base fee</td>
                  <td className="py-2 text-right">{money(invoice.baseFee)}</td>
                </tr>
                {invoice.additionalCharges.map((c) => (
                  <tr key={c.id} className="border-b">
                    <td className="py-2">
                      {c.category}
                      {c.description ? (
                        <span className="text-muted-foreground">
                          {" "}
                          — {c.description}
                        </span>
                      ) : null}
                      <span className="text-muted-foreground">
                        {" "}
                        ({formatDate(c.chargeDate)})
                      </span>
                    </td>
                    <td className="py-2 text-right">{money(c.amount)}</td>
                  </tr>
                ))}
                {Number(invoice.refundAmount) > 0 ? (
                  <tr className="border-b">
                    <td className="py-2 text-green-700">Refund</td>
                    <td className="py-2 text-right text-green-700">
                      −{money(invoice.refundAmount)}
                    </td>
                  </tr>
                ) : null}
              </tbody>
              <tfoot>
                <tr className="font-medium">
                  <td className="py-2">Total due</td>
                  <td className="py-2 text-right">{money(invoice.totalDue)}</td>
                </tr>
              </tfoot>
            </table>
          </section>

          {/* Payment summary */}
          <section className="rounded-md bg-muted/40 p-4 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Paid</span>
              <span>{money(invoice.amountPaid)}</span>
            </div>
            <div className="mt-1 flex justify-between font-medium">
              <span>Balance due</span>
              <span>{money(invoice.balanceDue)}</span>
            </div>
          </section>

          {/* Payment history */}
          <section>
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">
              Payment history
            </h3>
            {invoice.payments.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No payments recorded yet.
              </p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {invoice.payments.map((p) => (
                    <tr key={p.id} className="border-b last:border-0">
                      <td className="py-2">{formatDate(p.paidOn)}</td>
                      <td className="py-2 text-right">{money(p.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* Log Payment — Admin + Finance */}
          {canLogPayment && invoice.status !== "PAID" ? (
            <Button className="w-full" onClick={() => setShowPayment(true)}>
              Log payment
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {showPayment && canLogPayment ? (
        <LogPaymentModal
          invoiceId={invoice.id}
          patientId={params.id}
          period={params.period}
          balanceDue={money(invoice.balanceDue)}
          onClose={() => setShowPayment(false)}
        />
      ) : null}
    </main>
  );
}
