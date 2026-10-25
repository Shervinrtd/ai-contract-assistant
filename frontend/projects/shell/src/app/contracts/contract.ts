/** A contract as returned by GET /contracts (backend/app/schemas.py). */
export interface Contract {
  id: string;
  title: string;
  counterparty: string;
  contract_type: string;
  effective_date: string;
  expiration_date: string;
  status: string;
  days_until_expiration: number;
  pdf_url: string;
}
