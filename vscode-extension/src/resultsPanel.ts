/**
 * Webview panel for displaying VSRS results
 */

import * as vscode from 'vscode';
import { VerificationReport, CheckResult, BenchmarkResult } from './types';

export class ResultsPanel {
    public static currentPanel: ResultsPanel | undefined;
    private static readonly viewType = 'vsrsResultsPanel';
    private panel: vscode.WebviewPanel;
    private disposables: vscode.Disposable[] = [];

    public static createOrShow(extensionUri: vscode.Uri): ResultsPanel {
        if (ResultsPanel.currentPanel) {
            ResultsPanel.currentPanel.panel.reveal(vscode.ViewColumn.Two);
            return ResultsPanel.currentPanel;
        }

        const panel = vscode.window.createWebviewPanel(
            ResultsPanel.viewType,
            'VSRS Results',
            vscode.ViewColumn.Two,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            }
        );

        ResultsPanel.currentPanel = new ResultsPanel(panel, extensionUri);
        return ResultsPanel.currentPanel;
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
        this.panel = panel;
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
        this.panel.webview.html = this.getHtml();
    }

    public showVerificationReport(report: VerificationReport): void {
        const checksHtml = report.checks.map(c => this.renderCheck(c)).join('');
        const statusClass = report.required_passed ? 'pass' : 'fail';
        const statusText = report.required_passed ? 'PASSED' : 'FAILED';

        this.panel.webview.html = this.getHtml(`
            <h2>Verification Report</h2>
            <div class="status ${statusClass}">
                <span class="status-badge">${statusText}</span>
                <span>Final Status: ${report.final_status}</span>
            </div>
            ${report.blockers.length > 0 ? `
                <div class="blockers">
                    <h3>Blockers</h3>
                    <ul>${report.blockers.map(b => `<li>${b}</li>`).join('')}</ul>
                </div>
            ` : ''}
            <h3>Checks (${report.checks.length})</h3>
            <div class="checks">${checksHtml}</div>
        `);
    }

    public showBenchmarkResult(result: BenchmarkResult): void {
        const rate = (v: number) => `${(v * 100).toFixed(1)}%`;
        this.panel.webview.html = this.getHtml(`
            <h2>Benchmark Results</h2>
            <div class="metrics">
                <div class="metric">
                    <span class="metric-value">${result.total_tasks}</span>
                    <span class="metric-label">Total Tasks</span>
                </div>
                <div class="metric">
                    <span class="metric-value">${result.verified_success_count}</span>
                    <span class="metric-label">Verified Success</span>
                </div>
                <div class="metric">
                    <span class="metric-value">${rate(result.verified_success_rate)}</span>
                    <span class="metric-label">Success Rate</span>
                </div>
                <div class="metric">
                    <span class="metric-value">${rate(result.pass_at_1_rate)}</span>
                    <span class="metric-label">Pass@1 Rate</span>
                </div>
                <div class="metric">
                    <span class="metric-value">${rate(result.repair_success_rate)}</span>
                    <span class="metric-label">Repair Rate</span>
                </div>
                <div class="metric">
                    <span class="metric-value">${rate(result.regression_rate)}</span>
                    <span class="metric-label">Regression Rate</span>
                </div>
            </div>
        `);
    }

    private renderCheck(check: CheckResult): string {
        const statusClass = check.status === 'pass' ? 'pass' : check.status === 'fail' ? 'fail' : 'skip';
        return `
            <div class="check ${statusClass}">
                <span class="check-type">${check.check_type}</span>
                <span class="check-status">${check.status}</span>
                <span class="check-duration">${check.duration_seconds.toFixed(2)}s</span>
                ${check.error_message ? `<pre class="check-error">${check.error_message}</pre>` : ''}
            </div>
        `;
    }

    private getHtml(content: string = ''): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        body {
            font-family: var(--vscode-font-family, 'Segoe UI', sans-serif);
            color: var(--vscode-foreground, #333);
            background: var(--vscode-editor-background, #fff);
            padding: 16px;
        }
        h2 { margin-top: 0; }
        h3 { margin-bottom: 8px; }
        .status {
            padding: 12px 16px;
            border-radius: 4px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .status.pass { background: rgba(40, 167, 69, 0.15); }
        .status.fail { background: rgba(220, 53, 69, 0.15); }
        .status-badge {
            font-weight: bold;
            padding: 4px 12px;
            border-radius: 3px;
            font-size: 12px;
        }
        .status.pass .status-badge { background: #28a745; color: white; }
        .status.fail .status-badge { background: #dc3545; color: white; }
        .blockers {
            background: rgba(255, 193, 7, 0.1);
            padding: 12px 16px;
            border-radius: 4px;
            margin-bottom: 16px;
        }
        .blockers ul { margin: 4px 0; padding-left: 20px; }
        .check {
            padding: 8px 12px;
            border-left: 3px solid #ccc;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .check.pass { border-color: #28a745; }
        .check.fail { border-color: #dc3545; }
        .check.skip { border-color: #6c757d; }
        .check-type { font-weight: bold; min-width: 120px; }
        .check-status { text-transform: uppercase; font-size: 11px; }
        .check-duration { color: var(--vscode-descriptionForeground, #888); font-size: 12px; }
        .check-error {
            width: 100%;
            background: var(--vscode-textBlockQuote-background, #f5f5f5);
            padding: 8px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            margin-top: 4px;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 12px;
        }
        .metric {
            padding: 16px;
            border-radius: 4px;
            background: var(--vscode-editorWidget-background, #f0f0f0);
            text-align: center;
        }
        .metric-value {
            display: block;
            font-size: 24px;
            font-weight: bold;
        }
        .metric-label {
            display: block;
            font-size: 12px;
            color: var(--vscode-descriptionForeground, #888);
            margin-top: 4px;
        }
    </style>
</head>
<body>
    ${content}
</body>
</html>`;
    }

    public dispose(): void {
        ResultsPanel.currentPanel = undefined;
        this.panel.dispose();
        while (this.disposables.length) {
            const d = this.disposables.pop();
            if (d) { d.dispose(); }
        }
    }
}
