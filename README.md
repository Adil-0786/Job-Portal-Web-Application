# 🏢 TalentBridge — Job Portal Web Application

A full-stack **Flask** web application that connects job seekers with employers. Features secure authentication, role-based dashboards, job search & filtering, and application tracking — all in a modern, responsive UI.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=flat-square&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## ✨ Features

| Feature | Description |
|---|---|
| **🔐 Authentication** | Secure local login + Google OAuth 2.0 support |
| **👥 Role-Based Access** | Separate dashboards for Seekers, Employers, and Admins |
| **📋 Job Listings** | Post, edit, and manage jobs with rich detail fields |
| **🔍 Search & Filter** | Filter jobs by keyword, location, category, company, and type |
| **📝 Application Tracking** | Seekers track status; employers review & manage applications |
| **📊 Admin Dashboard** | Platform-wide stats, user management, and job moderation |
| **🌱 Sample Data** | Auto-seeds demo users, companies, and job listings |
| **📱 Responsive Design** | Optimized for desktop and mobile devices |

---

## 🛠️ Tech Stack

- **Backend:** Python 3.10+, Flask 3.x, Gunicorn
- **Database:** SQLite (zero-config, file-based)
- **Auth:** Werkzeug password hashing + Authlib (Google OAuth)
- **Templates:** Jinja2 with Bootstrap-based CSS
- **Deployment:** Render (via `render.yaml`)

---

## 📂 Project Structure

```
Job-Portal-Web-Application/
├── app.py                  # Application entry point
├── jobboard/
│   ├── __init__.py         # Flask app factory
│   ├── views.py            # Routes & controllers
│   ├── db.py               # Database helpers & seeding
│   ├── oauth.py            # Google OAuth integration
│   └── schema.sql          # Database schema
├── templates/              # Jinja2 HTML templates (14 pages)
├── static/css/             # Stylesheets
├── tests/
│   └── test_app.py         # Test suite
├── .env.example            # Environment variables template
├── requirements.txt        # Python dependencies
├── render.yaml             # Render deployment config
├── Procfile                # Heroku/Render process file
└── README.md
```

---

## ⚙️ Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/Adil-0786/Job-Portal-Web-Application.git
cd Job-Portal-Web-Application
```

### 2. Create a virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up environment
```bash
cp .env.example .env
# Edit .env to customize settings (optional — defaults work out of the box)
```

### 5. Run the application
```bash
python app.py
```

The app starts at **http://localhost:5000** with sample data auto-seeded.

---

## 🔑 Default Accounts

| Role | Email | Password |
|---|---|---|
| **Admin** | `admin@gmail.com` | `Admin123!` |
| **Employer** | `employer@talentbridge.local` | `Employer123!` |
| **Job Seeker** | `seeker@talentbridge.local` | `Seeker123!` |

---

## 🌐 Deployment

### Deploy to Render (one-click)
This repo includes a `render.yaml` — just connect your GitHub repo to [Render](https://render.com) and it auto-deploys.

### Environment Variables
| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Flask secret key |
| `ADMIN_EMAIL` | `admin@talentbridge.local` | Admin login email |
| `ADMIN_PASSWORD` | `Admin123!` | Admin login password |
| `DATA_DIR` | `instance` | Database file location |
| `ALLOW_LOCAL_LOGIN` | `true` | Enable email/password login |
| `SEED_SAMPLE_DATA` | `true` | Auto-seed demo data |

---

## 🧪 Running Tests
```bash
python -m pytest tests/
```

---

## 📄 License

MIT License — feel free to use, modify, and distribute.

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/Adil-0786">Adil</a>
</p>
