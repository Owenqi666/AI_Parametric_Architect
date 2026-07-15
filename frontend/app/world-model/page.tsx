import type { Metadata } from "next";
import { ProductShell } from "../components/product-shell";
import { WorldModelExplorerClient } from "./world-model-explorer-client";

export const metadata: Metadata = {
  title: "World Model Explorer",
  description: "Explore the authoritative sample World Model through its validated read-only Render IR projection.",
};

export default function WorldModelExplorerPage() {
  return (
    <ProductShell active="world-model">
      <WorldModelExplorerClient />
    </ProductShell>
  );
}

