# 🔋 ChargeHub - Project Context Report

> **مشروع تخرج DEPI** - منصة شحن موبايل وكروت سكراتش إلكترونية
> آخر تحديث: بناءً على أحدث commit في الـ repo

---

## 📁 1. هيكل المشروع (Project Structure)

```
Depi_Project-phase1/
├── .github/
│   └── workflows/
│       └── ci-cd.yml              # CI/CD Pipeline (GitHub Actions)
├── ansible/
│   ├── inventory.yml              # Ansible inventory
│   ├── playbook-deploy.yml        # Deployment playbook
│   └── playbook-monitoring.yml    # Monitoring setup playbook
├── backend/
│   ├── app.py                     # Flask API الرئيسي
│   ├── init_db.py                 # سكريبت إنشاء الداتابيز والـ seed data
│   ├── requirements.txt           # Python dependencies
│   └── Dockerfile                 # Backend container image
├── frontend/
│   ├── index.html                 # Landing page رئيسية
│   ├── login.html                 # صفحة تسجيل الدخول/التسجيل
│   ├── dashboard.html             # لوحة تحكم المستخدم
│   ├── admin.html                 # لوحة تحكم الأدمن
│   ├── styles.css                 # CSS (Arabic RTL + Dark Theme)
│   ├── nginx.conf.template        # Nginx config template (envsubst)
│   └── Dockerfile                 # Frontend container image
├── k8s/
│   ├── namespace.yaml             # Kubernetes namespace
│   ├── postgres.yaml              # PostgreSQL (PVC + Secret + Deployment + Service)
│   ├── backend.yaml               # Backend (ConfigMap + Secret + Deployment + Service + HPA)
│   ├── frontend.yaml              # Frontend (Deployment + Service + Ingress)
│   └── db-init-job.yaml           # Database initialization Job
├── monitoring/
│   ├── prometheus.yml             # Prometheus scrape config
│   ├── promtail.yml               # Promtail log shipping config
│   └── grafana/
│       ├── dashboards/
│       │   ├── chargehub-dashboard.json  # Grafana dashboard
│       │   └── dashboard.yml             # Dashboard provisioning
│       └── datasources/
│           └── datasource.yml            # Prometheus + Loki datasources
├── docker-compose.yml             # Full local stack (8 services)
├── README.md
└── .gitignore
```

---

## ⚙️ 2. Backend (Flask API)

### 2.1 التقنيات المستخدمة
- **Framework:** Flask 3.0.3
- **Auth:** JWT via flask-jwt-extended 4.6.0
- **Database:** PostgreSQL 16 via psycopg2-binary
- **WSGI Server:** Gunicorn 22.0.0 (2 workers)
- **Metrics:** prometheus-client 0.21.0
- **CORS:** flask-cors 4.0.0

### 2.2 requirements.txt

```txt
flask==3.0.3
flask-cors==4.0.0
flask-jwt-extended==4.6.0
psycopg2-binary==2.9.9
gunicorn==22.0.0
python-dotenv==1.0.1
prometheus-client==0.21.0
```

### 2.3 API Endpoints

| Method | Endpoint | Auth | الوصف |
|--------|----------|------|--------|
| `POST` | `/api/auth/register` | ❌ | تسجيل مستخدم جديد (يبدأ برصيد 1000 جنيه) |
| `POST` | `/api/auth/login` | ❌ | تسجيل دخول + JWT token |
| `GET` | `/api/auth/profile` | ✅ JWT | بيانات المستخدم الحالي |
| `GET` | `/api/recharge/operators` | ❌ | قائمة شبكات المحمول المدعومة |
| `POST` | `/api/recharge` | ✅ JWT | شحن رقم موبايل |
| `GET` | `/api/cards/available` | ❌ | الكروت المتاحة (مجمعة بالشبكة والفئة) |
| `POST` | `/api/cards/purchase` | ✅ JWT | شراء كارت سكراتش |
| `GET` | `/api/transactions` | ✅ JWT | سجل العمليات (مع pagination) |
| `GET` | `/api/admin/stats` | ❌ | إحصائيات المنصة (Admin) |
| `POST` | `/api/admin/add-balance` | ❌ | إضافة رصيد لمستخدم (Admin) |
| `GET` | `/api/health` | ❌ | Health check (للـ load balancers) |
| `GET` | `/metrics` | ❌ | Prometheus metrics endpoint |

### 2.4 الشبكات المدعومة

| Operator | Prefix | ID |
|----------|--------|----|
| Vodafone | 010 | vodafone |
| Etisalat | 011 | etisalat |
| Orange | 012 | orange |
| WE | 015 | we |

