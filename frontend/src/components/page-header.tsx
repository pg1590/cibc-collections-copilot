export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    // page-drift: the header lags and softens as the page scrolls (globals.css).
    <header className="page-drift mb-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-2.5">
        <span aria-hidden className="mb-4 block h-1 w-12 rounded-full bg-gradient-to-r from-[#0e6a63] to-[#155a7e]" />
        <h1 className="text-[2rem] leading-tight font-normal tracking-[-0.02em] sm:text-[2.375rem]">{title}</h1>
        {description && <p className="text-muted-foreground max-w-2xl text-[1.0625rem] leading-relaxed">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
