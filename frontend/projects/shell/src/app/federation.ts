import { InjectionToken, Type } from '@angular/core';
import type { NativeFederationResult } from '@angular-architects/native-federation';

/** The federation instance returned by initFederation() in main.ts (null if it failed). */
export const FEDERATION = new InjectionToken<NativeFederationResult | null>('FEDERATION');

/** Remote name (as in federation.manifest.json) and the module it exposes. */
export const ASSISTANT_REMOTE = { remoteName: 'assistant', exposedModule: './Assistant' } as const;

/** Loads the assistant component from the remote at runtime. */
export async function loadAssistant(federation: NativeFederationResult | null): Promise<Type<unknown>> {
  if (!federation) throw new Error('Native Federation is not initialised.');
  const module = await federation.loadRemoteModule<{ AssistantComponent: Type<unknown> }>(
    ASSISTANT_REMOTE.remoteName,
    ASSISTANT_REMOTE.exposedModule,
  );
  return module.AssistantComponent;
}
