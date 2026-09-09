import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind classes, letting later ones win over earlier conflicts.
 *
 * Without this, `cn('p-4', props.className)` silently keeps `p-4` when the
 * caller passes `p-6`, because both land in the class list and CSS order — not
 * argument order — decides.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
