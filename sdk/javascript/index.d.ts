export type Json = null | boolean | number | string | Json[] | {[key: string]: Json};
export type JsonObject = {[key: string]: Json};
export interface Job {
  id: string;
  bot_id: string;
  kind: string;
  payload: JsonObject;
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'uncertain';
  attempts: number;
  max_attempts: number;
  recovery: 'retry' | 'uncertain';
  run_after: number;
  lease_token?: string | null;
  lease_until: number | null;
  result: JsonObject | null;
  progress: JsonObject | null;
  error: string | null;
  priority: number;
  dedupe_key: string | null;
  created_at: number;
  updated_at: number;
}
export interface EnqueueOptions {
  dedupe_key?: string;
  priority?: number;
  run_after?: number;
  max_attempts?: number;
  recovery?: 'retry' | 'uncertain';
}
export class GramRailError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string);
}
export class GramRail {
  constructor(options: {baseUrl: string; apiKey: string; botId: string; fetch?: typeof globalThis.fetch; timeoutMs?: number});
  enqueue(kind: string, payload: JsonObject, options?: EnqueueOptions): Promise<Job>;
  getJob(id: string): Promise<Job>;
  claim(kinds: string[], leaseSeconds?: number): Promise<Job | null>;
  complete(id: string, leaseToken: string, result?: JsonObject): Promise<Job>;
  fail(id: string, leaseToken: string, error: string, options?: {retry_in?: number; uncertain?: boolean}): Promise<Job>;
  heartbeat(id: string, leaseToken: string, options?: {lease_seconds?: number; progress?: JsonObject}): Promise<Job>;
  sendText(chatId: number, text: string, options?: Pick<EnqueueOptions, 'dedupe_key' | 'priority' | 'run_after'>): Promise<Job>;
  ingest(update: JsonObject): Promise<{accepted: boolean; duplicate: boolean; update_id: number; effects?: number}>;
  request(method: string, path: string, body?: JsonObject): Promise<unknown>;
}
