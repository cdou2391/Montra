/**
 * Thin API client.
 *
 * Sessions are HTTP-only cookies, so every request forwards credentials and no
 * token is ever read or stored by JavaScript (API spec section 5).
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type ApiError = {
  code: string;
  message: string;
  details?: { field: string; message: string }[] | null;
  request_id?: string;
};

export class MontraApiError extends Error {
  code: string;
  details?: { field: string; message: string }[] | null;
  status: number;

  constructor(status: number, error: ApiError) {
    super(error.message);
    this.status = status;
    this.code = error.code;
    this.details = error.details;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new MontraApiError(
      response.status,
      body?.error ?? { code: "UNKNOWN", message: "Something went wrong." },
    );
  }

  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
      headers,
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ------------------------------------------------------------------ resources

export type Money = { amount: string; currency: string };

export type CreditCardFields = {
  credit_limit: string | null;
  statement_balance: string | null;
  statement_closing_day: number | null;
  payment_due_day: number | null;
  minimum_payment: string | null;
  interest_rate: string | null;
  expiry_month: number | null;
  expiry_year: number | null;
};

export type Account = {
  id: string;
  name: string;
  account_type: string;
  account_nature: "ASSET" | "LIABILITY";
  currency: string;
  balance: string;
  opening_balance: string;
  masked_identifier: string | null;
  visibility: string;
  ownership_type: string;
  status: string;
  can_edit: boolean;
  can_transact: boolean;
  credit_card: CreditCardFields | null;
};

export type CardSummary = {
  account_id: string;
  currency: string;
  outstanding_balance: string;
  available_credit: string | null;
  credit_limit: string | null;
  utilization_percentage: string | null;
  utilization_band: "NORMAL" | "NEUTRAL" | "WARNING" | "HIGH" | null;
  statement_balance: string | null;
  minimum_payment: string | null;
  payment_due_date: string | null;
  statement_closing_day: number | null;
  interest_rate: string | null;
};

export type ReconciliationPreview = {
  current_balance: string;
  actual_balance: string;
  difference: string;
  direction: "INCREASE" | "DECREASE" | null;
  currency: string;
};

export type Transaction = {
  id: string;
  account: { id: string; name: string } | null;
  transaction_type: "INCOME" | "EXPENSE" | "TRANSFER" | "ADJUSTMENT";
  amount: string;
  currency: string;
  direction: "INCREASE" | "DECREASE";
  occurred_at: string;
  status: string;
  description: string | null;
  merchant: string | null;
  category: { id: string; name: string } | null;
  transfer_id: string | null;
};

export type Category = {
  id: string;
  name: string;
  category_type: "INCOME" | "EXPENSE";
};

export type CurrentUser = {
  id: string;
  email: string;
  display_name: string | null;
  base_currency: string;
  timezone: string;
  active_family: { id: string; name: string; role: string } | null;
};

type Envelope<T> = { data: T };
type Collection<T> = { data: T[]; pagination: { limit: number; next_cursor: string | null } };

export const montra = {
  me: () => api.get<Envelope<CurrentUser>>("/auth/me").then((r) => r.data),
  login: (email: string, password: string) =>
    api.post<Envelope<{ user: CurrentUser }>>("/auth/login", { email, password }),
  register: (payload: {
    email: string;
    password: string;
    display_name?: string;
    base_currency: string;
    timezone: string;
  }) => api.post<Envelope<CurrentUser>>("/auth/register", payload),
  logout: () => api.post<void>("/auth/logout"),

  accounts: () => api.get<Collection<Account>>("/accounts").then((r) => r.data),
  account: (id: string) => api.get<Envelope<Account>>(`/accounts/${id}`).then((r) => r.data),
  createAccount: (payload: Record<string, unknown>) =>
    api.post<Envelope<Account>>("/accounts", payload).then((r) => r.data),
  archiveAccount: (id: string) => api.post<void>(`/accounts/${id}/archive`),

  transactions: (query = "") =>
    api.get<Collection<Transaction>>(`/transactions${query}`),
  createTransaction: (payload: Record<string, unknown>) =>
    api.post<Envelope<Transaction>>("/transactions", payload).then((r) => r.data),
  deleteTransaction: (id: string) => api.delete<void>(`/transactions/${id}`),

  cardSummary: (id: string) =>
    api.get<Envelope<CardSummary>>(`/credit-cards/${id}/summary`).then((r) => r.data),
  payCard: (id: string, payload: Record<string, unknown>, idempotencyKey: string) =>
    api.post<Envelope<unknown>>(`/credit-cards/${id}/payments`, payload, {
      "Idempotency-Key": idempotencyKey,
    }),
  topUpPrepaid: (id: string, payload: Record<string, unknown>, idempotencyKey: string) =>
    api.post<Envelope<unknown>>(`/prepaid-cards/${id}/top-ups`, payload, {
      "Idempotency-Key": idempotencyKey,
    }),

  reconciliationPreview: (id: string, actualBalance: string) =>
    api
      .get<Envelope<ReconciliationPreview>>(
        `/accounts/${id}/reconciliation-preview?actual_balance=${encodeURIComponent(
          actualBalance,
        )}`,
      )
      .then((r) => r.data),
  reconcile: (id: string, payload: Record<string, unknown>) =>
    api.post<Envelope<unknown>>(`/accounts/${id}/balance-adjustments`, payload),

  createTransfer: (payload: Record<string, unknown>, idempotencyKey: string) =>
    api.post<Envelope<unknown>>("/transfers", payload, {
      "Idempotency-Key": idempotencyKey,
    }),

  categories: (type?: "INCOME" | "EXPENSE") =>
    api
      .get<Collection<Category>>(`/categories${type ? `?type=${type}` : ""}`)
      .then((r) => r.data),
};
