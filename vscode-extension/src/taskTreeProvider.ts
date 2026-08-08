/**
 * Task tree view provider for the VSRS sidebar
 */

import * as vscode from 'vscode';
import { TaskInfo, TaskStatus, VSRSClient } from './types';

export class TaskTreeItem extends vscode.TreeItem {
    constructor(
        public readonly task: TaskInfo,
        collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(task.instruction.slice(0, 60), collapsibleState);
        this.id = task.id;
        this.tooltip = `${task.type} - ${task.status}`;
        this.description = task.status;
        this.contextValue = task.status === 'running' ? 'task-running' : 'task';
        this.iconPath = TaskTreeItem.getIcon(task.status);
    }

    private static getIcon(status: TaskStatus): vscode.ThemeIcon {
        switch (status) {
            case 'pending':
                return new vscode.ThemeIcon('circle-outline');
            case 'running':
                return new vscode.ThemeIcon('loading~spin');
            case 'completed':
                return new vscode.ThemeIcon('check');
            case 'failed':
                return new vscode.ThemeIcon('error');
            case 'cancelled':
                return new vscode.ThemeIcon('circle-slash');
            default:
                return new vscode.ThemeIcon('circle');
        }
    }
}

export class TaskTreeProvider implements vscode.TreeDataProvider<TaskTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<TaskTreeItem | undefined>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private tasks: TaskInfo[] = [];

    constructor(private client: VSRSClient) {}

    refresh(): void {
        this._onDidChangeTreeData.fire(undefined);
    }

    setTasks(tasks: TaskInfo[]): void {
        this.tasks = tasks;
        this.refresh();
    }

    getTreeItem(element: TaskTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: TaskTreeItem): Promise<TaskTreeItem[]> {
        if (!element) {
            return this.tasks.map(
                (task) => new TaskTreeItem(task, vscode.TreeItemCollapsibleState.None)
            );
        }
        return [];
    }
}