**مبالغ الشحن المتاحة:** 5, 10, 15, 20, 25, 50, 100, 200 جنيه

### 2.5 Database Schema

```sql
-- جدول المستخدمين
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(120) UNIQUE NOT NULL,
    password_hash   VARCHAR(256) NOT NULL,
    balance         DECIMAL(10, 2) DEFAULT 0.00 NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- جدول العمليات
CREATE TABLE transactions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(20) NOT NULL CHECK (type IN ('recharge', 'card_purchase', 'deposit')),
    operator        VARCHAR(20),
    amount          DECIMAL(10, 2) NOT NULL,
    phone_number    VARCHAR(15),
    status          VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- جدول كروت الشحن
CREATE TABLE cards (
    id              SERIAL PRIMARY KEY,
    operator        VARCHAR(20) NOT NULL,
    denomination    DECIMAL(10, 2) NOT NULL,
    serial_number   VARCHAR(20) UNIQUE NOT NULL,
    pin             VARCHAR(20) NOT NULL,
    is_sold         BOOLEAN DEFAULT FALSE,
    sold_to         INTEGER REFERENCES users(id),
    sold_at         TIMESTAMP
);
```

**Indexes:**
- `idx_transactions_user_id` — بحث سريع بالمستخدم
- `idx_transactions_created_at DESC` — ترتيب زمني
- `idx_cards_operator_denomination` — بحث الكروت بالشبكة والفئة
- `idx_cards_is_sold (partial WHERE is_sold = FALSE)` — كروت متاحة فقط
- `idx_users_email` — بحث بالإيميل

**Seed Data:**
- 320 كارت سكراتش (4 شبكات × 8 فئات × 10 كروت لكل تركيبة)
- Admin user: `admin@chargehub.com` / رصيد 99,999 جنيه

