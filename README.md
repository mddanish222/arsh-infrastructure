# 🏗️ Arsh Infrastructure — Project Tracker & Client Portal

A full-stack construction-project tracking website built for **Arsh Infrastructure Pvt. Ltd.** Clients can look up live updates on their construction project using just their project name and phone number, while admins manage everything — updates, photos, and incoming leads — from a protected dashboard.

---

## ✨ Key Features

### 🌐 Public Site
- Marketing pages (Home / About / Contact) with an image slider and services showcase
- **Project Update Lookup** — clients search their project's progress by **project name + phone number**, with an optional date-range filter
- **Contact / lead-capture form** that routes enquiries straight into the admin dashboard
- Installable **PWA** (manifest + Service Worker) with offline fallback and cache-first static assets

### 🛠️ Admin Dashboard
- Token-based admin authentication using `itsdangerous` signed, **time-expiring tokens (24h)** — no session storage needed
- **Obscured admin entry point**: the login route is only reachable via a custom, non-guessable redirect path (`netlify.toml` rewrite), keeping the login page off the public nav
- Post, edit, bulk-select, and delete project updates, each with multi-image upload
- Dedicated **Contact Requests** inbox — view, and bulk-delete leads submitted through the public contact form; quick "email this lead" action
- Client-side lightbox for viewing uploaded project photos at full size

### ☁️ Backend & Storage
- **Flask REST API** with clean separation between public endpoints (`/api/search`, `/api/contact-submit`) and admin-only endpoints (guarded by a `@login_required` decorator)
- **PostgreSQL** (via `psycopg2`) for structured data (updates, contact requests)
- **Supabase Storage** for image uploads, generating public URLs for each project photo
- CORS configured for cross-origin calls between the Netlify-hosted frontend and Render-hosted API

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Gunicorn |
| Database | PostgreSQL (psycopg2) |
| File Storage | Supabase Storage |
| Auth | itsdangerous (signed, expiring tokens) |
| Frontend | HTML5, vanilla JS, custom CSS |
| Hosting | Netlify (frontend, static) + Render (Flask API) |
| Offline / Installable | Service Worker, Web App Manifest |

---

## 🧩 Architecture Overview

```
frontend/
 ├── index.html              → Public search / lookup
 ├── about.html                → Company info + project gallery slider
 ├── contact.html                → Lead-capture form
 ├── login.html                    → Hidden admin login (token auth)
 ├── admin.html                      → Post / manage project updates
 ├── edit.html                         → Edit a specific update
 ├── contact-requests.html               → Admin inbox for leads
 ├── config.js                             → Auto-switches API base URL (local vs prod)
 ├── script.js / style.css                   → Shared frontend logic & design
 └── sw.js / manifest.json                     → PWA support

app.py           → Flask app: routes, auth decorator, DB + Supabase Storage helpers
requirements.txt → Python dependencies
render.yaml      → Render deployment config (API)
netlify.toml     → Netlify deployment + hidden-admin-route redirect
```

### Core Flow
1. **Client lookup**: visitor enters project name + phone on `index.html` → `/api/search` queries Postgres and returns matching updates (with optional date filtering)
2. **Lead capture**: visitor submits `contact.html` → stored in `contact_requests` table, visible to admin
3. **Admin login**: admin navigates to the obscured redirect path → `login.html` → `/api/login` verifies password and issues a signed, time-limited token stored in `localStorage`
4. **Admin actions**: create/edit/delete updates (with image upload to Supabase Storage) and manage incoming contact requests, all behind `@login_required`

---


