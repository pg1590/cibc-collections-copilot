"use client";

import { ShieldAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { canSee, SECTION_ROLES, useAuth, type Section } from "@/lib/auth";

/** Hides a section from roles that cannot use it. The backend still enforces access. */
export function RoleGate({ section, children }: { section: Section; children: React.ReactNode }) {
  const { session } = useAuth();
  if (canSee(session?.user.role, section)) return <>{children}</>;
  return (
    <Alert>
      <ShieldAlert aria-hidden />
      <AlertTitle>Not available for your role</AlertTitle>
      <AlertDescription>
        <p>
          This section is for the {SECTION_ROLES[section].join(" and ")} roles. You are signed in as{" "}
          <strong>{session?.user.role}</strong>.
        </p>
      </AlertDescription>
    </Alert>
  );
}