### 2.6 Backend Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "app:app"]
```

### 2.7 Prometheus Metrics

الـ Backend بيعمل expose لـ metrics عند `/metrics` باستخدام `prometheus_client`:
- `http_requests_total` (Counter) — إجمالي الطلبات بالـ method, endpoint, status
- `http_request_duration_seconds` (Histogram) — زمن الاستجابة بالـ method, endpoint

---

## 🎨 3. Frontend (Nginx + Static HTML)

### 3.1 صفحات HTML

| الملف | الوصف |
|-------|--------|
| `index.html` | Landing page — واجهة المنصة الرئيسية (معلومات + CTA) |
| `login.html` | صفحة تسجيل الدخول والتسجيل الجديد |
| `dashboard.html` | لوحة المستخدم — شحن، شراء كروت، سجل العمليات |
| `admin.html` | لوحة الأدمن — إحصائيات، إدارة مستخدمين، إضافة رصيد |

**التصميم:** Dark theme + Arabic RTL + Responsive (الـ CSS في `styles.css`)

### 3.2 آلية المصادقة (Auth Mechanism)

1. المستخدم يسجل/يدخل عبر `/api/auth/login` أو `/api/auth/register`
2. الـ Backend يرجّع `access_token` (JWT)
3. الـ Frontend يخزّن الـ token في `localStorage`
4. كل request محمي بيبعت Header: `Authorization: Bearer <token>`
5. لو الـ token انتهى أو مش موجود → redirect لصفحة login

### 3.3 nginx.conf.template

```nginx
server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # API proxy to backend
    location /api/ {
        proxy_pass https://${BACKEND_HOST}/api/;
        proxy_ssl_server_name on;
        proxy_set_header Host ${BACKEND_HOST};
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 30s;
    }

    # Metrics proxy
    location /metrics {
        proxy_pass https://${BACKEND_HOST}/metrics;
        proxy_ssl_server_name on;
        proxy_set_header Host ${BACKEND_HOST};
    }

    # Frontend static files
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
```

> **ملاحظة:** الـ `${BACKEND_HOST}` بيتحل وقت الـ container startup عن طريق `envsubst`
> ده مهم لـ Railway لأن الـ private network domain بيتغير

### 3.4 Frontend Dockerfile

```dockerfile
FROM nginx:alpine
RUN apk add --no-cache gettext
COPY index.html /usr/share/nginx/html/index.html
COPY login.html /usr/share/nginx/html/login.html
COPY dashboard.html /usr/share/nginx/html/dashboard.html
COPY admin.html /usr/share/nginx/html/admin.html
COPY styles.css /usr/share/nginx/html/styles.css
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
CMD ["sh", "-c", "envsubst '${BACKEND_HOST}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
```

> **الفكرة:** `envsubst` بتستبدل `${BACKEND_HOST}` بقيمة الـ environment variable الفعلية وقت الـ runtime.
> كده نقدر نغيّر الـ backend host من غير ما نعمل rebuild للـ image.

---

## 🐳 4. Docker & Docker Compose

### 4.1 الخدمات (8 Services)

| Service | Image | Port | الوظيفة |
|---------|-------|------|---------|
| `postgres` | postgres:16-alpine | 5432 | قاعدة البيانات الرئيسية |
| `backend` | build: ./backend | 5000 | Flask API |
| `db-init` | build: ./backend | — | one-shot: يشغّل `init_db.py` ويموت |
| `frontend` | build: ./frontend | 8080→80 | Nginx static + reverse proxy |
| `prometheus` | prom/prometheus:latest | 9090 | Metrics collection |
| `grafana` | grafana/grafana:latest | 3000 | Metrics visualization |
| `loki` | grafana/loki:latest | 3100 | Log aggregation |
| `promtail` | grafana/promtail:latest | — | Docker log shipping to Loki |

### 4.2 docker-compose.yml (secrets redacted)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: chargehub-db
    environment:
      POSTGRES_USER: chargehub
      POSTGRES_PASSWORD: <REDACTED>
      POSTGRES_DB: chargehub
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U chargehub"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - chargehub-net

  backend:
    build: ./backend
    container_name: chargehub-backend
    environment:
      DATABASE_URL: postgresql://chargehub:<REDACTED>@postgres:5432/chargehub
      JWT_SECRET_KEY: <REDACTED>
      FLASK_DEBUG: "false"
      CORS_ORIGINS: "*"
    ports:
      - "5000:5000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')\""]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - chargehub-net

  db-init:
    build: ./backend
    container_name: chargehub-db-init
    command: python init_db.py
    environment:
      DATABASE_URL: postgresql://chargehub:<REDACTED>@postgres:5432/chargehub
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"
    networks:
      - chargehub-net

  frontend:
    build: ./frontend
    container_name: chargehub-frontend
    ports:
      - "8080:80"
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - chargehub-net

  prometheus:
    image: prom/prometheus:latest
    container_name: chargehub-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=7d'
    restart: unless-stopped
    networks:
      - chargehub-net

  grafana:
    image: grafana/grafana:latest
    container_name: chargehub-grafana
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: <REDACTED>
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    restart: unless-stopped
    networks:
      - chargehub-net

  loki:
    image: grafana/loki:latest
    container_name: chargehub-loki
    ports:
      - "3100:3100"
    volumes:
      - loki_data:/loki
    restart: unless-stopped
    networks:
      - chargehub-net

  promtail:
    image: grafana/promtail:latest
    container_name: chargehub-promtail
    volumes:
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./monitoring/promtail.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    depends_on:
      - loki
    restart: unless-stopped
    networks:
      - chargehub-net

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:
  loki_data:

networks:
  chargehub-net:
    driver: bridge
```

---

## ☸️ 5. Kubernetes Manifests

### 5.1 ملفات الـ K8s

| الملف | المحتويات |
|-------|-----------|
| `namespace.yaml` | Namespace: `chargehub` |
| `postgres.yaml` | PVC (5Gi) + Secret + Deployment + Service (`postgres-service:5432`) |
| `backend.yaml` | ConfigMap + Secret + Deployment (3 replicas) + Service + **HPA** (2-10 pods, target CPU 70%) |
| `frontend.yaml` | Deployment (2 replicas) + Service + **Ingress** (host: `chargehub.local`) |
| `db-init-job.yaml` | Job مع initContainer (wait-for-postgres) + container يشغّل `init_db.py` |

### 5.2 ترتيب التطبيق

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres.yaml
# انتظر لحد ما الـ postgres pod يبقى Ready
kubectl apply -f k8s/db-init-job.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/frontend.yaml
```

### 5.3 Backend HPA (Horizontal Pod Autoscaler)

```yaml
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### 5.4 Ingress

```yaml
spec:
  ingressClassName: nginx
  rules:
    - host: chargehub.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 80
```

---

## 🔄 6. CI/CD Pipeline (GitHub Actions)

### 6.1 الـ Workflow: `.github/workflows/ci-cd.yml`

**Triggers:** Push to `main`/`develop` + Pull Requests to `main`

### 6.2 المراحل الثلاثة

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   1. TEST       │────▶│   2. BUILD      │────▶│   3. DEPLOY     │
│   Lint & Test   │     │   Docker Push   │     │   Notification  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

#### Stage 1: Test (Lint & Test)
- **Service Container:** PostgreSQL 16-alpine (`chargehub_test` DB)
- **Python:** 3.12
- **Steps:**
  1. Install `requirements.txt`
  2. Run `flake8` (max-line-length=120, ignore E501,W503)
  3. Initialize test DB via `init_db.py`
  4. Run health check test (`/api/health` returns 200)

#### Stage 2: Build & Push (Docker Images)
- **Condition:** Push events only (not PRs)
- **Registry:** GitHub Container Registry (ghcr.io)
- **Images:**
  - `ghcr.io/<owner>/chargehub-backend:latest` + `:${{ github.sha }}`
  - `ghcr.io/<owner>/chargehub-frontend:latest` + `:${{ github.sha }}`
- **Cache:** GitHub Actions cache (type=gha)
- **Permission:** `packages: write` (مطلوب لـ GHCR push)
- **Note:** Lowercase repo owner لتجنب مشاكل GHCR

#### Stage 3: Deploy Notification
- **Condition:** Push to `main` only
- **Action:** بيطبع ملخص إن Railway متوصل بالـ repo وبيعمل auto-deploy
- Railway بيسحب أحدث commit من `main` تلقائياً — مفيش deploy يدوي

---

## 📊 7. Monitoring Stack

### 7.1 Prometheus (`monitoring/prometheus.yml`)

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'chargehub-backend'
    metrics_path: /metrics
    static_configs:
      - targets: ['backend:5000']
        labels:
          service: 'backend'

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

**بيجمع metrics من:**
- Backend Flask app (port 5000) → `http_requests_total`, `http_request_duration_seconds`
- Prometheus نفسه (self-monitoring)

### 7.2 Grafana

**Datasources (auto-provisioned):**
- **Prometheus** (default) → `http://prometheus:9090`
- **Loki** → `http://loki:3100`

**Dashboards:**
- `chargehub-dashboard.json` — provisioned تلقائياً من `/etc/grafana/provisioning/dashboards`
- Admin: `admin` / `<REDACTED>`

### 7.3 Loki + Promtail (Log Aggregation)

**Promtail config (`monitoring/promtail.yml`):**

```yaml
server:
  http_listen_port: 9080

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
        filters:
          - name: label
            values: ["com.docker.compose.project=depi_project-phase1"]
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: 'container'
      - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
        target_label: 'service'
      - source_labels: ['__meta_docker_container_label_com_docker_compose_project']
        target_label: 'project'
```

**كيف بيشتغل:**
1. Promtail بيتوصل بالـ Docker socket
2. بيكتشف containers الخاصة بالـ compose project تلقائياً
3. بيعمل relabel للـ logs بالـ container name والـ service name
4. بيبعت اللوجات لـ Loki
5. Grafana بتعرض اللوجات من Loki (قابلة للبحث والفلترة)

---

## 🌍 8. Environment Variables

| المتغير | الوصف | القيمة الافتراضية |
|---------|-------|-------------------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://chargehub:<REDACTED>@postgres:5432/chargehub` |
| `JWT_SECRET_KEY` | مفتاح توقيع JWT tokens | `<REDACTED>` |
| `JWT_TOKEN_EXPIRES` | مدة صلاحية الـ token بالثواني | `86400` (24 ساعة) |
| `FLASK_DEBUG` | وضع التطوير | `false` |
| `CORS_ORIGINS` | الـ origins المسموحة | `*` |
| `FLASK_PORT` | بورت الـ Flask app | `5000` |
| `BACKEND_HOST` | (Frontend/Railway) domain الـ backend | متغير حسب البيئة |
| `POSTGRES_USER` | PostgreSQL username | `chargehub` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `<REDACTED>` |
| `POSTGRES_DB` | اسم الداتابيز | `chargehub` |
| `GF_SECURITY_ADMIN_USER` | Grafana admin username | `admin` |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana admin password | `<REDACTED>` |

---

## 🚂 9. Railway Deployment

### 9.1 الوضع الحالي

- **Backend:** متنشر على Railway كـ service (auto-deploy من `main`)
- **Frontend:** متنشر على Railway — بيستخدم `nginx.conf.template` مع `envsubst`
- **الربط:** Frontend بيعمل reverse proxy لـ Backend عبر Railway private network

### 9.2 آلية العمل على Railway

1. Railway بيسحب الكود من GitHub (branch: `main`) تلقائياً مع كل push
2. بيعمل build للـ Docker images باستخدام الـ Dockerfile الموجود
3. Frontend بيستخدم `BACKEND_HOST` environment variable (Railway reference variable)
4. وقت startup، `envsubst` بيستبدل `${BACKEND_HOST}` في nginx config بالقيمة الفعلية
5. Nginx بيعمل proxy pass لـ `/api/*` requests للـ backend عبر HTTPS

### 9.3 سبب استخدام envsubst

في Railway، الـ backend domain مش ثابت (private network). فبدل ما نعمل hardcode:
- بنحط template في nginx config
- وقت الـ container boot بيحل الـ variable
- كده لو Railway غيّر الـ domain، بس نغيّر الـ env variable ومحتاجوش rebuild

---

## 📜 10. Git History

### 10.1 آخر Commits

```
9f31f52 fix: use Railway reference variable BACKEND_HOST via envsubst template
401719c fix: add dynamic DNS resolver for backend private network domain in nginx
812834d refactor: simplify deploy job since Railway auto-deploys from main
4fe1462 fix: configure frontend for Railway (port 8080, private network proxy to backend)
2be67e3 fix: add packages write permission for GHCR push
324d36a fix: lowercase repository owner for GHCR image tags
b12fd87 fix: flake8 lint errors (unused import, blank lines, long lines)
59c8dc0 fix: healthcheck, metrics via prometheus_client, k8s init job, CI/CD deploy, grafana dashboard, loki logging via promtail, cleanup
999c80d Initial project upload
```

### 10.2 Git Status

```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  deleted:    frontend/nginx.conf

(nginx.conf اتمسح لأنه اتعوّض بـ nginx.conf.template — الـ template version بيدعم envsubst لـ Railway)
```

---

## 🏗️ 11. ملخص المعمارية (Architecture Summary)

```
┌─────────────────────────────────────────────────────────────┐
│                        USER (Browser)                        │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/HTTPS
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              FRONTEND (Nginx - Port 8080)                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Static HTML │  │ styles.css   │  │ Reverse Proxy    │   │
│  │ (4 pages)   │  │ (RTL Dark)   │  │ /api/* → Backend │   │
│  └─────────────┘  └──────────────┘  └────────┬─────────┘   │
└───────────────────────────────────────────────┼─────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────┐
│              BACKEND (Flask/Gunicorn - Port 5000)            │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Auth API │  │ Recharge  │  │ Cards    │  │ Admin    │  │
│  │ (JWT)    │  │ Service   │  │ Service  │  │ Service  │  │
│  └──────────┘  └───────────┘  └──────────┘  └──────────┘  │
│  ┌──────────────────┐  ┌─────────────────────────────┐     │
│  │ /metrics         │  │ /api/health                 │     │
│  │ (prometheus)     │  │ (load balancer healthcheck) │     │
│  └──────────────────┘  └─────────────────────────────┘     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              POSTGRESQL 16 (Port 5432)                       │
│  ┌─────────┐  ┌──────────────┐  ┌─────────┐               │
│  │ users   │  │ transactions │  │ cards   │               │
│  └─────────┘  └──────────────┘  └─────────┘               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    MONITORING STACK                          │
│  ┌────────────┐   ┌─────────┐   ┌──────┐   ┌──────────┐  │
│  │ Prometheus │──▶│ Grafana │◀──│ Loki │◀──│ Promtail │  │
│  │ :9090      │   │ :3000   │   │:3100 │   │(docker   │  │
│  └────────────┘   └─────────┘   └──────┘   │ logs)    │  │
│       ▲                                      └──────────┘  │
│       │ scrape /metrics                                     │
│       └─────────── Backend :5000                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 ملاحظات إضافية

1. **أمان:** الـ Admin endpoints حالياً مفتوحة (مفيش JWT عليها) — ده design choice للـ demo، في production لازم يتحطّ عليها auth
2. **الرصيد الابتدائي:** كل مستخدم جديد بياخد 1000 جنيه رصيد تجريبي
3. **الكروت:** Serial numbers و PINs بيتولدوا randomly وقت الـ seed (16 و 14 رقم على التوالي)
4. **الـ HPA:** في Kubernetes، الـ backend بيعمل scale من 2 لـ 10 pods لو CPU > 70%
5. **الـ Healthcheck:** `/api/health` بيرجّع `healthy` لو الداتابيز شغالة، `degraded` لو لأ
6. **تسمية الـ images:** GHCR بيحتاج الـ owner يكون lowercase — ده اتحل في الـ CI

---

> 📌 **آخر commit:** `9f31f52` — fix: use Railway reference variable BACKEND_HOST via envsubst template
