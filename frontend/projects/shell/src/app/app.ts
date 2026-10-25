import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <header class="top">
      <div class="brand">
        <strong>AI Contract Assistant</strong>
        <span>host app · port 4200</span>
      </div>
      <nav>
        <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Contracts</a>
        <a routerLink="/assistant" routerLinkActive="active">Assistant (full page)</a>
      </nav>
    </header>
    <main class="content"><router-outlet /></main>
  `,
  styles: `
    :host { display: flex; flex-direction: column; height: 100vh; }
    .top { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; background: #1d2330; color: #fff; }
    .brand { display: flex; align-items: baseline; gap: 10px; }
    .brand span { font-size: 12px; color: #a9b2c3; }
    nav { display: flex; gap: 4px; }
    nav a { color: #cfd6e4; text-decoration: none; font-size: 13px; padding: 6px 10px; border-radius: 6px; }
    nav a.active, nav a:hover { background: #2f3a52; color: #fff; }
    .content { flex: 1; min-height: 0; padding: 16px 20px; box-sizing: border-box; }
  `,
})
export class App {}
