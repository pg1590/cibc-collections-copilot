"use client";

import { createContext, useContext } from "react";

/**
 * Pages holding unsaved work (a live call) set a message here; links that leave
 * the page, like policy citations, ask before navigating while it is set.
 */
export const LeaveGuardContext = createContext<string | null>(null);

export function useLeaveGuard() {
  const message = useContext(LeaveGuardContext);
  return (event: React.MouseEvent) => {
    if (message && !window.confirm(message)) event.preventDefault();
  };
}
