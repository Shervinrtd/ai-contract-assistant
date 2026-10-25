import { Component, ElementRef, OnInit, computed, signal, viewChild } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { AssistantApi, ChatResponse, Citation, Health, HistoryTurn } from './assistant-api';
import { Block, formatAnswer } from './format-answer';

interface Turn {
  question: string;
  response?: ChatResponse;
  blocks?: Block[];
  error?: string;
}

/**
 * The contract assistant chat. Exposed by this remote as './Assistant' and loaded by the
 * host at runtime; it also runs on its own in the remote's standalone app.
 */
@Component({
  selector: 'ca-assistant',
  imports: [FormsModule, NgTemplateOutlet],
  templateUrl: './assistant.component.html',
  styleUrl: './assistant.component.css',
})
export class AssistantComponent implements OnInit {
  protected readonly api = new AssistantApi();
  protected readonly examples = [
    'Which contracts expire in the next 30 days?',
    'Which contracts renew automatically?',
    'What are the termination conditions in the supply agreement?',
    'What are the termination conditions in the NDA?',
    'Of the contracts expiring in the next 90 days, which renew automatically?',
  ];

  protected readonly turns = signal<Turn[]>([]);
  protected readonly draft = signal('');
  protected readonly pending = signal(false);
  protected readonly health = signal<Health | null>(null);
  protected readonly healthError = signal(false);
  protected readonly canSend = computed(() => this.draft().trim().length > 0 && !this.pending());

  private readonly log = viewChild<ElementRef<HTMLElement>>('log');

  async ngOnInit(): Promise<void> {
    try {
      this.health.set(await this.api.health());
    } catch {
      this.healthError.set(true);
    }
  }

  protected async ask(question = this.draft()): Promise<void> {
    question = question.trim();
    if (!question || this.pending()) return;
    const history = this.history();
    this.draft.set('');
    this.pending.set(true);
    this.turns.update((t) => [...t, { question }]);
    this.scrollToEnd();
    try {
      const response = await this.api.ask(question, history);
      this.updateLast({ question, response, blocks: formatAnswer(response.answer) });
    } catch (err) {
      this.updateLast({ question, error: err instanceof Error ? err.message : String(err) });
    } finally {
      this.pending.set(false);
      this.scrollToEnd();
    }
  }

  protected onEnter(event: Event): void {
    const key = event as KeyboardEvent;
    if (!key.shiftKey) {
      key.preventDefault();
      void this.ask();
    }
  }

  protected citation(turn: Turn, n: number): Citation | undefined {
    return turn.response?.citations.find((c) => c.n === n);
  }

  protected args(args: Record<string, unknown>): string {
    return Object.entries(args)
      .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
      .join(', ');
  }

  protected clear(): void {
    this.turns.set([]);
  }

  /** Earlier questions and answers, so follow-up questions have context. */
  private history(): HistoryTurn[] {
    return this.turns()
      .filter((t) => t.response)
      .slice(-3)
      .flatMap((t) => [
        { role: 'user' as const, content: t.question },
        { role: 'assistant' as const, content: t.response!.answer },
      ]);
  }

  private updateLast(turn: Turn): void {
    this.turns.update((t) => [...t.slice(0, -1), turn]);
  }

  private scrollToEnd(): void {
    setTimeout(() => {
      const el = this.log()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
}
