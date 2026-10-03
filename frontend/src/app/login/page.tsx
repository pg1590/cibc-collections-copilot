"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BarChart3, Headset, Loader2, LogIn, ShieldCheck, type LucideIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";

// Demo account usernames match the roles. Passwords are configured in the
// backend's local environment (see README); none are stored here.
const ACCOUNTS: { username: Role; title: string; blurb: string; icon: LucideIcon }[] = [
  { username: "analyst", title: "Analyst", blurb: "Portfolio questions, data quality, features", icon: BarChart3 },
  { username: "agent", title: "Agent", blurb: "Assigned customers and call briefs", icon: Headset },
  { username: "supervisor", title: "Supervisor", blurb: "Review drafts, audit log, everything", icon: ShieldCheck },
];

export default function LoginPage() {
  const { session, ready, login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState<string>("analyst");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (ready && session) router.replace("/overview");
  }, [ready, session, router]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(username.trim(), password);
      router.replace("/overview");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-dvh lg:grid-cols-[1fr_1.1fr]">
      <section className="bg-sidebar text-sidebar-foreground hidden flex-col justify-between p-12 lg:flex">
        <p className="text-lg font-semibold text-white">Collections Copilot</p>
        <div className="max-w-md space-y-4">
          <h1 className="text-3xl leading-tight font-semibold text-white">
            One customer view, clear answers, and drafts a person approves.
          </h1>
          <p className="text-sidebar-muted leading-relaxed">
            Runs locally on the synthetic hackathon dataset. Every number comes from the data pipeline, every answer shows
            its SQL or sources, and no message reaches a customer without supervisor review.
          </p>
        </div>
        <p className="text-sidebar-muted text-sm">Team Adda Wale · CIBC Collections Hackathon 2026</p>
      </section>

      <section className="flex items-center justify-center px-4 py-12 sm:px-8">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-xl">Sign in</CardTitle>
            <CardDescription>Choose a local demo account. Your role decides what you can see and do.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-6">
              <fieldset className="space-y-2">
                <legend className="mb-2 text-sm font-medium">Account</legend>
                <div className="grid gap-2">
                  {ACCOUNTS.map(({ username: value, title, blurb, icon: Icon }) => (
                    <label
                      key={value}
                      className={cn(
                        "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/30",
                        username === value ? "border-primary bg-accent/50" : "hover:bg-muted",
                      )}
                    >
                      <input
                        type="radio"
                        name="account"
                        value={value}
                        checked={username === value}
                        onChange={() => setUsername(value)}
                        className="sr-only"
                      />
                      <Icon className={cn("size-5", username === value ? "text-primary" : "text-muted-foreground")} aria-hidden />
                      <span>
                        <span className="block text-sm font-medium">{title}</span>
                        <span className="text-muted-foreground block text-xs">{blurb}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-describedby="password-help"
                />
                <p id="password-help" className="text-muted-foreground text-xs">
                  Set by the backend&apos;s local configuration. See the project README for local defaults.
                </p>
              </div>

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <Button type="submit" className="w-full" size="lg" disabled={pending || !username || !password}>
                {pending ? <Loader2 className="animate-spin" aria-hidden /> : <LogIn aria-hidden />}
                {pending ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
