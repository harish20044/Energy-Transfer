/** Client for this household's own agent: what it has learned, and a
 *  conversation with it (an LLM that reads the agent's real records). */

import { apiFetch } from '@/api/client';

export interface AgentMemory {
  household_id: string;
  sell_margin: number;
  buy_margin: number;
  price_by_hour: (number | null)[];
  trades: number;
  units_sold: number;
  units_bought: number;
  savings_inr: number;
  graph_nodes: string[];
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatReply {
  reply: string;
  provider: string;
  tools_used: string[];
}

export function fetchOwnAgent(accessToken: string, signal?: AbortSignal): Promise<AgentMemory> {
  return apiFetch<AgentMemory>('/agents/me', accessToken, { signal });
}

export function chatWithAgent(
  accessToken: string,
  message: string,
  history: ChatTurn[],
): Promise<ChatReply> {
  return apiFetch<ChatReply>('/agents/me/chat', accessToken, {
    method: 'POST',
    body: { message, history },
  });
}
