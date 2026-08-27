"use client";

import { useMutation } from "@apollo/client";
import { FormEvent, useState } from "react";

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
import { SUBMIT_WEB_ENQUIRY } from "@/lib/graphql/operations";

type SubmitResult = { submitWebEnquiry: { ok: boolean; message: string } };

export default function EnquirePage() {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [company, setCompany] = useState(""); // honeypot
  const [done, setDone] = useState<string | null>(null);

  const [submit, { loading, error }] = useMutation<SubmitResult>(
    SUBMIT_WEB_ENQUIRY,
    {
      onCompleted: (data) => setDone(data.submitWebEnquiry.message),
      onError: () => {},
    }
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit({
      variables: { data: { name, phone, email, message, company } },
    });
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4 sm:p-8">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Enquire about admission</CardTitle>
          <CardDescription>
            Leave your details and our patient-relations team will contact you.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {done ? (
            <div className="rounded-lg border bg-green-50 p-4 text-center">
              <p className="text-sm font-medium text-green-800">{done}</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => {
                  setName("");
                  setPhone("");
                  setEmail("");
                  setMessage("");
                  setDone(null);
                }}
              >
                Submit another enquiry
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Your name</Label>
                <Input
                  id="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="phone">Phone</Label>
                  <Input
                    id="phone"
                    type="tel"
                    inputMode="tel"
                    placeholder="98765 43210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>
              <p className="-mt-1 text-xs text-muted-foreground">
                Give us a phone number or email so we can reach you.
              </p>
              <div className="space-y-2">
                <Label htmlFor="message">How can we help? (optional)</Label>
                <textarea
                  id="message"
                  rows={4}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
              </div>
              {/* Honeypot: hidden from real users; bots tend to fill it. */}
              <div className="hidden" aria-hidden="true">
                <label htmlFor="company">Company</label>
                <input
                  id="company"
                  tabIndex={-1}
                  autoComplete="off"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                />
              </div>
              {error ? (
                <p className="text-sm text-red-600">{error.message}</p>
              ) : null}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Sending…" : "Send enquiry"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
