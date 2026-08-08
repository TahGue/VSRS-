/**
 * Status bar manager for VSRS connection and task status
 */

import * as vscode from 'vscode';
import { VSRSClient } from './types';

export class StatusBarManager {
    private statusBarItem: vscode.StatusBarItem;
    private client: VSRSClient;

    constructor(client: VSRSClient) {
        this.client = client;
        this.statusBarItem = vscode.window.createStatusBarItem(
            vscode.StatusBarAlignment.Right,
            100
        );
        this.statusBarItem.command = 'vsrs.connectServer';
        this.update();
    }

    update(): void {
        if (this.client.isConnected()) {
            this.statusBarItem.text = '$(check) VSRS: Connected';
            this.statusBarItem.tooltip = 'VSRS server connected - Click to disconnect';
            this.statusBarItem.command = 'vsrs.disconnectServer';
            this.statusBarItem.backgroundColor = undefined;
        } else {
            this.statusBarItem.text = '$(debug-disconnect) VSRS: Disconnected';
            this.statusBarItem.tooltip = 'VSRS server not connected - Click to connect';
            this.statusBarItem.command = 'vsrs.connectServer';
            this.statusBarItem.backgroundColor = new vscode.ThemeColor(
                'statusBarItem.warningBackground'
            );
        }
        this.statusBarItem.show();
    }

    setBusy(text: string): void {
        this.statusBarItem.text = `$(loading~spin) VSRS: ${text}`;
        this.statusBarItem.backgroundColor = undefined;
    }

    setError(text: string): void {
        this.statusBarItem.text = `$(error) VSRS: ${text}`;
        this.statusBarItem.backgroundColor = new vscode.ThemeColor(
            'statusBarItem.errorBackground'
        );
        this.statusBarItem.show();
    }

    dispose(): void {
        this.statusBarItem.dispose();
    }
}
