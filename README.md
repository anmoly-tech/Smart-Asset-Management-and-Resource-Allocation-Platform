# 🏢 Smart Asset Management Hub

> An intuitive, role-based resource reservation and inventory optimization system. Automates equipment booking, controls rolling availability calendars, and manages global transactional history with dedicated **Admin** and **Standard User** experiences.

---

## 📋 Table of Contents

- [Features](#-features)
- [Demo Video](#-demo-video)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Local Setup & Installation](#-local-setup--installation)
- [Network Testing & Sharing](#-network-testing--sharing)
- [Logic Highlights](#-logic-highlights)
- [Security](#-security)

---

## ✨ Features

### 👤 Standard User Experience

- **Rolling Timeline Ledger** — The dashboard surfaces only active and recent reservations from the past 5 days, keeping the view focused and clutter-free.
- **Instant Notification Controls** — A real-time alert bell delivers reservation updates using persistent unread state (`is_read=False`). Includes a **"Clear Feed"** tool to dismiss all alerts at once.
- **Asset Discovery Registry** — Browse all available equipment, each item equipped with an interactive, base64-encoded **QR tracking badge** for quick identification.

### 🛠️ Administrator Workspace

- **Real-Time Request Alerts** — When a user submits a booking, the system instantly dispatches unread notifications to all active admins (`is_staff=True`).
- **Global Purge Administration** — A secure panel inside the Admin Workspace allows flushing of non-active, archived ledger rows (`Returned`, `Canceled`, `Rejected`) globally, keeping the database lean.
- **Ecosystem Analytics** — Visual dashboards powered by **Chart.js** track asset volume, active handouts, and upcoming reservations at a glance.
- **Security Guards** — All admin endpoints are protected via Django's `@user_passes_test` decorator.

---

## 🎥 Demo Video
Watch the video below to see the project in action:

[DEMO VIDEO](https://drive.google.com/file/d/1b3kehByEOfYeDF96MHScKfK_bMsNrGYl/view?usp=sharing)

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.9+, Django 4.2+ |
| Frontend | HTML, Tailwind CSS |
| Analytics | Chart.js |
| QR Badges | `qrcode`, `Pillow` |
| Database | SQLite3 (default) |

---

## 📁 Project Structure

```
ASSET_MANAGEMENT_HUB/
│
├── core/                        # Main application
│   ├── migrations/              # Database migration files
│   │   ├── __init__.py
│   │   ├── 0001_initial.py
│   │   ├── 0002_notification_...
│   │   └── 0003_maintenancel...
│   │
│   ├── templates/core/          # HTML templates
│   │   ├── admin_workflow.html
│   │   ├── book_asset.html
│   │   ├── dashboard.html
│   │   ├── history.html
│   │   ├── login.html
│   │   ├── notifications.html
│   │   ├── report_health.html
│   │   └── signup.html
│   │
│   ├── __init__.py
│   ├── admin.py                 # Django admin configurations
│   ├── apps.py
│   ├── models.py                # Core data models
│   ├── tests.py
│   └── views.py                 # Route handlers & business logic
│
├── main/                        # Django project config
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py              # Project settings
│   ├── urls.py                  # URL routing
│   └── wsgi.py
│
├── manage.py                    # Django management CLI
├── db.sqlite3                   # SQLite database
└── README.md
```

---

## 🚀 Local Setup & Installation

```bash
# ── 1. Clone the repository ──────────────────────────────────────────────────
git clone https://github.com/your-username/asset-platform.git


# ── 2. Create a virtual environment ──────────────────────────────────────────
# macOS / Linux:
python3 -m venv venv
# Windows:
python -m venv venv

# ── 3. Activate the virtual environment ──────────────────────────────────────
# macOS / Linux:
source venv/bin/activate
# Windows (Command Prompt):
venv\Scripts\activate
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# ── 4. Install dependencies ───────────────────────────────────────────────────
pip install --upgrade pip
pip install django qrcode pillow

# ── 5. Apply database migrations ─────────────────────────────────────────────
python manage.py makemigrations
python manage.py migrate

# ── 6. Create a superuser (admin account) ────────────────────────────────────
python manage.py createsuperuser

# ── 7. Start the development server ──────────────────────────────────────────
python manage.py runserver
```

Once running, open your browser and navigate to:

```
http://127.0.0.1:8000/
```

The Django admin panel is available at:

```
http://127.0.0.1:8000/admin/
```

---

## 🌐 Network Testing & Sharing

### Local Wi-Fi (LAN)

To let others on the same network test the app, find your machine's local IP address and run:

```bash
python manage.py runserver 192.168.X.X:8000
```

> ⚠️ You must also update `ALLOWED_HOSTS` in `main/settings.py` to allow connections:
> ```python
> ALLOWED_HOSTS = ['*']
> ```

Other devices on the same Wi-Fi can then access the app at `http://192.168.X.X:8000`.

### Remote Access via Ngrok

For testing outside your local network, use [Ngrok](https://ngrok.com/) to create a secure public tunnel:

```bash
# In a separate terminal, with the Django server already running:
ngrok http 8000
```

Ngrok will generate a public HTTPS URL (e.g., `https://abc123.ngrok.io`) that anyone on the internet can use to access your local server.

---

## ⚙️ Logic Highlights

**Temporal Constraints**
The dashboard filters user reservations using a dynamic 5-day delta window to avoid view bloat:
```python
from datetime import timedelta
from django.utils import timezone

cutoff = timezone.now() - timedelta(days=5)
reservations = Reservation.objects.filter(user=request.user, created_at__gte=cutoff)
```

**Inventory Balance Protection**
The history clean-up routine deliberately preserves `Approved` and active-status rows so that inventory counts always reflect physical allocations accurately. Only terminal states (`Returned`, `Canceled`, `Rejected`) are eligible for purge.

**UI Safety for Destructive Actions**
All irreversible database actions require inline browser confirmation before executing:
```html
<button onclick="return confirm('Are you sure? This action cannot be undone.')">
  Purge Archive
</button>
```

---

## 🔒 Security

- Admin-only views are gated with Django's `@user_passes_test` decorator, redirecting unauthorized users.
- Staff status (`is_staff=True`) is required to receive admin-level booking notifications.
- No destructive action is exposed without explicit user confirmation.

---

## 📄 License

This project is for educational and portfolio use. Feel free to fork and adapt it for your own needs.