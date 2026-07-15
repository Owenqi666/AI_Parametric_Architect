import Link from "next/link";
import type { ReactNode } from "react";
import styles from "./product-shell.module.css";

export type ProductArea = "studio" | "benchmark" | "world-model" | "architecture";

const AREAS: readonly {
  readonly id: ProductArea;
  readonly href: string;
  readonly index: string;
  readonly label: string;
}[] = [
  { id: "studio", href: "/", index: "01", label: "Design Studio" },
  { id: "benchmark", href: "/benchmark", index: "02", label: "Benchmark Lab" },
  { id: "world-model", href: "/world-model", index: "03", label: "World Model" },
  { id: "architecture", href: "/architecture", index: "04", label: "Architecture & Safety" },
];

interface ProductShellProps {
  readonly active: ProductArea;
  readonly children: ReactNode;
  readonly density?: "workspace" | "document";
}

export function ProductShell({ active, children, density = "workspace" }: ProductShellProps) {
  return (
    <div className={styles.shell} data-density={density}>
      <a className={styles.skipLink} href="#main-content">
        Skip to main content
      </a>
      <header className={styles.productBar}>
        <Link className={styles.brand} href="/" aria-label="AI Parametric Architect Studio home">
          <span className={styles.brandGlyph} aria-hidden="true">
            AP
          </span>
          <span className={styles.brandCopy}>
            <strong>AI Parametric Architect</strong>
            <small>Studio</small>
          </span>
        </Link>

        <nav className={styles.navigation} aria-label="Primary product areas">
          {AREAS.map((area) => (
            <Link
              key={area.id}
              href={area.href}
              aria-current={active === area.id ? "page" : undefined}
              data-active={active === area.id}
            >
              <span aria-hidden="true">{area.index}</span>
              {area.label}
            </Link>
          ))}
        </nav>

        <div className={styles.systemStatus} aria-label="Showcase data posture">
          <i aria-hidden="true" />
          <span>
            <strong>Offline mode</strong>
            <small>Bundled evidence</small>
          </span>
        </div>
      </header>
      <main id="main-content" className={styles.main}>
        {children}
      </main>
    </div>
  );
}
