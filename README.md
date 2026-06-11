# 📊 Excel InsightForge Agent

**AI-Ready Analytics Platform** — built for the CMRIT FDP *"Agentic AI: Developing Intelligent Agents with Modern AI Frameworks"* (Day 5: Applications, Deployment & Future Trends).

Upload any Excel workbook → get automatic profiling, KPIs, interactive charts, forecasts, anomaly detection — and, with a Groq API key, an **agentic AI analyst** that plans tool calls, inspects your data, and answers business questions.

> Works **with or without** an AI key. No key → 🟡 Analytics Mode (everything except AI narration). Key present → 🟢 AI Mode (Groq Llama 3.3 70B).

---

## 🏗️ Architecture

```
                ┌──────────────────────────────────────────────┐
                │                Streamlit UI                  │
                │  Overview │ KPIs │ Charts │ AI Summary │ Ask │
                └──────┬───────────────────────────┬───────────┘
                       │                           │
            ┌──────────▼──────────┐     ┌──────────▼──────────┐
            │   Analytics Engine   │     │   Agentic AI Layer  │
            │  pandas / numpy      │◄────┤  ReAct tool loop    │
            │  profiling, KPIs,    │tools│  LangChain + Groq   │
            │  forecast, anomalies │     │  llama-3.3-70b      │
            └──────────┬──────────┘     └──────────┬──────────┘
                       │                           │ (optional)
                ┌──────▼───────┐            ┌──────▼───────┐
                │ Excel Upload │            │   Groq API   │
                │ / Demo Data  │            └──────────────┘
                └──────────────┘

   Git push ──► GitHub repo ──► ArgoCD (auto-sync) ──► Kubernetes
                                     ▲                    │
                                     └── self-heal ◄──────┘
   docker build ──► Docker Hub (appars/excel-insightforge-agent)
```

**The agentic part:** the "Ask Data" tab runs a minimal ReAct loop. The LLM receives a tool catalog (`get_kpis`, `group_aggregate`, `trend_and_forecast`, `anomalies`, `declining_products`…), decides which to call, observes JSON results, iterates up to 5 steps, then answers — with the full trace visible in the UI.

---

## 🚀 Local Development

```bash
git clone https://github.com/appars/excel-insightforge-agent
cd excel-insightforge-agent

python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py
# → http://localhost:8501
```

Click **Generate Demo Dataset** for the built-in *Global E-Commerce Analytics* workbook (50k orders, 10k customers, 500 products, marketing + supply-chain sheets with planted insights).

### Run tests

```bash
pip install pytest
pytest -q
```

---

## 🔑 Groq Configuration (AI Mode)

Get a free key at <https://console.groq.com/keys>. Priority order:

1. **Sidebar** API key field (highest)
2. `.env` file → `cp .env.example .env` and set `GROQ_API_KEY=gsk_...`
3. Environment variable → `export GROQ_API_KEY=gsk_...`
4. Nothing → 🟡 **Analytics Mode** (never crashes, gracefully degrades)

| Mode | Indicator | Features |
|---|---|---|
| Analytics | 🟡 | Upload, profiling, KPIs, charts, forecast, anomalies, rule-based summary |
| AI | 🟢 | Everything above + LLM executive summary + agentic Q&A with tool trace |

---

## 🐳 Docker

```bash
# Build
docker build -t appars/excel-insightforge-agent:latest .

# Run (Analytics Mode)
docker run -p 8501:8501 appars/excel-insightforge-agent:latest

# Run (AI Mode)
docker run -p 8501:8501 -e GROQ_API_KEY=gsk_xxx appars/excel-insightforge-agent:latest

# Push to Docker Hub
docker login
docker push appars/excel-insightforge-agent:latest
```

Image highlights: `python:3.11-slim`, non-root user, layer-cached deps, built-in `HEALTHCHECK` on Streamlit's `/_stcore/health`.

---

## 🖥️ Rancher Desktop Setup

