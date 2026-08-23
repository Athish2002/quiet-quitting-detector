# Free Online Hosting & Industry-Standard Security Runbook

This guide outlines **100% free hosting strategies** for the Quiet-Quitting Detector and details the **security, privacy, and integrity guardrails** enforced across the codebase.

---

## 1. Free Online Hosting Architectures

| Architecture | Frontend Host | Backend Host | Cost | Best For |
|---|---|---|---|---|
| **Option A: GitHub Pages (Recommended)** | GitHub Pages (`.github/workflows/deploy-pages.yml`) | Standalone Client-Side Simulation / Local-First | **$0.00 / Free Forever** | Demo, Capstone presentation, Portfolio showcase |
| **Option B: Decoupled Fullstack** | GitHub Pages / Vercel / Netlify | Render.com / Koyeb (FastAPI Python) | **$0.00 / Free Tier** | Live multi-user backend with persistent SQLite / PostgreSQL |
| **Option C: All-in-One Container** | Embedded in FastAPI | Hugging Face Spaces (Docker / 16GB RAM) | **$0.00 / Free Tier** | Single-container deployment with direct Python runtime |

---

## 2. Option A: 1-Click Deployment to GitHub Pages (Fastest & Free)

The project includes an automated deployment workflow: [`.github/workflows/deploy-pages.yml`](.github/workflows/deploy-pages.yml).

### How to Activate on GitHub:
1. Push this repository to your GitHub account (`git push origin main`).
2. On GitHub, navigate to **Settings** $\rightarrow$ **Pages** (under Code and automation).
3. Under **Build and deployment**:
   - **Source**: Select **GitHub Actions**.
4. The workflow will automatically run on every push to `main` (or via manual trigger under Actions $\rightarrow$ *Deploy to GitHub Pages*).
5. Your live app will be accessible at:
   `https://<your-github-username>.github.io/<your-repo-name>/`

### Built-in GitHub Pages Protections:
- **SPA Deep-Linking Fix (`404.html` + `index.html`)**: Prevents 404 errors when refreshing sub-routes (e.g. `/cohort`, `/person/Arjun`).
- **Relative Asset Resolution (`vite.config.ts`)**: Generates relative paths (`./assets/...`), ensuring correct loading under subpath URLs.
- **`.nojekyll`**: Bypasses GitHub's default Jekyll processor to serve raw Vite production assets.

---

## 3. Option B: Free Fullstack Deployment (Vercel + Render.com)

### Backend on Render.com (Free Web Service):
1. Sign up at [Render.com](https://render.com) (Free Tier).
2. Click **New +** $\rightarrow$ **Web Service** $\rightarrow$ Connect your GitHub repo.
3. Configure the service:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install uv && uv sync --frozen --all-extras`
   - **Start Command**: `uv run uvicorn app:app --host 0.0.0.0 --port $PORT`
4. Set Environment Variables:
   - `GEMINI_API_KEY`: *(Optional: Your Google Gemini API Key for live AI synthesis)*
   - `GOOGLE_CLOUD_LOCATION`: `global`
   - `IDENTITY_SALT`: *(Any random 32-character string)*

### Frontend on Vercel or GitHub Pages:
- Set `VITE_API_BASE_URL` in the frontend build settings to point to your Render backend URL (e.g. `https://quiet-quitting-api.onrender.com`).

---

## 4. Option C: Free Deployment on Hugging Face Spaces

1. Create a new Space on [Hugging Face Spaces](https://huggingface.co/spaces).
2. Select **Docker** or **Python** (FastAPI template).
3. Push the repository; FastAPI will serve the built static bundle directly on port `7860`.

---

## 5. Security & Privacy Guardrails (Enforced to Industry Standards)

When hosting an AI wellbeing and HR diagnostic application publicly, strict security guardrails prevent intrusive or damaging behavior:

### 🛡️ 1. Zero-Leak Secret Protection
- **Pre-commit & CI Secret Scanners**: GitHub Actions executes `gitleaks` on every commit and PR to prevent API keys, database credentials, or GCP secrets from being committed.
- **Strict `.gitignore`**: Blocks `.env`, `*.db`, `agent_memory/`, `data/*.db`, and runtime credentials.

### 🔒 2. Privacy by Design & Zero-Surveillance Stance (GDPR / NIST AI RMF)
- **No Free-Text Employee Notes**: The schema intentionally contains **no free-text columns** for manager commentary or employee surveillance. Closed-set enums prevent recording private meeting transcripts.
- **Pseudonymous Surrogate Identifiers**: Employee records are indexed using cryptographic surrogate keys rather than raw PII.
- **Individual-Baseline Evaluation**: Trajectories evaluate an individual strictly against their **own earlier weeks**—never ranking employees or comparing them against cohort peers.

### 🛑 3. Web & Application Hardening (OWASP Top 10)
- **Strict Content Security Policy (CSP)**: Blocks inline script injections, clickjacking (`frame-ancestors 'none'`), and unauthorized external cross-origin connections.
- **Input Sanitization & Parameterization**: All database interactions use parameterized SQLite queries; custom SQL ingestion includes strict read-only introspection.
- **Non-Punitive Safe Mode**: The system design enforces that wellbeing flags can **never** trigger automated disciplinary actions or ranking.

### 📜 4. Cryptographic Hash-Chained Audit Trail
- Every access to an individual's assessment is logged into an append-only, SHA-256 hash-chained access log (`/audit`).
- Refused unauthorized requests are recorded as audit entries themselves, ensuring tamper-evident accountability.
