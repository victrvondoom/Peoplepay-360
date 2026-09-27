"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Error boundaries must be class components -- there is no hooks equivalent.
 * Used to isolate purely decorative subtrees (e.g. the 3D background scene)
 * so a crash there can't take down the whole page/app and block navigation;
 * it renders `fallback` (default: nothing) instead of the failed subtree.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary caught an error (isolated, rest of the page is unaffected):", error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? null;
    }
    return this.props.children;
  }
}
