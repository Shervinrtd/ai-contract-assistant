import { Component } from '@angular/core';

import { ContractList } from './contracts/contract-list';
import { RemoteAssistant } from './remote-assistant/remote-assistant';

@Component({
  selector: 'app-dashboard',
  imports: [ContractList, RemoteAssistant],
  template: `
    <div class="grid">
      <app-contract-list />
      <app-remote-assistant />
    </div>
  `,
  styles: `
    .grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(360px, 1fr); gap: 16px; height: 100%; min-height: 0; }
    @media (max-width: 980px) { .grid { grid-template-columns: 1fr; height: auto; } }
  `,
})
export class Dashboard {}
