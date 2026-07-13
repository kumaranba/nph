"use client";

import Link from "next/link";
import { Plus, HeartPulse, Banknote } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useMe } from "@/lib/me-context";
import { AppTopbar } from "@/components/app-topbar";
import { KpiCards } from "@/components/dashboard/kpi-cards";
import { PaymentsTrendCard } from "@/components/dashboard/payments-trend";
import { FeesDueCard } from "@/components/dashboard/fees-due-card";
import { FlaggedVitalsCard } from "@/components/dashboard/flagged-vitals-card";
import { RecentAdmissionsCard } from "@/components/dashboard/recent-admissions-card";
import { WardOccupancyCard } from "@/components/dashboard/ward-occupancy-card";
import { ActivityCard } from "@/components/dashboard/activity-card";

export default function DashboardPage() {
  const me = useMe();
  const role = me?.role ?? "ADMIN";
  const isNurse = role === "NURSE";
  const isFinance = role === "FINANCE";

  // Role-adaptive: Nurse hides billing panels, Finance hides the clinical feed.
  const showBilling = !isNurse; // payments trend + fees-due table
  const showClinicalFeed = !isFinance; // flagged vitals feed

  const firstName = me?.email ? me.email.split("@")[0] : "";

  return (
    <>
      <AppTopbar title="Dashboard" />

      <main className="mx-auto flex w-full max-w-[1520px] flex-col gap-5 p-[22px] pb-10 md:px-6">
        {/* Page header */}
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Good morning{firstName ? `, ${firstName}` : ""}
            </h1>
            <p className="mt-1.5 text-[13.5px] text-muted-foreground">
              Here&apos;s what&apos;s happening at Nila Psychiatric Hospital today
            </p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <Button asChild className="h-[38px] gap-2">
              <Link href="/admissions/new">
                <Plus className="h-4 w-4" />
                New admission
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-[38px] gap-2">
              <Link href="/vitals/new">
                <HeartPulse className="h-4 w-4" />
                Log vitals
              </Link>
            </Button>
            {showBilling ? (
              <Button asChild variant="outline" className="h-[38px] gap-2">
                <Link href="/fees-due">
                  <Banknote className="h-4 w-4" />
                  Log payment
                </Link>
              </Button>
            ) : null}
          </div>
        </div>

        {/* KPIs */}
        <KpiCards />

        {/* Trend + fees | vitals + admissions */}
        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.6fr_1fr]">
          <div className="flex min-w-0 flex-col gap-5">
            {showBilling ? <PaymentsTrendCard /> : null}
            {showBilling ? <FeesDueCard /> : null}
          </div>
          <div className="flex min-w-0 flex-col gap-5">
            {showClinicalFeed ? <FlaggedVitalsCard /> : null}
            <RecentAdmissionsCard />
          </div>
        </div>

        {/* Ward map | activity */}
        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.6fr_1fr]">
          <WardOccupancyCard />
          <ActivityCard />
        </div>
      </main>
    </>
  );
}
