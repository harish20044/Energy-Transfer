import { Bot, Loader2, Send, User } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { chatWithAgent, type ChatTurn } from '@/api/agents';
import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/useAuth';
import { cn } from '@/lib/cn';

const SUGGESTIONS = [
  'What is your plan for tonight?',
  'Why did you buy from neighbours instead of the EB?',
  'How much are we saving this session?',
  'Keep 60% charge in the battery from now on.',
];

/** Talk to the household's agent. The answers come from an LLM that can
 *  only read the agent's real records — it never trades. */
export function AgentChat() {
  const { accessToken } = useAuth();
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [meta, setMeta] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: 'nearest' });
  }, [history, sending]);

  async function send(message: string) {
    const text = message.trim();
    if (accessToken === null || text === '' || sending) return;
    const before = history;
    setHistory([...before, { role: 'user', content: text }]);
    setDraft('');
    setSending(true);
    try {
      const reply = await chatWithAgent(accessToken, text, before.slice(-10));
      setHistory((h) => [...h, { role: 'assistant', content: reply.reply }]);
      setMeta(
        `${reply.provider === 'groq' ? 'Groq · gpt-oss-120b' : reply.provider}` +
          (reply.tools_used.length > 0
            ? ` · checked ${[...new Set(reply.tools_used)].join(', ')}`
            : ''),
      );
    } catch (err) {
      const reason = err instanceof ApiError ? err.message : 'the agent could not answer';
      setHistory((h) => [...h, { role: 'assistant', content: `Sorry — ${reason}.` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-[440px] flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">
        {history.length === 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-stone-500">
              Ask your agent why it traded the way it did, or tell it how much charge to keep.
            </p>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void send(s)}
                className="rounded-lg border border-stone-200 px-3 py-2 text-left text-sm text-stone-700 transition-colors hover:bg-stone-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {history.map((turn, i) => (
          <div key={i} className={cn('flex gap-2', turn.role === 'user' && 'flex-row-reverse')}>
            <span
              className={cn(
                'flex size-7 shrink-0 items-center justify-center rounded-full',
                turn.role === 'user' ? 'bg-stone-200 text-stone-600' : 'bg-peer-100 text-peer-700',
              )}
            >
              {turn.role === 'user' ? (
                <User className="size-4" aria-hidden="true" />
              ) : (
                <Bot className="size-4" aria-hidden="true" />
              )}
            </span>
            <p
              className={cn(
                'max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap',
                turn.role === 'user' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-800',
              )}
            >
              {turn.content}
            </p>
          </div>
        ))}
        {sending && (
          <p className="flex items-center gap-2 text-xs text-stone-500">
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> Your agent is checking
            its records…
          </p>
        )}
        <div ref={bottom} />
      </div>
      {meta !== null && <p className="pt-2 text-[11px] text-stone-400">{meta}</p>}
      <form
        className="mt-2 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <input
          aria-label="Message your agent"
          value={draft}
          maxLength={1000}
          onChange={(e) => {
            setDraft(e.target.value);
          }}
          placeholder="Ask your agent…"
          className="flex-1 rounded-lg border border-stone-200 px-3 py-2 text-sm outline-none focus:border-peer-400"
        />
        <button
          type="submit"
          aria-label="Send"
          disabled={sending || draft.trim() === ''}
          className="flex size-9 items-center justify-center rounded-lg bg-peer-600 text-white transition-colors hover:bg-peer-700 disabled:opacity-50"
        >
          <Send className="size-4" aria-hidden="true" />
        </button>
      </form>
    </div>
  );
}
