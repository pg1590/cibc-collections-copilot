"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, BarChart3, Check, Eye, EyeOff, Headset, Loader2, ShieldCheck, type LucideIcon } from "lucide-react";
import { BrandMark } from "@/components/landing/brand-mark";
import { SiteFooter } from "@/components/site-footer";
import { ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";

// Demo account usernames match the roles. Passwords are configured in the
// backend's local environment (see README); none are stored here.
const ACCOUNTS: { username: Role; title: string; blurb: string; icon: LucideIcon }[] = [
  { username: "analyst", title: "Analyst", blurb: "Portfolio questions and data checks", icon: BarChart3 },
  { username: "agent", title: "Agent", blurb: "Your queue, calls and briefs", icon: Headset },
  { username: "supervisor", title: "Supervisor", blurb: "Reviews, audit log and everything else", icon: ShieldCheck },
];

const isRole = (value: string | null): value is Role => ACCOUNTS.some((a) => a.username === value);

export default function LoginPage() {
  const { session, ready, login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState<string>("analyst");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ready && session) router.replace("/overview");
  }, [ready, session, router]);

  // The welcome page links here with ?role=agent and so on.
  useEffect(() => {
    const role = new URLSearchParams(window.location.search).get("role");
    if (isRole(role)) setUsername(role);
  }, []);

  const selected = ACCOUNTS.find((a) => a.username === username.trim());

  function chooseAccount(value: Role) {
    setUsername(value);
    setError(null);
    passwordRef.current?.focus();
  }

  function trackCapsLock(event: React.KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState("CapsLock"));
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(username.trim(), password);
      router.replace("/overview");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "That password doesn't match this account. Check it and try again."
          : errorMessage(err),
      );
      passwordRef.current?.select();
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="font-humane bg-mist text-ink-soft flex min-h-dvh flex-col">
      <header className="site-bar">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <Link href="/" className="focus-visible:ring-primary/40 flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-[3px]">
            <BrandMark />
            <span className="text-[1.0625rem] font-medium">Collections Copilot</span>
          </Link>
          <Link
            href="/"
            className="text-slate hover:text-ink-soft hover:bg-seaglass/60 focus-visible:ring-primary/40 rounded-full px-4 py-2 text-[0.9375rem] outline-none focus-visible:ring-[3px]"
          >
            Back to home
          </Link>
        </div>
      </header>

      <main className="flex flex-1 items-start justify-center px-4 pt-8 pb-14 sm:items-center sm:pt-10">
        <section
          aria-labelledby="signin-heading"
          className="bg-paper border-line-soft w-full max-w-[27rem] rounded-[1.25rem] border p-6 shadow-[0_1px_0_rgb(31_45_61/0.04),0_28px_60px_-30px_rgb(31_45_61/0.22)] sm:p-8"
        >
          <h1 id="signin-heading" className="text-[1.75rem] leading-tight font-normal tracking-[-0.02em]">
            Sign in
          </h1>
          <p className="text-slate mt-2 text-[0.9375rem] leading-relaxed">
            Choose how you&apos;re working today. Your role decides what you can see and do.
          </p>

          <form onSubmit={onSubmit} className="mt-7 space-y-6">
            <fieldset>
              <legend className="mb-2.5 text-[0.9375rem] font-medium">I&apos;m working as</legend>
              <div className="grid gap-2">
                {ACCOUNTS.map(({ username: value, title, blurb, icon: Icon }) => {
                  const active = selected?.username === value;
                  return (
                    <label
                      key={value}
                      className={cn(
                        "flex cursor-pointer items-center gap-3.5 rounded-xl border px-4 py-3 transition-colors",
                        "has-[:focus-visible]:ring-primary/35 has-[:focus-visible]:ring-[3px]",
                        active ? "border-primary/60 bg-seaglass/45" : "border-line-soft hover:bg-mist/70",
                      )}
                    >
                      <input
                        type="radio"
                        name="account"
                        value={value}
                        checked={active}
                        onChange={() => chooseAccount(value)}
                        className="sr-only"
                      />
                      <Icon className={cn("size-5 shrink-0", active ? "text-primary" : "text-slate")} aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">{title}</span>
                        <span className="text-slate block text-sm">{blurb}</span>
                      </span>
                      <span
                        aria-hidden
                        className={cn(
                          "grid size-5 shrink-0 place-items-center rounded-full border transition-colors",
                          active ? "bg-primary border-primary text-primary-foreground" : "border-seaglass-deep",
                        )}
                      >
                        {active && <Check className="size-3.5" strokeWidth={3} />}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <div className="space-y-2">
              <label htmlFor="username" className="block text-[0.9375rem] font-medium">
                Username
              </label>
              <input
                id="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className={fieldClass}
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="block text-[0.9375rem] font-medium">
                Password
              </label>
              <div className="relative">
                <input
                  ref={passwordRef}
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  autoFocus
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={trackCapsLock}
                  onKeyUp={trackCapsLock}
                  aria-invalid={error ? true : undefined}
                  aria-describedby="password-help"
                  className={cn(fieldClass, "pr-20")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-pressed={showPassword}
                  className="text-slate hover:text-ink-soft hover:bg-mist focus-visible:ring-primary/35 absolute inset-y-1.5 right-1.5 inline-flex items-center gap-1.5 rounded-lg px-2.5 text-sm outline-none focus-visible:ring-[3px]"
                >
                  {showPassword ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              <p id="password-help" className="text-slate text-sm leading-relaxed">
                {capsLock ? (
                  <span className="text-ink-soft font-medium">Caps Lock is on.</span>
                ) : (
                  "Set in the backend's local settings. The project README lists the demo defaults."
                )}
              </p>
            </div>

            <div aria-live="polite">
              {error && (
                <p className="flex items-start gap-2.5 rounded-xl bg-[#fbeceb] px-4 py-3 text-[0.9375rem] leading-snug text-[#8a2c22]">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
                  {error}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={pending || !username.trim() || !password}
              className="bg-primary text-primary-foreground hover:bg-primary/90 focus-visible:ring-primary/35 inline-flex h-12 w-full items-center justify-center gap-2 rounded-full text-base font-medium outline-none focus-visible:ring-4 disabled:cursor-not-allowed disabled:opacity-55"
            >
              {pending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              {pending ? "Signing in…" : selected ? `Sign in as ${selected.title}` : "Sign in"}
            </button>
          </form>
        </section>
      </main>

      <SiteFooter
        links={[
          { href: "/", label: "Home" },
          { href: "/#roles-heading", label: "What each role can do" },
        ]}
      />
    </div>
  );
}

const fieldClass =
  "bg-paper border-seaglass-deep/70 text-ink-soft placeholder:text-slate/70 h-12 w-full rounded-xl border px-4 text-base outline-none transition-[border-color,box-shadow] focus-visible:border-primary focus-visible:ring-primary/25 focus-visible:ring-4 aria-invalid:border-[#c4554a]";
