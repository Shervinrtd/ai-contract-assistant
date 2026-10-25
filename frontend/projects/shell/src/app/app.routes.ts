import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { FEDERATION, loadAssistant } from './federation';
import { Dashboard } from './dashboard';

export const routes: Routes = [
  // Contract list with the federated assistant in a side panel.
  { path: '', component: Dashboard, title: 'Contracts' },
  // The same remote component mounted as a full page through the router.
  { path: 'assistant', loadComponent: () => loadAssistant(inject(FEDERATION)), title: 'Assistant' },
  { path: '**', redirectTo: '' },
];
