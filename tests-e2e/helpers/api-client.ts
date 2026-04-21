/**
 * API Client — thin wrapper over fetch for backend calls.
 *
 * Use when tests need to assert/verify backend state directly
 * (bypassing UI) or to seed via REST endpoints instead of DB.
 *
 * Auth: pass a JWT token; fixtures get one via login helper.
 */
import * as dotenv from 'dotenv';
import * as path from 'path';

const envName = process.env.TEST_ENV || 'prod';
dotenv.config({ path: path.resolve(__dirname, `../.env.${envName}`) });

const BASE_URL = process.env.BASE_URL || 'https://app.xcleaners.app';
const SLUG = process.env.BUSINESS_SLUG || 'e2e-testing-co';

export interface ApiClientOptions {
  token?: string;
  baseUrl?: string;
  slug?: string;
}

export class ApiClient {
  private baseUrl: string;
  private slug: string;
  private token?: string;

  constructor(opts: ApiClientOptions = {}) {
    this.baseUrl = opts.baseUrl ?? BASE_URL;
    this.slug = opts.slug ?? SLUG;
    this.token = opts.token;
  }

  setToken(token: string) {
    this.token = token;
  }

  async login(email: string, password: string): Promise<{ access_token: string; refresh_token?: string }> {
    // Real backend prefix is /auth (not /api/v1/auth)
    const res = await fetch(`${this.baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(`Login failed ${res.status}: ${t}`);
    }
    const body = await res.json() as { access_token: string; refresh_token?: string };
    this.token = body.access_token;
    return body;
  }

  async get<T = unknown>(path: string): Promise<T> {
    return this.request<T>('GET', path);
  }

  async post<T = unknown>(path: string, body: unknown): Promise<T> {
    return this.request<T>('POST', path, body);
  }

  async put<T = unknown>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PUT', path, body);
  }

  async delete<T = unknown>(path: string): Promise<T> {
    return this.request<T>('DELETE', path);
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    // Auto-prefix with /api/v1/clean/{slug} for module endpoints that omit prefix.
    const url = path.startsWith('http')
      ? path
      : path.startsWith('/api/')
        ? `${this.baseUrl}${path}`
        : `${this.baseUrl}/api/v1/clean/${this.slug}${path}`;

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers['Authorization'] = `Bearer ${this.token}`;

    const res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // Return structured error object so tests can assert against `reason`, `status_code`, etc.
    if (!res.ok) {
      let parsed: unknown = null;
      try { parsed = await res.json(); } catch { /* ignore */ }
      const err: any = new Error(`${method} ${path} failed ${res.status}`);
      err.status = res.status;
      err.body = parsed;
      throw err;
    }

    if (res.status === 204) return {} as T;
    return res.json() as Promise<T>;
  }
}
