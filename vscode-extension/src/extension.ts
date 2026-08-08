/**
 * VSRS VSCode Extension - Entry point
 * Activates the extension and registers all commands
 */

import * as vscode from 'vscode';
import { VSRSApiClient } from './apiClient';
import { TaskTreeProvider } from './taskTreeProvider';
import { StatusBarManager } from './statusBar';
import { ResultsPanel } from './resultsPanel';
import { ServerConfig, VSRSClient } from './types';

let client: VSRSClient;
let taskTreeProvider: TaskTreeProvider;
let statusBar: StatusBarManager;

export function activate(context: vscode.ExtensionContext): void {
    // Load configuration
    const config = loadConfig();
    client = new VSRSApiClient(config);

    // Create providers
    taskTreeProvider = new TaskTreeProvider(client);
    statusBar = new StatusBarManager(client);

    // Register tree view
    const treeView = vscode.window.createTreeView('vsrs.tasksView', {
        treeDataProvider: taskTreeProvider,
        showCollapseAll: true,
    });

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('vsrs.connectServer', () => connectServer()),
        vscode.commands.registerCommand('vsrs.disconnectServer', () => disconnectServer()),
        vscode.commands.registerCommand('vsrs.runVerification', () => runVerification()),
        vscode.commands.registerCommand('vsrs.runRepair', () => runRepair()),
        vscode.commands.registerCommand('vsrs.runBenchmark', () => runBenchmark()),
        vscode.commands.registerCommand('vsrs.viewResults', () => viewResults(context)),
        vscode.commands.registerCommand('vsrs.refreshTasks', () => refreshTasks()),
        vscode.commands.registerCommand('vsrs.viewTaskDetails', (item) => viewTaskDetails(item)),
        vscode.commands.registerCommand('vsrs.cancelTask', (item) => cancelTask(item)),
        vscode.commands.registerCommand('vsrs.showSettings', () => showSettings()),
    );

    context.subscriptions.push(treeView, statusBar);

    // Auto-connect if server URL is configured
    if (config.serverUrl) {
        connectServer().catch(() => {});
    }

    // Watch for config changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('vsrs')) {
                const newConfig = loadConfig();
                (client as VSRSApiClient).disconnect();
                client = new VSRSApiClient(newConfig);
                statusBar.update();
            }
        })
    );

    // Auto-run verification on save if enabled
    if (config.autoRunVerification) {
        context.subscriptions.push(
            vscode.workspace.onDidSaveTextDocument(() => {
                runVerification().catch(() => {});
            })
        );
    }
}

export function deactivate(): void {
    if (client) {
        (client as VSRSApiClient).disconnect();
    }
    if (statusBar) {
        statusBar.dispose();
    }
}

function loadConfig(): ServerConfig {
    const cfg = vscode.workspace.getConfiguration('vsrs');
    return {
        serverUrl: cfg.get<string>('serverUrl', 'http://localhost:8000'),
        apiKey: cfg.get<string>('apiKey', ''),
        maxAttempts: cfg.get<number>('maxAttempts', 3),
        timeout: cfg.get<number>('timeout', 300),
        requiredGates: cfg.get<string[]>('requiredGates', ['syntax', 'build', 'existing_tests']),
        autoRunVerification: cfg.get<boolean>('autoRunVerification', false),
    };
}

async function connectServer(): Promise<void> {
    statusBar.setBusy('Connecting...');
    try {
        const connected = await client.connect();
        if (connected) {
            statusBar.update();
            vscode.window.showInformationMessage('VSRS: Connected to server');
            await refreshTasks();
        } else {
            statusBar.setError('Connection failed');
            vscode.window.showErrorMessage('VSRS: Failed to connect to server');
        }
    } catch (e) {
        statusBar.setError('Connection error');
        vscode.window.showErrorMessage(`VSRS: Connection error - ${e}`);
    }
}

async function disconnectServer(): Promise<void> {
    (client as VSRSApiClient).disconnect();
    statusBar.update();
    vscode.window.showInformationMessage('VSRS: Disconnected from server');
    taskTreeProvider.setTasks([]);
}

