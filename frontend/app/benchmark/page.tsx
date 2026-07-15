import type { Metadata } from "next";
import { ProductShell } from "../components/product-shell";

import { BenchmarkLab } from "./benchmark-lab";

export const metadata: Metadata = {
  title: "Benchmark Lab",
  description: "Offline planning benchmark evidence for AI Parametric Architect.",
};

export default function BenchmarkPage() {
  return (
    <ProductShell active="benchmark" density="document">
      <BenchmarkLab />
    </ProductShell>
  );
}
