# Frontend (Angular + Native Federation)

Two Angular apps in one workspace:

- `projects/shell` is the **host** (port 4200): contract list, plus the assistant loaded at runtime.
- `projects/assistant` is the **remote** (port 4201): exposes the assistant chat as `./Assistant`.

```powershell
npm install
npm start               # both apps; or: npm run start:assistant / npm run start:shell
```

See the root README for the full setup and how the federation is configured.
