import { Component, OnInit, Type, inject, signal } from '@angular/core';
import { NgComponentOutlet } from '@angular/common';

import { ASSISTANT_REMOTE, FEDERATION, loadAssistant } from '../federation';

/**
 * Side panel that loads the assistant component from the `assistant` remote at runtime
 * (Native Federation). The host has no build-time dependency on the remote's code.
 */
@Component({
  selector: 'app-remote-assistant',
  imports: [NgComponentOutlet],
  template: `
    <section class="panel">
      <p class="origin">
        Loaded at runtime from remote <code>{{ remote.remoteName }}</code> ({{ remote.exposedModule }})
      </p>
      @if (component(); as c) {
        <div class="slot"><ng-container *ngComponentOutlet="c" /></div>
      } @else if (error()) {
        <div class="fallback">
          <strong>The assistant remote is not available.</strong>
          <p>Start it with <code>npm run start:assistant</code> (port 4201) and reload the page.</p>
          <p class="detail">{{ error() }}</p>
        </div>
      } @else {
        <p class="loading">Loading the assistant remote…</p>
      }
    </section>
  `,
  styles: `
    :host { display: block; min-height: 0; }
    .panel { height: 100%; min-height: 480px; display: flex; flex-direction: column; border: 1px solid #dfe3ea; border-radius: 12px; overflow: hidden; background: #fff; }
    .origin { margin: 0; padding: 6px 12px; font: 11px system-ui, sans-serif; color: #5d6675; background: #f1f3f8; border-bottom: 1px solid #dfe3ea; }
    .origin code { font-size: 11px; }
    .slot { flex: 1; min-height: 0; }
    .fallback { margin: 16px; padding: 14px; border: 1px dashed #f3d39b; background: #fff8ea; border-radius: 10px; font: 14px system-ui, sans-serif; color: #5a3a00; }
    .fallback p { margin: 6px 0 0; }
    .detail { font-size: 12px; color: #8a6a3a; }
    .loading { padding: 16px; font: 14px system-ui, sans-serif; color: #5d6675; }
  `,
})
export class RemoteAssistant implements OnInit {
  private readonly federation = inject(FEDERATION);
  protected readonly remote = ASSISTANT_REMOTE;
  protected readonly component = signal<Type<unknown> | null>(null);
  protected readonly error = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    try {
      this.component.set(await loadAssistant(this.federation));
    } catch (err) {
      this.error.set(err instanceof Error ? err.message : String(err));
    }
  }
}
