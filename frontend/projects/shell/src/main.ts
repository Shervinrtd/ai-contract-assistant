import { initFederation } from '@angular-architects/native-federation';

// 1. Read the manifest (remote name -> URL of its remoteEntry.json) at runtime, so remote
//    locations can change per environment without rebuilding the host.
// 2. Bootstrap Angular, handing over the federation instance used to load remotes.
//    If a remote is unreachable the host still starts; the panel shows a fallback.
initFederation('federation.manifest.json', {
  hostRemoteEntry: { url: './remoteEntry.json' },
})
  .catch((err) => {
    console.error('Native Federation could not initialise; remotes will be unavailable.', err);
    return null;
  })
  .then((federation) => import('./bootstrap').then((m) => m.bootstrap(federation)))
  .catch((err) => console.error(err));
