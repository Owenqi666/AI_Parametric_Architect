import type { Metadata } from "next";
import Link from "next/link";
import { ProductShell } from "../components/product-shell";

import styles from "./architecture.module.css";

export const metadata: Metadata = {
  title: "Architecture & Safety — AI Parametric Architect Studio",
  description:
    "The trust boundaries that keep AI intent, solver proposals, rendering, and authoritative JSON revisions separate.",
};

const TRUST_CATEGORIES = [
  {
    index: "01",
    tone: "untrusted",
    title: "Untrusted input",
    description: "Requirements, provider output, datasets, and proposal metadata enter through strict boundaries.",
  },
  {
    index: "02",
    tone: "advisory",
    title: "Typed advisory",
    description: "DesignIntent, plans, and proposals are immutable candidate values, never persisted geometry.",
  },
  {
    index: "03",
    tone: "control",
    title: "Trusted control",
    description: "Authorization, complete validation, affected-entity checks, and CAS govern every write.",
  },
  {
    index: "04",
    tone: "authority",
    title: "Authoritative state",
    description: "Only a persisted JSON revision is the World Model. Authority is explicit and singular.",
  },
  {
    index: "05",
    tone: "derived",
    title: "Derived read-only",
    description: "SVG, Render IR, Three.js scenes, metrics, and reports can be recreated or discarded.",
  },
] as const;

const PROPOSAL_STAGES = [
  {
    number: "01",
    kicker: "Input",
    title: "Natural-language requirement",
    detail: "Untrusted text",
    tone: "untrusted",
  },
  {
    number: "02",
    kicker: "Interpret",
    title: "Requirement Agent",
    detail: "DesignIntent only",
    tone: "advisory",
  },
  {
    number: "03",
    kicker: "Plan",
    title: "CP-SAT constraint solver",
    detail: "Deterministic planning",
    tone: "control",
  },
  {
    number: "04",
    kicker: "Propose",
    title: "FloorPlanProposal v2",
    detail: "Detached Proposal",
    tone: "advisory",
  },
] as const;

const WRITE_STAGES = [
  { title: "PatchProposal", detail: "Untrusted candidate" },
  { title: "Authorization", detail: "Intent + capability policy" },
  { title: "Validation", detail: "Schema + semantic + geometry" },
  { title: "CAS Commit", detail: "Expected revision required" },
  { title: "JSON Revision", detail: "Authoritative World Model" },
  { title: "Trusted Audit", detail: "Authenticated identity" },
] as const;

const BOUNDARIES = [
  {
    number: "01",
    title: "LLM interprets intent—not geometry",
    text: "The opt-in OpenAI adapter receives requirement text and returns a locally validated DesignIntent. It has no World Model, revision, geometry, repository, Patch, tool, authorization, or commit access.",
    evidence: "Intent-only provider boundary",
  },
  {
    number: "02",
    title: "Solver output stays detached",
    text: "CP-SAT produces a typed FloorPlanProposal v2. Its coordinates are advisory planning output and cannot enter the World Model Render IR projector or create committed geometry.",
    evidence: "Detached Proposal · Not committed to World Model",
  },
  {
    number: "03",
    title: "Evaluation is not authorization",
    text: "Planning metrics and benchmark reports are reproducible evidence. A high score, a valid plan, or a proposal digest never grants write authority and is rejected at the commit boundary.",
    evidence: "Evidence only · No write authority",
  },
  {
    number: "04",
    title: "Render IR is a read-only projection",
    text: "Only a completely validated authoritative ModelDocument can produce Render IR 1.0.0. The browser admits that versioned derivative and builds a disposable Three.js scene with no Patch or repository client.",
    evidence: "Derived read-only · Reproducible from revision",
  },
  {
    number: "05",
    title: "CAS prevents stale writes",
    text: "A candidate is applied to a defensive JSON copy, fully validated, and committed only when its expected base revision still matches the repository head. A concurrent change fails closed.",
    evidence: "Compare-and-swap · Monotonic revisions",
  },
  {
    number: "06",
    title: "Audit identity travels separately",
    text: "TrustedAuditIdentity comes from authenticated application context. Proposal provenance and rationale remain explicitly untrusted and cannot claim a human or system identity.",
    evidence: "Trusted actor channel · Append-only event",
  },
] as const;

function ToneTag({ tone, children }: { tone: string; children: React.ReactNode }) {
  return (
    <span className={styles.toneTag} data-tone={tone}>
      <span className={styles.toneDot} aria-hidden="true" />
      {children}
    </span>
  );
}

