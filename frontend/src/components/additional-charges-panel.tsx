"use client";

import { useMutation } from "@apollo/client";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CREATE_CHARGE,
  DELETE_CHARGE,
  PATIENT,
} from "@/lib/graphql/operations";
import { formatDate } from "@/lib/format-date";

export type Charge = {
  id: string;
  category: string;
  amount: string;
  chargeDate: string;
  description: string;
};

const CATEGORIES = [
  "DRUGS",
  "SNACKS",
  "PERSONAL_CARE",
  "SPECIALIST",
  "OTHER",
] as const;

type ChargeForm = {
  category: (typeof CATEGORIES)[number];
  amount: string;
  chargeDate: string;
  description: string;
};

function money(value: string) {
  return `₹${Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

type Props = {
  admissionId: string;
  patientId: string;
  charges: Charge[];
  /** The Add form and delete buttons are Finance-only. */
  isFinance: boolean;
  /** Charges can only be added while the admission is active. */
  isActive: boolean;
};

export function AdditionalChargesPanel({
  admissionId,
  patientId,
  charges,
  isFinance,
  isActive,
}: Props) {
  const refetch = [{ query: PATIENT, variables: { pk: patientId } }];

  const { register, handleSubmit, reset } = useForm<ChargeForm>({
    defaultValues: {
      category: "DRUGS",
      amount: "",
      chargeDate: new Date().toISOString().slice(0, 10),
      description: "",
    },
  });

  const [createCharge, { loading: creating, error: createError }] = useMutation(
    CREATE_CHARGE,
    { refetchQueries: refetch, onCompleted: () => reset(), onError: () => {} }
  );

  const [deleteCharge, { error: deleteError }] = useMutation(DELETE_CHARGE, {
    refetchQueries: refetch,
    onError: () => {},
  });

  function onSubmit(values: ChargeForm) {
    createCharge({
      variables: {
        admissionId,
        category: values.category,
        amount: values.amount,
        chargeDate: values.chargeDate,
        description: values.description,
      },
    });
  }

  const total = charges.reduce((sum, c) => sum + Number(c.amount), 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Additional charges</CardTitle>
        <CardDescription>Drugs, snacks, specialist visits, etc.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Charge log */}
        {charges.length === 0 ? (
          <p className="text-sm text-muted-foreground">No charges logged yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Date</th>
                <th className="py-2 pr-4 font-medium">Category</th>
                <th className="py-2 pr-4 font-medium">Description</th>
                <th className="py-2 pr-4 text-right font-medium">Amount</th>
                {isFinance ? <th className="py-2" /> : null}
              </tr>
            </thead>
            <tbody>
              {charges.map((c) => (
                <tr key={c.id} className="border-b last:border-0">
                  <td className="py-2 pr-4">{formatDate(c.chargeDate)}</td>
                  <td className="py-2 pr-4">{c.category}</td>
                  <td className="py-2 pr-4 text-muted-foreground">
                    {c.description || "—"}
                  </td>
                  <td className="py-2 pr-4 text-right">{money(c.amount)}</td>
                  {isFinance ? (
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        className="text-xs text-red-600 hover:underline"
                        onClick={() =>
                          deleteCharge({ variables: { chargeId: c.id } })
                        }
                      >
                        Delete
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="font-medium">
                <td className="py-2" colSpan={3}>
                  Total
                </td>
                <td className="py-2 pr-4 text-right">{money(String(total))}</td>
                {isFinance ? <td /> : null}
              </tr>
            </tfoot>
          </table>
        )}

        {deleteError ? (
          <p className="text-sm text-red-600">{deleteError.message}</p>
        ) : null}

        {/* Add Charge form — Finance only, active admissions only */}
        {isFinance && isActive ? (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-4 border-t pt-4"
          >
            <p className="text-sm font-medium">Add charge</p>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="category">Category</Label>
                <select
                  id="category"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  {...register("category")}
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="amount">Amount</Label>
                <Input
                  id="amount"
                  type="number"
                  min={0}
                  step="0.01"
                  placeholder="0.00"
                  {...register("amount", { required: true })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="chargeDate">Date</Label>
                <Input
                  id="chargeDate"
                  type="date"
                  {...register("chargeDate", { required: true })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description (optional)</Label>
                <Input id="description" {...register("description")} />
              </div>
            </div>

            {createError ? (
              <p className="text-sm text-red-600">{createError.message}</p>
            ) : null}

            <Button type="submit" disabled={creating}>
              {creating ? "Adding…" : "Add charge"}
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
