import { API_BASE_URL } from '../config';

// Shapes returned by the backend (see backend/app/schemas.py).

export interface Citation {
  n: number;
  source_id: string;
  kind: 'clause' | 'contract';
  contract_id: string;
  contract_title: string;
  label: string;
  pdf_url: string;
  clause_number: string | null;
  heading: string | null;
  page_start: number | null;
  page_end: number | null;
  quote: string | null;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  summary: string;
  duration_ms: number;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  tool_calls: ToolCall[];
  grounded: boolean;
  mode: 'openai' | 'mock';
  model: string;
  rounds: number;
  warnings: string[];
}

export interface Health {
  status: string;
  assistant_mode: 'openai' | 'mock';
  model: string;
}

export interface HistoryTurn {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * Uses fetch rather than HttpClient on purpose: the component then needs no providers
 * from whichever host loads it, so it can be dropped into any federated shell.
 */
export class AssistantApi {
  constructor(private readonly baseUrl: string = API_BASE_URL) {}

  pdfUrl(path: string): string {
    return this.baseUrl + path;
  }

  async health(): Promise<Health> {
    const response = await fetch(`${this.baseUrl}/health`);
    if (!response.ok) throw new Error(`Health check failed (${response.status})`);
    return response.json();
  }

  async ask(message: string, history: HistoryTurn[]): Promise<ChatResponse> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history }),
      });
    } catch {
      throw new Error(`Cannot reach the API at ${this.baseUrl}. Is the backend running?`);
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail ?? `The assistant returned an error (${response.status}).`);
    }
    return response.json();
  }
}
