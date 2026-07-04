# ⚡ ChargeHub - Mobile Recharge & Scratch Cards Platform

> DEPI Graduation Project - Ministry of Communications & Information Technology

منصة شحن الرصيد وكروت الفكة لجميع الشبكات المصرية (فودافون - اتصالات - اورنج - وي)

## 🏗️ Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│  PostgreSQL  │
│   (Nginx)   │     │   (Flask)   │     │  (Database)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌───────────┐ ┌──────────┐ ┌─────────┐
       │Prometheus │ │  Grafana │ │  Loki   │
       │ (Metrics) │ │(Dashboards)│ │(Logging)│
       └───────────┘ └──────────┘ └─────────┘
```

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | HTML5, CSS3, JavaScript, Nginx |
| Backend | Python Flask, Gunicorn |
| Database | PostgreSQL 16 |
| Containerization | Docker, Docker Compose |
| Orchestration | Kubernetes |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus + Grafana |
| Logging | Loki |
| Automation | Ansible |

## 🚀 Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd Depi_Project-phase1

# Start all services
docker compose up -d --build

# Wait for services to be ready, then access:
# Frontend: http://localhost:8080
# Backend API: http://localhost:5000/api/health
# Grafana: http://localhost:3000 (admin/chargehub123)
# Prometheus: http://localhost:9090
```

## 📁 Project Structure

```
├── backend/                 # Flask microservices
│   ├── app.py              # Main application (JWT, recharge, cards, admin)
│   ├── init_db.py          # Database initialization & seed data
│   ├── requirements.txt    # Python dependencies
│   └── Dockerfile
├── frontend/               # Web application (Arabic RTL, dark theme)
│   ├── index.html          # Landing page
│   ├── login.html          # Login & registration page
│   ├── dashboard.html      # Main user dashboard (recharge, cards, history, profile)
│   ├── admin.html          # Admin panel (restricted to admin@chargehub.com)
│   ├── styles.css          # Modern dark theme styles
│   ├── nginx.conf          # Nginx config with API proxy
│   └── Dockerfile
├── k8s/                    # Kubernetes manifests
│   ├── namespace.yaml
│   ├── postgres.yaml       # PostgreSQL with PVC (5Gi)
│   ├── db-init-job.yaml    # Database initialization Job
│   ├── backend.yaml        # Backend Deployment + HPA + Service
│   └── frontend.yaml       # Frontend Deployment + Service + Ingress
├── monitoring/             # Monitoring & logging configuration
│   ├── prometheus.yml      # Prometheus scrape config
│   ├── promtail.yml        # Promtail log collection config
│   └── grafana/
│       ├── dashboards/
│       │   ├── dashboard.yml                # Provisioning config
│       │   └── chargehub-dashboard.json     # API monitoring dashboard
│       └── datasources/
│           └── datasource.yml               # Prometheus + Loki datasources
├── ansible/                # Automation playbooks
│   ├── inventory.yml
│   ├── playbook-deploy.yml
│   └── playbook-monitoring.yml
├── .github/workflows/      # CI/CD pipeline
│   └── ci-cd.yml           # 3-stage: test → build → deploy
└── docker-compose.yml      # Full stack composition (8 services)
```

## 🔌 API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | /api/auth/register | Register new user | ❌ |
| POST | /api/auth/login | Login | ❌ |
| GET | /api/auth/profile | Get user profile | ✅ |
| GET | /api/recharge/operators | List operators | ❌ |
| POST | /api/recharge | Recharge phone (validates prefix per operator) | ✅ |
| GET | /api/cards/available | Available cards | ❌ |
| POST | /api/cards/purchase | Buy scratch card | ✅ |
| GET | /api/transactions | Transaction history (paginated) | ✅ |
| GET | /api/admin/stats | Platform statistics | ❌ |
| POST | /api/admin/add-balance | Add balance to user | ❌ |
| GET | /api/health | Health check | ❌ |
| GET | /metrics | Prometheus metrics (via prometheus-flask-instrumentator) | ❌ |

## 👥 Team Roles

- **Monitoring & Logging Engineer** - Prometheus, Grafana, Loki
- **Automation & Ansible Engineer** - Ansible playbooks, infrastructure
- **Backend & Microservices Engineer** - Flask API, PostgreSQL
- **Docker & Containerization Engineer** - Dockerfiles, Compose
- **CI/CD Pipeline Engineer** - GitHub Actions, automated deployment

## 📊 Monitoring

- **Grafana Dashboard**: http://localhost:3000 (admin/chargehub123)
- **Prometheus**: http://localhost:9090
- **Loki Logs**: Accessible through Grafana

## 🚢 Deployment with Ansible

```bash
cd ansible
ansible-playbook -i inventory.yml playbook-deploy.yml
ansible-playbook -i inventory.yml playbook-monitoring.yml
```

## 📜 License

DEPI Graduation Project © 2024
