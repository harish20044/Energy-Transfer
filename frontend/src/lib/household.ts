/** Household ids are "h1".."h10" throughout the backend; this is the one
 *  place that turns one into the label a person reads, so renaming the
 *  display convention later is a one-line change. */
export function householdLabel(householdId: string): string {
  const suffix = householdId.startsWith('h') ? householdId.slice(1) : householdId;
  return `House ${suffix}`;
}
