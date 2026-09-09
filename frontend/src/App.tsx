import { useEffect, useState } from 'react';

import { fetchLiveness, type LivenessResponse } from '@/api/health';

/** Discriminated union so an unreachable API cannot be confused with a slow one. */
type ConnectionState =
  | { kind: 'checking' }
  | { kind: 'connected'; info: LivenessResponse }
  | { kind: 'unreachable'; message: string };

const OBJECTIVES = [
  { id: 'O1', label: 'Accurate forecasting', target: 'nMAE ≥25% below seasonal-naive' },
  { id: 'O2', label: 'Efficient P2P matching', target: '≥95% of offline optimum' },
  { id: 'O3', label: 'Autonomous trading', target: 'p95 <200ms at 100 agents' },
  { id: 'O4', label: 'Safe energy allocation', target: 'exactly 0 grid violations' },
  { id: 'O5', label: 'Renewable utilisation', target: 'grid export ↓ ≥30%' },
  { id: 'O6', label: 'Economic benefit', target: 'bills ↓10–20%, nobody worse off' },
  { id: 'O7', label: 'Explainability', target: '100% of trades carry a rationale' },
] as const;

function StatusBadge({ state }: { state: ConnectionState }) {
  const styles: Record<ConnectionState['kind'], string> = {
    checking: 'bg-amber-100 text-amber-900 ring-amber-300',
    connected: 'bg-emerald-100 text-emerald-900 ring-emerald-300',
    unreachable: 'bg-rose-100 text-rose-900 ring-rose-300',
  };

  const labels: Record<ConnectionState['kind'], string> = {
    checking: 'Checking API…',
    connected: 'API connected',
    unreachable: 'API unreachable',
  };

  return (
    <span
      role="status"
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ring-1 ${styles[state.kind]}`}
    >
      <span className="h-2 w-2 rounded-full bg-current" aria-hidden="true" />
      {labels[state.kind]}
    </span>
  );
}

export default function App() {
  const [state, setState] = useState<ConnectionState>({ kind: 'checking' });

  useEffect(() => {
    const controller = new AbortController();

    fetchLiveness(controller.signal)
      .then((info) => {
        setState({ kind: 'connected', info });
      })
      .catch((error: unknown) => {
        // An abort is an expected teardown, not a failure worth showing.
        if (controller.signal.aborted) return;
        setState({
          kind: 'unreachable',
          message: error instanceof Error ? error.message : 'Unknown error',
        });
      });

    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-6 py-16">
      <header className="mb-10">
        <p className="mb-2 text-sm font-medium tracking-wide text-slate-500 uppercase">
          M.Tech Industry Accelerate Program
        </p>
        <h1 className="text-3xl font-semibold text-slate-900">
          Agentic P2P Energy Trading in Microgrids
        </h1>
        <p className="mt-3 text-slate-600">
          Households with rooftop solar trade surplus electricity directly with their neighbours,
          priced between the feed-in and retail tariffs so both sides beat the utility — with a grid
          safety layer holding veto power over every trade.
        </p>
      </header>

      <section className="mb-10" aria-labelledby="status-heading">
        <h2 id="status-heading" className="mb-3 text-lg font-semibold text-slate-900">
          Service status
        </h2>
        <StatusBadge state={state} />
        {state.kind === 'connected' && (
          <p className="mt-3 text-sm text-slate-600">
            Connected to <code className="font-mono">{state.info.service}</code> version{' '}
            <code className="font-mono">{state.info.version}</code>.
          </p>
        )}
        {state.kind === 'unreachable' && (
          <p className="mt-3 text-sm text-rose-700">
            {state.message}. Start the stack with{' '}
            <code className="font-mono">docker compose up</code>.
          </p>
        )}
      </section>

      <section aria-labelledby="objectives-heading">
        <h2 id="objectives-heading" className="mb-3 text-lg font-semibold text-slate-900">
          Objectives
        </h2>
        <ul className="divide-y divide-slate-200 rounded-lg ring-1 ring-slate-200">
          {OBJECTIVES.map((objective) => (
            <li key={objective.id} className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-3">
              <span className="font-mono text-sm text-slate-400">{objective.id}</span>
              <span className="font-medium text-slate-900">{objective.label}</span>
              <span className="ml-auto text-sm text-slate-600">{objective.target}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
