"use client";

import { useQuery } from "@apollo/client";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  type ChartData,
  type ChartOptions,
} from "chart.js";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError } from "@/components/query-states";
import { PAYMENTS_TREND } from "@/lib/graphql/dashboard-operations";
import { formatLakh } from "@/components/dashboard/format";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

type Point = { month: string; total: string };

export function PaymentsTrendCard() {
  const { data, loading, error, refetch } = useQuery<{ paymentsTrend: Point[] }>(
    PAYMENTS_TREND,
    { variables: { months: 8 } }
  );

  const points = data?.paymentsTrend ?? [];
  const latest = points.length ? Number(points[points.length - 1].total) : 0;
  const prev = points.length > 1 ? Number(points[points.length - 2].total) : 0;
  const delta = prev ? ((latest - prev) / prev) * 100 : 0;

  const chartData: ChartData<"line"> = {
    labels: points.map((p) => p.month),
    datasets: [
      {
        data: points.map((p) => Number(p.total)),
        borderColor: "#18181b",
        borderWidth: 2,
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: "#18181b",
        backgroundColor: (ctx) => {
          const { chart } = ctx;
          const g = chart.ctx.createLinearGradient(0, 0, 0, chart.height || 190);
          g.addColorStop(0, "rgba(24,24,27,0.12)");
          g.addColorStop(1, "rgba(24,24,27,0)");
          return g;
        },
      },
    ],
  };

  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: { label: (i) => formatLakh(i.parsed.y ?? 0) },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        border: { display: false },
        ticks: { color: "#a1a1aa", font: { size: 11 } },
      },
      y: {
        beginAtZero: false,
        grid: { color: "#f0f0f1" },
        border: { display: false },
        ticks: {
          color: "#b4b4bb",
          font: { size: 10 },
          callback: (v) => `${Number(v) / 100000}L`,
        },
      },
    },
  };

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-1 flex items-start justify-between">
        <div>
          <div className="text-sm font-semibold">Payments collected</div>
          <div className="mt-0.5 text-[12.5px] text-muted-foreground">
            Monthly collections · last {points.length || 8} months
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl font-semibold tabular-nums">{formatLakh(latest)}</div>
          <div
            className={`text-xs font-semibold ${
              delta >= 0 ? "text-emerald-700" : "text-red-600"
            }`}
          >
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}% vs prev
          </div>
        </div>
      </div>
      {loading ? (
        <LinesSkeleton lines={4} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : (
        <div className="h-[190px]">
          <Line data={chartData} options={options} />
        </div>
      )}
    </Card>
  );
}
