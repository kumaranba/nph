"use client";

import {
  CategoryScale,
  Chart as ChartJS,
  type ChartOptions,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import annotationPlugin from "chartjs-plugin-annotation";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  annotationPlugin
);

type Props = {
  title: string;
  unit?: string;
  labels: string[];
  values: (number | null)[];
  below: number | null;
  above: number | null;
};

export function VitalChart({ title, unit, labels, values, below, above }: Props) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const annotations: Record<string, any> = {};
  // Shade the acceptable range (between the below/above thresholds) as a
  // faint green horizontal band.
  if (below !== null || above !== null) {
    annotations.safeBand = {
      type: "box",
      yMin: below ?? undefined,
      yMax: above ?? undefined,
      backgroundColor: "rgba(34, 197, 94, 0.10)",
      borderWidth: 0,
    };
  }

  const data = {
    labels,
    datasets: [
      {
        label: title,
        data: values,
        borderColor: "#2563eb",
        backgroundColor: "#2563eb",
        spanGaps: true,
        tension: 0.25,
        pointRadius: 3,
      },
    ],
  };

  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      // annotation plugin options; typed loosely above to avoid deep generics.
      annotation: { annotations },
    },
    scales: {
      y: unit ? { title: { display: true, text: unit } } : {},
    },
  };

  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      <div className="h-56">
        <Line data={data} options={options} />
      </div>
    </div>
  );
}
