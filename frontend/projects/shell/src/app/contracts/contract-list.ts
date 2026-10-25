import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';

import { API_BASE_URL } from '../config';
import { Contract } from './contract';

const SOON_DAYS = 30;

@Component({
  selector: 'app-contract-list',
  imports: [DatePipe],
  templateUrl: './contract-list.html',
  styleUrl: './contract-list.css',
})
export class ContractList implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly contracts = signal<Contract[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly filter = signal('');
  protected readonly apiBase = API_BASE_URL;

  protected readonly visible = computed(() => {
    const q = this.filter().trim().toLowerCase();
    if (!q) return this.contracts();
    return this.contracts().filter((c) =>
      [c.id, c.title, c.counterparty, c.contract_type, c.status].some((v) => v.toLowerCase().includes(q)),
    );
  });

  ngOnInit(): void {
    this.http.get<Contract[]>(`${API_BASE_URL}/contracts`).subscribe({
      next: (contracts) => {
        this.contracts.set(contracts);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(`Cannot load contracts from ${API_BASE_URL}. Is the backend running?`);
        this.loading.set(false);
      },
    });
  }

  protected statusOf(c: Contract): 'expired' | 'soon' | 'active' {
    if (c.status === 'Expired') return 'expired';
    return c.days_until_expiration <= SOON_DAYS ? 'soon' : 'active';
  }

  protected relative(days: number): string {
    if (days === 0) return 'today';
    if (days < 0) return `${-days} day${days === -1 ? '' : 's'} ago`;
    return `in ${days} day${days === 1 ? '' : 's'}`;
  }
}