export default function ArchitectureSafetyPage() {
  return (
    <ProductShell active="architecture" density="document">
      <div className={styles.page}>
        <main id="architecture-content" className={styles.main}>
        <section className={styles.hero} aria-labelledby="architecture-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>Trust architecture · Contract 01</p>
            <h1 id="architecture-title">
              Intelligence proposes.{" "}
              <span>Deterministic controls decide.</span>
            </h1>
            <p className={styles.heroLead}>
              A safe, constraint-aware world-model planning environment where every artifact has
              one explicit trust role—and only a persisted JSON revision is authoritative.
            </p>
            <div className={styles.heroFacts} aria-label="Current system posture">
              <div>
                <strong>Offline by default</strong>
                <span>No API key or network required</span>
              </div>
              <div>
                <strong>Opt-in LLM</strong>
                <span>Requirement to DesignIntent only</span>
              </div>
              <div>
                <strong>Strict write path</strong>
                <span>Authorize · validate · CAS · audit</span>
              </div>
            </div>
          </div>

          <aside className={styles.authorityCard} aria-label="World Model authority invariant">
            <div className={styles.cardHeader}>
              <span>Authority invariant</span>
              <span className={styles.cardIndex}>WM / 01</span>
            </div>
            <div className={styles.authorityCore}>
              <span className={styles.orbit} aria-hidden="true" />
              <span className={styles.coreLabel}>ONLY</span>
              <strong>Persisted JSON Revision</strong>
              <small>Authoritative World Model</small>
            </div>
            <div className={styles.notAuthority}>
              <span>Never authoritative</span>
              <p>DesignIntent · Proposal · solver coordinates · metrics · Render IR · scene state</p>
            </div>
          </aside>
        </section>

        <section className={styles.trustSection} aria-labelledby="trust-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Five trust categories</p>
              <h2 id="trust-title">A visible type system for authority</h2>
            </div>
            <p>Color reinforces the category; the text label always carries the meaning.</p>
          </div>
          <ol className={styles.trustGrid} aria-label="Five trust categories">
            {TRUST_CATEGORIES.map((category) => (
              <li key={category.index} data-trust-category={category.tone}>
                <div className={styles.trustTopline}>
                  <span>{category.index}</span>
                  <ToneTag tone={category.tone}>{category.title}</ToneTag>
                </div>
                <p>{category.description}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.pipelineSection} aria-labelledby="pipeline-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Proposal lane</p>
              <h2 id="pipeline-title">Natural language stops at a detached plan</h2>
            </div>
            <div className={styles.pipelineLegend}>
              <ToneTag tone="advisory">Advisory planning output</ToneTag>
              <ToneTag tone="authority">World Model authority</ToneTag>
            </div>
          </div>

          <ol className={styles.proposalFlow} aria-label="Requirement to detached proposal pipeline">
            {PROPOSAL_STAGES.map((stage) => (
              <li className={styles.flowNode} key={stage.number} data-tone={stage.tone}>
                <span className={styles.flowNumber}>{stage.number}</span>
                <span className={styles.flowKicker}>{stage.kicker}</span>
                <strong>{stage.title}</strong>
                <small>{stage.detail}</small>
              </li>
            ))}
          </ol>

          <div className={styles.detachedBoundary} role="note">
            <span className={styles.lockMark} aria-hidden="true">×</span>
            <div>
              <strong>Detached Planning Sandbox</strong>
              <span>Detached Proposal · Not committed to World Model · Advisory planning output</span>
            </div>
            <p>
              Solver rectangles do not cross this boundary. Geometry realization would require a
              separately authorized Patch and the complete write path below.
            </p>
          </div>

          <div className={styles.writeLane}>
            <div className={styles.laneLabel}>
              <span>Mandatory write path</span>
              <small>No shortcuts</small>
            </div>
            <ol className={styles.writeFlow} aria-label="Mandatory authoritative write path">
              {WRITE_STAGES.map((stage, index) => (
                <li key={stage.title} data-final={index === WRITE_STAGES.length - 2}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{stage.title}</strong>
                  <small>{stage.detail}</small>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className={styles.boundarySection} aria-labelledby="boundaries-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>Six enforced boundaries</p>
              <h2 id="boundaries-title">Capability is narrower than connectivity</h2>
            </div>
            <p>Each component receives only the data and authority required for its role.</p>
          </div>
          <div className={styles.boundaryGrid}>
            {BOUNDARIES.map((boundary) => (
              <article key={boundary.number}>
                <span className={styles.boundaryNumber}>{boundary.number}</span>
                <h3>{boundary.title}</h3>
                <p>{boundary.text}</p>
                <footer>{boundary.evidence}</footer>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.readPath} aria-labelledby="read-path-title">
          <div>
            <p className={styles.eyebrow}>One-way read path</p>
            <h2 id="read-path-title">Committed state can be projected. A projection cannot commit.</h2>
          </div>
          <ol aria-label="Authoritative World Model visualization path">
            <li><span>01</span><strong>JSON Revision</strong><small>Authoritative</small></li>
            <li><span>02</span><strong>Complete validation</strong><small>Strict admission</small></li>
            <li><span>03</span><strong>Render IR 1.0.0</strong><small>Immutable derivative</small></li>
            <li><span>04</span><strong>Three.js scene</strong><small>Disposable read-only state</small></li>
          </ol>
        </section>

        <footer className={styles.pageFooter}>
          <div>
            <strong>Safe by capability design</strong>
            <p>
              Trace records retain tenant-scoped keyed digests and allowlisted metadata—not prompts,
              secrets, tool payloads, rationale, or chain-of-thought.
            </p>
          </div>
          <Link href="/">Return to Design Studio <span aria-hidden="true">↗</span></Link>
        </footer>
        </main>
      </div>
    </ProductShell>
  );
}
