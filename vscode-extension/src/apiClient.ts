/**
 * VSRS API Client
 * Communicates with the VSRS Python backend via REST API
 */

import * as http from 'http';
import * as https from 'https';
import { URL } from 'url';
import {
    TaskInfo,
    TaskResult,
    VerificationReport,
    BenchmarkResult,
    ServerConfig,
    VSRSClient,
} from './types';

export class VSRSApiClient implements VSRSClient {
    private config: ServerConfig;
    private _connected: boolean = false;

    constructor(config: ServerConfig) {
        this.config = config;
    }

    async connect(): Promise<boolean> {
        try {
            await this.request('GET', '/health');
            this._connected = true;
            return true;
        } catch {
            this._connected = false;
            return false;
        }
    }

    disconnect(): void {
        this._connected = false;
    }

    isConnected(): boolean {
        return this._connected;
    }

    async createTask(instruction: string, type: string): Promise<TaskInfo> {
        return this.request('POST', '/api/tasks', { instruction, type });
    }

    async getTask(taskId: string): Promise<TaskInfo> {
        return this.request('GET', `/api/tasks/${taskId}`);
    }

    async listTasks(): Promise<TaskInfo[]> {
        return this.request('GET', '/api/tasks');
    }

    async runVerification(taskId: string): Promise<VerificationReport> {
        return this.request('POST', `/api/tasks/${taskId}/verify`);
    }

    async runRepair(taskId: string, maxAttempts?: number): Promise<TaskResult> {
        const body = maxAttempts !== undefined ? { max_attempts: maxAttempts } : undefined;
        return this.request('POST', `/api/tasks/${taskId}/repair`, body);
    }

    async runBenchmark(): Promise<BenchmarkResult> {
        return this.request('POST', '/api/benchmark/run');
    }

    async cancelTask(taskId: string): Promise<boolean> {
        const result = await this.request('POST', `/api/tasks/${taskId}/cancel`);
        return result.cancelled === true;
    }

    private request(method: string, path: string, body?: any): Promise<any> {
        return new Promise((resolve, reject) => {
            const url = new URL(path, this.config.serverUrl);
            const isHttps = url.protocol === 'https:';
            const lib = isHttps ? https : http;

            const data = body ? JSON.stringify(body) : undefined;

            const options: http.RequestOptions = {
                method,
                hostname: url.hostname,
                port: url.port || (isHttps ? 443 : 80),
                path: url.pathname + url.search,
                headers: {
                    'Content-Type': 'application/json',
                    ...(data ? { 'Content-Length': Buffer.byteLength(data) } : {}),
                    ...(this.config.apiKey ? { 'Authorization': `Bearer ${this.config.apiKey}` } : {}),
                },
                timeout: this.config.timeout * 1000,
            };

            const req = lib.request(options, (res) => {
                let responseData = '';
                res.on('data', (chunk) => { responseData += chunk; });
                res.on('end', () => {
                    if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                        try {
                            resolve(responseData ? JSON.parse(responseData) : {});
                        } catch {
                            reject(new Error(`Invalid JSON response: ${responseData}`));
                        }
                    } else {
                        reject(new Error(`HTTP ${res.statusCode}: ${responseData}`));
                    }
                });
            });

            req.on('error', (err) => reject(err));
            req.on('timeout', () => {
                req.destroy();
                reject(new Error('Request timeout'));
            });

            if (data) {
                req.write(data);
            }
            req.end();
        });
    }
}
