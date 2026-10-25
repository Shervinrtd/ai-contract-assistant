import {
  withNativeFederation,
  fromPackageJson,
} from '@angular-architects/native-federation/config';

// The remote: a separately built and served app that exposes the assistant chat
// as a standalone Angular component any host can load at runtime.
export default withNativeFederation({
  name: 'assistant',

  exposes: {
    './Assistant': './projects/assistant/src/app/assistant/assistant.component.ts',
  },

  // Angular and RxJS are shared as singletons, so host and remote use one copy.
  shared: fromPackageJson({
    singleton: true,
    strictVersion: true,
    requiredVersion: 'auto',
    build: 'package',
  })
    .patch(['@angular/*'], { includeSecondaries: { keepAll: true } })
    .get(),

  // Not shared: unused RxJS entry points, and the animation entry points of
  // @angular/platform-browser (they need @angular/animations, which this app does not use).
  skip: [
    'rxjs/ajax',
    'rxjs/fetch',
    'rxjs/testing',
    'rxjs/webSocket',
    '@angular/platform-browser/animations',
    '@angular/platform-browser/animations/async',
  ],

  features: {
    denseChunking: true,
    denseExternals: true,
    strictImports: false,
  },
});