async function runVerification(): Promise<void> {
    if (!client.isConnected()) {
        vscode.window.showWarningMessage('VSRS: Not connected to server');
        return;
    }

    const instruction = await vscode.window.showInputBox({
        prompt: 'Enter task instruction for verification',
        placeHolder: 'e.g. Fix the authentication bug in login.py',
    });
    if (!instruction) { return; }

    statusBar.setBusy('Creating task...');
    try {
        const task = await client.createTask(instruction, 'bugfix');
        statusBar.setBusy('Running verification...');
        const report = await client.runVerification(task.id);

        const panel = ResultsPanel.createOrShow(vscode.extensions.getExtension('vsrs.vscode')!.extensionUri);
        panel.showVerificationReport(report);

        statusBar.update();
        if (report.required_passed) {
            vscode.window.showInformationMessage('VSRS: Verification passed');
        } else {
            vscode.window.showWarningMessage(`VSRS: Verification failed - ${report.blockers.length} blockers`);
        }
        await refreshTasks();
    } catch (e) {
        statusBar.setError('Verification failed');
        vscode.window.showErrorMessage(`VSRS: Verification error - ${e}`);
    }
}

async function runRepair(): Promise<void> {
    if (!client.isConnected()) {
        vscode.window.showWarningMessage('VSRS: Not connected to server');
        return;
    }

    const instruction = await vscode.window.showInputBox({
        prompt: 'Enter task instruction for repair',
        placeHolder: 'e.g. Fix the failing test in test_auth.py',
    });
    if (!instruction) { return; }

    const config = loadConfig();
    statusBar.setBusy('Creating task...');
    try {
        const task = await client.createTask(instruction, 'bugfix');
        statusBar.setBusy('Running repair...');
        const result = await client.runRepair(task.id, config.maxAttempts);

        const panel = ResultsPanel.createOrShow(vscode.extensions.getExtension('vsrs.vscode')!.extensionUri);
        panel.showVerificationReport({
            patch_id: task.id,
            checks: result.checks || [],
            required_passed: result.verified,
            blockers: result.blockers || [],
            final_status: result.final_status,
        });

        statusBar.update();
        if (result.verified) {
            vscode.window.showInformationMessage('VSRS: Repair successful');
        } else {
            vscode.window.showWarningMessage('VSRS: Repair did not achieve verification');
        }
        await refreshTasks();
    } catch (e) {
        statusBar.setError('Repair failed');
        vscode.window.showErrorMessage(`VSRS: Repair error - ${e}`);
    }
}

async function runBenchmark(): Promise<void> {
    if (!client.isConnected()) {
        vscode.window.showWarningMessage('VSRS: Not connected to server');
        return;
    }

    statusBar.setBusy('Running benchmark...');
    try {
        const result = await client.runBenchmark();
        const panel = ResultsPanel.createOrShow(vscode.extensions.getExtension('vsrs.vscode')!.extensionUri);
        panel.showBenchmarkResult(result);
        statusBar.update();
        vscode.window.showInformationMessage(
            `VSRS: Benchmark complete - ${result.verified_success_count}/${result.total_tasks} verified`
        );
    } catch (e) {
        statusBar.setError('Benchmark failed');
        vscode.window.showErrorMessage(`VSRS: Benchmark error - ${e}`);
    }
}

function viewResults(context: vscode.ExtensionContext): void {
    ResultsPanel.createOrShow(context.extensionUri);
}

async function refreshTasks(): Promise<void> {
    if (!client.isConnected()) { return; }
    try {
        const tasks = await client.listTasks();
        taskTreeProvider.setTasks(tasks);
    } catch (e) {
        vscode.window.showErrorMessage(`VSRS: Failed to refresh tasks - ${e}`);
    }
}

async function viewTaskDetails(item: any): Promise<void> {
    if (!item || !item.task) { return; }
    const task = item.task;
    const panel = ResultsPanel.createOrShow(vscode.extensions.getExtension('vsrs.vscode')!.extensionUri);
    if (task.result) {
        panel.showVerificationReport({
            patch_id: task.id,
            checks: task.result.checks || [],
            required_passed: task.result.verified,
            blockers: task.result.blockers || [],
            final_status: task.result.final_status,
        });
    } else {
        vscode.window.showInformationMessage(`VSRS: Task ${task.id} has no results yet`);
    }
}

async function cancelTask(item: any): Promise<void> {
    if (!item || !item.task) { return; }
    try {
        const cancelled = await client.cancelTask(item.task.id);
        if (cancelled) {
            vscode.window.showInformationMessage(`VSRS: Task ${item.task.id} cancelled`);
            await refreshTasks();
        } else {
            vscode.window.showWarningMessage(`VSRS: Could not cancel task ${item.task.id}`);
        }
    } catch (e) {
        vscode.window.showErrorMessage(`VSRS: Cancel error - ${e}`);
    }
}

function showSettings(): void {
    vscode.commands.executeCommand('workbench.action.openSettings', 'vsrs');
}
