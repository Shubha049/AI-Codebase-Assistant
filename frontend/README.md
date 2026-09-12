# AI Codebase Assistant — React Frontend

Professional React/Vite frontend for the Phase 1–9 repository intelligence backend.

## Features

- Repository workspace and ZIP upload
- Repository overview and health signals
- Grounded AI Q&A with citations
- Architecture explorer
- Security findings and scan trigger
- Documentation generation and markdown preview
- Repository-specific interview preparation
- Persistent active-repository selection
- Responsive dark enterprise SaaS UI

## Run

```bash
npm install
cp .env.example .env
npm run dev
```

Default API target: `http://localhost:8000`.

Set `VITE_API_BASE_URL` to point to another FastAPI instance.

## Build

```bash
npm run build
```