1. Install [Rancher Desktop](https://rancherdesktop.io/) → enable **Kubernetes** (containerd or dockerd).
2. Verify: `kubectl get nodes` shows `lima-rancher-desktop` (or similar) Ready.
3. NodePort services are reachable at `localhost:<nodePort>`.

---

## ☸️ Kubernetes Deployment (manual)

```bash
# Optional: real Groq secret (skip → Analytics Mode)
kubectl create secret generic groq-secret --from-literal=GROQ_API_KEY=gsk_xxx

kubectl apply -f k8s/
kubectl get pods -l app=excel-insightforge-agent   # 2 replicas Running

# Access
open http://localhost:30851        # NodePort on Rancher Desktop
# or: kubectl port-forward svc/excel-insightforge-agent 8501:80
```

Manifests include: 2 replicas, readiness + liveness probes on `/_stcore/health`, resource requests/limits, optional secret injection.

> ⚠️ `k8s/secret.yaml` is a **template with an empty key** — never commit real secrets. Create them with `kubectl create secret` or a sealed-secrets/SOPS workflow.

---

## 🔁 GitOps with ArgoCD

```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# UI access
kubectl port-forward svc/argocd-server -n argocd 8080:443
# password:
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Register the app
kubectl apply -f argocd/application.yaml
```

ArgoCD now watches `github.com/appars/excel-insightforge-agent` (path `k8s/`, branch `main`) with **auto-sync + self-heal + prune**.

**Live demo moment 🎬:** edit `k8s/deployment.yaml` in GitHub (e.g. `replicas: 2 → 3`), commit, and watch ArgoCD detect, sync, and roll out — no `kubectl` needed. Then try `kubectl scale deploy excel-insightforge-agent --replicas=1` and watch self-heal revert it. That's GitOps.

---

## 🧪 Health Check

```bash
curl -fsS http://localhost:8501/_stcore/health   # → "ok"
```

Used by Docker `HEALTHCHECK` and both K8s probes.

---

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| `ImagePullBackOff` | Image not pushed / wrong name → `docker push appars/excel-insightforge-agent:latest` |
| Pod `OOMKilled` | Raise memory limit (demo dataset needs ~1Gi) |
| Probes failing | Check `kubectl logs`; Streamlit needs ~10–20 s to boot |
| ArgoCD `Unknown`/`ComparisonError` | Repo URL/branch/path wrong, or repo is private (add repo credentials in ArgoCD) |
| 🟡 mode despite secret | Secret name/key must be `groq-secret` / `GROQ_API_KEY`; restart pods after creating it |
| AI errors / rate limits | App auto-falls back to rule-based summary — demo never breaks |
| NodePort unreachable | `kubectl port-forward svc/excel-insightforge-agent 8501:80` |

---

## 📸 Screenshots

| | |
|---|---|
| ![Overview](assets/screenshot-overview.png) | ![KPIs](assets/screenshot-kpis.png) |
| ![Charts](assets/screenshot-charts.png) | ![Agent trace](assets/screenshot-agent.png) |

*(placeholders — add after first run)*

---

## 📁 Project Structure

```
excel-insightforge-agent/
├── app.py                     # Streamlit UI (tabs, modes, sidebar)
├── config.py                  # Hybrid API-key resolution, logging
├── services/
│   ├── analytics.py           # Profiling, KPIs, forecast, anomalies, rule-based summary
│   ├── ai_service.py          # Groq LLM + agentic ReAct tool loop
│   ├── dataset_generator.py   # 50k-row demo dataset with planted insights
│   └── visualization.py       # Plotly figure builders
├── tests/test_app.py          # Unit + smoke tests
├── k8s/                       # deployment / service / secret manifests
├── argocd/application.yaml    # GitOps app (auto-sync, self-heal)
├── Dockerfile                 # python:3.11-slim, non-root, healthcheck
├── requirements.txt
└── .env.example
```

## 📜 License

MIT — built for teaching. Reuse freely in your FDP sessions.
