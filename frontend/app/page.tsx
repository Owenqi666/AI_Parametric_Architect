import { ProductShell } from "./components/product-shell";
import { DesignStudioClient } from "./design-studio-client";

export default function Home() {
  return (
    <ProductShell active="studio">
      <DesignStudioClient />
    </ProductShell>
  );
}
