# VSRS - VSCode Extension

Run verification, repair, and benchmark tasks directly in VSCode with the Verified Self-Repair System.

## Features

- **Run Verification** — Submit code changes for automated verification (syntax, build, tests, lint, type check)
- **Run Repair** — Automated multi-attempt repair with verification gates
- **Run Benchmark** — Execute benchmark suites and view results
- **Task Tree View** — Browse and manage tasks in the sidebar
- **Results Panel** — Rich webview with check details, blockers, and metrics
- **Status Bar** — Connection status and operation progress
- **Keyboard Shortcuts** — `Ctrl+Shift+V` for verification, `Ctrl+Shift+R` for repair

## Getting Started

1. Start the VSRS API server:
   ```bash
   python -m vsrs.api.server --port 8000
   ```

2. Install the extension in VSCode

3. Configure the server URL in Settings > VSRS:
   - `vsrs.serverUrl`: API server URL (default: `http://localhost:8000`)
   - `vsrs.apiKey`: API key for authentication
   - `vsrs.maxAttempts`: Maximum repair attempts (default: 3)
   - `vsrs.requiredGates`: Required verification gates

4. Use `Ctrl+Shift+P` and search for "VSRS" commands

## Commands

| Command | Description |
|---------|-------------|
| `VSRS: Run Verification` | Create a task and run verification |
| `VSRS: Run Repair` | Create a task and run automated repair |
| `VSRS: Run Benchmark` | Execute the benchmark suite |
| `VSRS: View Results` | Open the results webview panel |
| `VSRS: Connect to Server` | Connect to the VSRS API server |
| `VSRS: Disconnect from Server` | Disconnect from the server |
| `VSRS: Refresh Tasks` | Refresh the task list |
| `VSRS: Cancel Task` | Cancel a running task |
| `VSRS: Show Settings` | Open VSRS settings |

## Architecture

```
vscode-extension/
├── package.json          # Extension manifest
├── tsconfig.json         # TypeScript config
├── src/
│   ├── extension.ts      # Entry point, command registration
│   ├── types.ts          # Shared type definitions
│   ├── apiClient.ts      # REST API client
│   ├── taskTreeProvider.ts  # Sidebar tree view
│   ├── statusBar.ts      # Status bar management
│   └── resultsPanel.ts   # Webview results panel
└── media/
    └── vsrs-icon.svg     # Extension icon
```

## Development

```bash
cd vscode-extension
npm install
npm run compile
# Press F5 in VSCode to launch extension development host
```
