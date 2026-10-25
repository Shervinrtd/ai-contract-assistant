import { bootstrapApplication } from '@angular/platform-browser';
import type { NativeFederationResult } from '@angular-architects/native-federation';

import { App } from './app/app';
import { appConfig } from './app/app.config';
import { FEDERATION } from './app/federation';

export function bootstrap(federation: NativeFederationResult | null) {
  return bootstrapApplication(App, {
    ...appConfig,
    providers: [...appConfig.providers, { provide: FEDERATION, useValue: federation }],
  });
}
