import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
  contentClassName?: string;
  children: ReactNode;
}

export function Card({
  title,
  subtitle,
  action,
  className,
  contentClassName,
  children,
}: CardProps) {
  const hasHeader = title !== undefined || action !== undefined;

  return (
    <section
      className={cn(
        'flex flex-col overflow-hidden rounded-xl border border-stone-200 bg-white',
        className,
      )}
    >
      {hasHeader && (
        <header className="flex items-start justify-between gap-4 border-b border-stone-100 px-5 py-3.5">
          <div className="min-w-0">
            {title !== undefined && (
              <h2 className="text-sm font-semibold text-stone-900">{title}</h2>
            )}
            {subtitle !== undefined && <p className="mt-0.5 text-xs text-stone-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={cn('flex-1 p-5', contentClassName)}>{children}</div>
    </section>
  );
}
