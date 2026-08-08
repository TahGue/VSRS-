# VSRS Web Dashboard

React-based dashboard for managing VSRS runs, viewing verification results, and browsing benchmarks.

## Features

- **Runs Page** — List all runs, create new runs with a form, navigate to run details
- **Run Detail** — View run info, task details, verification checks with pass/fail status, diff viewer with syntax highlighting
- **Benchmarks** — Browse available benchmark suites
- **Settings** — View current VSRS configuration

## Getting Started

### Development

```bash
cd web-dashboard
npm install
npm run dev
```

The dev server runs on port 5173 and proxies API requests to `http://localhost:8000`.

### Production Build

```bash
npm run build
```

The built files go to `dist/` and can be served by the VSRS FastAPI backend.

### Serving from FastAPI

The VSRS API server can serve the built dashboard. After building:

```bash
# Build the dashboard
cd web-dashboard && npm run build && cd ..

# Start the API server (serves dashboard at /)
python -m uvicorn vsrs.api.app:app --port 8000
```

## Architecture

```
web-dashboard/
├── package.json       # Dependencies and scripts
├── tsconfig.json      # TypeScript config
├── vite.config.ts     # Vite config with API proxy
├── index.html         # HTML entry point
└── src/
    ├── main.tsx       # React entry, router setup
    ├── App.tsx        # Layout with sidebar navigation
    ├── api.ts         # API client functions
    ├── types.ts       # TypeScript interfaces
    ├── index.css      # Global styles (dark theme)
    └── pages/
        ├── RunsPage.tsx       # Run list and creation
        ├── RunDetailPage.tsx  # Run details with verification and diff
        ├── BenchmarksPage.tsx # Benchmark listing
        └── SettingsPage.tsx   # Configuration viewer
```

## Tech Stack

- **React 18** — UI framework
- **React Router 6** — Client-side routing
- **Vite 5** — Build tool and dev server
- **TypeScript 5** — Type safety
- **Lucide React** — Icons
