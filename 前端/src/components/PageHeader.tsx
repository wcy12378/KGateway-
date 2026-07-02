import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description: string;
  actions?: ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="mb-5 flex flex-col gap-3 border-b border-crt-border pb-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="page-heading">{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
