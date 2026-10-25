import { Component } from '@angular/core';

import { AssistantComponent } from './assistant/assistant.component';

/** Standalone page of the remote (http://localhost:4201): the same component the host loads. */
@Component({
  selector: 'app-root',
  imports: [AssistantComponent],
  template: `
    <main class="page">
      <p class="hint">Remote app <code>assistant</code> running on its own. The host loads this same component at runtime.</p>
      <div class="frame"><ca-assistant /></div>
    </main>
  `,
  styles: `
    .page { max-width: 760px; margin: 0 auto; padding: 24px 16px; height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; gap: 12px; }
    .hint { margin: 0; font: 13px system-ui, sans-serif; color: #5d6675; }
    .frame { flex: 1; min-height: 0; border: 1px solid #dfe3ea; border-radius: 12px; overflow: hidden; }
  `,
})
export class App {}
