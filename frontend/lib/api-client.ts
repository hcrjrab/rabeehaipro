const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AgentRole =
  | "planner" | "coding" | "research" | "vision" | "browser"
  | "automation" | "business" | "office" | "file" | "memory" | "reviewer";

export interface TaskSummary {
  id: string;
  session_id: string;
  goal: string;
  status: "pending" | "planning" | "awaiting_approval" | "running" | "completed" | "failed" | "cancelled";
  plan: { goal: string; steps: Array<{ description: string; assigned_agent: AgentRole }> } | null;
  events: Array<{ kind: string; payload: Record<string, unknown>; created_at: string }>;
  created_at: string;
  updated_at: string;
}

export interface ToolInfo {
  name: string;
  description: string;
  risk: string;
}

export interface HealthInfo {
  status: string;
  version: string;
  providers: Array<{ provider: string; role: string; circuit_open: boolean }>;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  health: () => request<HealthInfo>("/healthz"),

  readiness: () =>
    request<{ status: string; providers: Array<{ provider: string; circuit_open: boolean }> }>("/readyz"),

  info: () => request<Record<string, unknown>>("/info"),

  agents: {
    list: () => request<Array<{ role: string; name: string }>>("/agents"),
    roles: () => request<string[]>("/agents/roles"),
  },

  tools: {
    list: () => request<ToolInfo[]>("/tools"),
    schemas: () => request<Record<string, unknown>[]>("/tools/schemas"),
  },

  tasks: {
    run: (goal: string, sessionId?: string) =>
      request<TaskSummary>("/tasks", {
        method: "POST",
        body: JSON.stringify({ goal, session_id: sessionId }),
      }),
    list: () => request<TaskSummary[]>("/tasks"),
    get: (id: string) => request<TaskSummary>(`/tasks/${id}`),
  },

  chat: {
    completion: (messages: Array<{ role: string; content: string }>, temperature = 0.2) =>
      request<{ content: string; model: string; provider: string }>("/chat/completion", {
        method: "POST",
        body: JSON.stringify({ messages, temperature }),
      }),
  },

  business: {
    // Customers
    listCustomers: () => request<unknown[]>("/business/customers"),
    createCustomer: (data: unknown) =>
      request<unknown>("/business/customers", { method: "POST", body: JSON.stringify(data) }),
    getCustomer: (id: string) => request<unknown>(`/business/customers/${id}`),
    updateCustomer: (id: string, data: unknown) =>
      request<unknown>(`/business/customers/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    deleteCustomer: (id: string) =>
      request<void>(`/business/customers/${id}`, { method: "DELETE" }),

    // Vendors
    listVendors: () => request<unknown[]>("/business/vendors"),
    createVendor: (data: unknown) =>
      request<unknown>("/business/vendors", { method: "POST", body: JSON.stringify(data) }),
    getVendor: (id: string) => request<unknown>(`/business/vendors/${id}`),

    // Quotations
    listQuotations: () => request<unknown[]>("/business/quotations"),
    createQuotation: (data: unknown) =>
      request<unknown>("/business/quotations", { method: "POST", body: JSON.stringify(data) }),
    getQuotation: (id: string) => request<unknown>(`/business/quotations/${id}`),

    // Invoices
    listInvoices: () => request<unknown[]>("/business/invoices"),
    createInvoice: (data: unknown) =>
      request<unknown>("/business/invoices", { method: "POST", body: JSON.stringify(data) }),
    getInvoice: (id: string) => request<unknown>(`/business/invoices/${id}`),

    // Purchase Orders
    listPurchaseOrders: () => request<unknown[]>("/business/purchase-orders"),
    createPurchaseOrder: (data: unknown) =>
      request<unknown>("/business/purchase-orders", { method: "POST", body: JSON.stringify(data) }),
    getPurchaseOrder: (id: string) => request<unknown>(`/business/purchase-orders/${id}`),

    // BOQ
    listBOQs: () => request<unknown[]>("/business/boq"),
    createBOQ: (data: unknown) =>
      request<unknown>("/business/boq", { method: "POST", body: JSON.stringify(data) }),
    getBOQ: (id: string) => request<unknown>(`/business/boq/${id}`),

    // Inventory
    listInventory: () => request<unknown[]>("/business/inventory"),
    createInventoryItem: (data: unknown) =>
      request<unknown>("/business/inventory", { method: "POST", body: JSON.stringify(data) }),
    getInventoryItem: (id: string) => request<unknown>(`/business/inventory/${id}`),
    updateInventoryItem: (id: string, data: unknown) =>
      request<unknown>(`/business/inventory/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    deleteInventoryItem: (id: string) =>
      request<void>(`/business/inventory/${id}`, { method: "DELETE" }),

    // Estimations
    listEstimations: () => request<unknown[]>("/business/estimations"),
    createEstimation: (data: unknown) =>
      request<unknown>("/business/estimations", { method: "POST", body: JSON.stringify(data) }),
    getEstimation: (id: string) => request<unknown>(`/business/estimations/${id}`),

    // Reports
    summary: () => request<Record<string, unknown>>("/business/reports/summary"),
  },
};
