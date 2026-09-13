"use client";

import * as React from "react";
import { useT } from "@/lib/i18n/use-t";
import { ErrorState } from "@/components/waterexpert/ui-states";

/**
 * Stops a panel's throw from taking the page with it.
 *
 * This is not hypothetical tidiness. The knowledge-graph view threw from a
 * vis-network effect — `network.fit` handed a node id the canvas did not hold —
 * and because the app had no boundary anywhere, what the user saw was the
 * framework's blank "This page couldn't load / Reload to try again". No panel,
 * no message, nothing naming what had failed. A visible wrong answer is
 * recoverable; a blank page is not, and it is the one failure that makes
 * everything else untraceable.
 *
 * Deliberately not app-wide: it wraps the graph panels, which are the ones that
 * render a canvas and drive a third-party layout engine. A boundary over the
 * whole shell would hide failures that should be loud.
 *
 * `resetKey` is the retry that actually recovers. When whatever was being drawn
 * changes — a new request, a different focus — the boundary clears itself, so a
 * single bad subgraph does not strand the tab until a full reload.
 */
interface PanelErrorBoundaryProps {
  children: React.ReactNode;
  /** Changing this clears a caught error. Omit to keep the failure until retried. */
  resetKey?: string | null;
}

interface PanelErrorBoundaryState {
  message: string | null;
}

export class PanelErrorBoundary extends React.Component<
  PanelErrorBoundaryProps,
  PanelErrorBoundaryState
> {
  state: PanelErrorBoundaryState = { message: null };

  static getDerivedStateFromError(error: unknown): PanelErrorBoundaryState {
    return { message: error instanceof Error ? error.message : String(error) };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    // Kept because this is the only place the real cause is still legible: the
    // fallback shows a localized sentence, not a stack.
    console.error("KG panel crashed:", error, info.componentStack);
  }

  componentDidUpdate(previous: PanelErrorBoundaryProps) {
    if (this.state.message !== null && previous.resetKey !== this.props.resetKey) {
      this.setState({ message: null });
    }
  }

  render() {
    if (this.state.message === null) return this.props.children;
    return <PanelErrorFallback message={this.state.message} onRetry={this.reset} />;
  }

  private reset = () => this.setState({ message: null });
}

/** A function component so the fallback can localize like everything else. */
function PanelErrorFallback({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useT();
  return (
    <div className="flex flex-col gap-2">
      <ErrorState message={t("kg.panelError")} onRetry={onRetry} />
      {/* The raw message, in the monospace slot the rest of the app uses for
          identifiers and diagnostics. */}
      <p className="text-muted-foreground font-mono text-xs break-all">{message}</p>
    </div>
  );
}
