import {
  withNativeFederation,
  fromPackageJson,
} from '@angular-architects/native-federation/config';

// The host: loads remotes listed in public/federation.manifest.json at runtime.
export default withNativeFederation({
  name: 'shell',


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
