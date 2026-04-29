import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
import secrets

from flask import Flask, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
MODEL_CACHE = {"name": None}
LOGIN_USERNAME = os.environ.get("APP_LOGIN_USERNAME", "admin")
LOGIN_PASSWORD = os.environ.get("APP_LOGIN_PASSWORD", "admin123")
USERS = {LOGIN_USERNAME: LOGIN_PASSWORD}
REGISTERED_EMAILS = {}
REGISTERED_NAMES = {}
USER_STORE_PATH = os.path.join(os.path.dirname(__file__), "users.json")
DRAFT_STORE_PATH = os.path.join(os.path.dirname(__file__), "drafts.json")
DRAFTS = {}
IELTS_DRAFT_STORE_PATH = os.path.join(os.path.dirname(__file__), "ielts_drafts.json")
IELTS_DRAFTS = {}
UNIVERSITIES_DB_PATH = os.path.join(os.path.dirname(__file__), "universities.db")


def get_all_countries():
    """Get list of all countries with universities in the database."""
    try:
        conn = sqlite3.connect(UNIVERSITIES_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT country FROM universities ORDER BY country")
        countries = [row[0] for row in cursor.fetchall()]
        conn.close()
        return countries
    except sqlite3.OperationalError:
        return []


def get_universities_by_country(country):
    """Get all universities from a specific country, ordered by QS ranking."""
    try:
        conn = sqlite3.connect(UNIVERSITIES_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM universities WHERE country = ? ORDER BY qs_ranking",
            (country,),
        )
        universities = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return universities
    except sqlite3.OperationalError:
        return []


def load_user_store():
    if not os.path.exists(USER_STORE_PATH):
        return
    try:
        with open(USER_STORE_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return

    users = data.get("users", {})
    emails = data.get("emails", {})
    names = data.get("names", {})
    if isinstance(users, dict):
        USERS.update({str(k): str(v) for k, v in users.items() if k and v})
    if isinstance(emails, dict):
        REGISTERED_EMAILS.update({str(k): str(v) for k, v in emails.items() if k and v})
    if isinstance(names, dict):
        REGISTERED_NAMES.update({str(k): str(v) for k, v in names.items() if k})


def save_user_store():
    payload = {
        "users": USERS,
        "emails": REGISTERED_EMAILS,
        "names": REGISTERED_NAMES,
    }
    with open(USER_STORE_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


load_user_store()


def load_drafts():
    if not os.path.exists(DRAFT_STORE_PATH):
        return
    try:
        with open(DRAFT_STORE_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(data, dict):
        for username, drafts in data.items():
            if isinstance(drafts, list):
                cleaned = []
                for draft in drafts:
                    if isinstance(draft, dict):
                        title = str(draft.get("title", "")).strip()
                        essay = str(draft.get("essay", "")).strip()
                        essay_type = str(draft.get("essay_type", "personal_statement")).strip() or "personal_statement"
                        if essay_type not in {"personal_statement", "motivational_essay"}:
                            essay_type = "personal_statement"
                        if title or essay:
                            cleaned.append({"title": title, "essay": essay, "essay_type": essay_type})
                DRAFTS[str(username)] = cleaned


def save_drafts():
    with open(DRAFT_STORE_PATH, "w", encoding="utf-8") as file:
        json.dump(DRAFTS, file, indent=2)


load_drafts()


def load_ielts_drafts():
    if not os.path.exists(IELTS_DRAFT_STORE_PATH):
        return
    try:
        with open(IELTS_DRAFT_STORE_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(data, dict):
        for username, drafts in data.items():
            if isinstance(drafts, list):
                cleaned = []
                for draft in drafts:
                    if isinstance(draft, dict):
                        title = str(draft.get("title", "")).strip()
                        response = str(draft.get("response", "")).strip()
                        if title or response:
                            cleaned.append({"title": title, "response": response})
                IELTS_DRAFTS[str(username)] = cleaned


def save_ielts_drafts():
    with open(IELTS_DRAFT_STORE_PATH, "w", encoding="utf-8") as file:
        json.dump(IELTS_DRAFTS, file, indent=2)


load_ielts_drafts()


AUTH_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>UniFlow - Access</title>
    <style>
        :root {
            --bg: #f3f0ed;
            --panel: #fffdfb;
            --ink: #2a2a2a;
            --muted: #69615a;
            --accent: #b55b3e;
            --accent-2: #d98663;
            --line: #ece6e0;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Georgia, "Times New Roman", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 12% 8%, #fff7ef 0%, transparent 35%),
                radial-gradient(circle at 92% 14%, #f7ece4 0%, transparent 28%),
                linear-gradient(135deg, #f4f0eb 0%, #eee6dd 100%);
        }
        .shell {
            width: min(1100px, calc(100% - 44px));
            margin: 34px auto;
            border: 1px solid var(--line);
            border-radius: 22px;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(255, 250, 244, 0.94) 100%);
            box-shadow: 0 18px 50px rgba(62, 45, 34, 0.1);
            padding: 30px;
            backdrop-filter: blur(4px);
        }
        h1 { margin: 0 0 12px; font-size: clamp(2.1rem, 5vw, 3.4rem); }
        .lead {
            color: var(--muted);
            border-bottom: 1px solid var(--line);
            padding-bottom: 14px;
            margin-bottom: 18px;
            line-height: 1.6;
        }
        .grid {
            display: grid;
            grid-template-columns: 1.1fr 1fr;
            gap: 18px;
        }
        .card {
            border: 1px solid var(--line);
            border-radius: 16px;
            background: linear-gradient(180deg, #fff 0%, #fff8f2 100%);
            padding: 22px;
            box-shadow: 0 10px 22px rgba(70, 50, 38, 0.06);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
            position: relative;
            overflow: hidden;
        }
        .card::before {
            content: "";
            position: absolute;
            inset: 0 0 auto 0;
            height: 3px;
            background: linear-gradient(90deg, var(--accent), var(--accent-2));
            opacity: 0.5;
        }
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 14px 30px rgba(70, 50, 38, 0.12);
        }
        .card h2 { margin: 0 0 12px; font-size: 2rem; }
        .card h3 { margin: 0 0 10px; font-size: 2rem; }
        .info-list { margin: 0; padding-left: 20px; color: #3f3a35; line-height: 1.45; }
        .hint { margin-top: 14px; color: var(--muted); }
        .link-button { display: inline-block; margin-top: 8px; color: #2c2c2c; font-weight: 700; }
        .link-button:hover { color: #8f3f29; }
        .auth-switch { display: flex; gap: 8px; margin-bottom: 12px; }
        .switch-btn {
            border: 1px solid var(--line);
            background: #f9f4ef;
            color: #493d33;
            border-radius: 999px;
            padding: 7px 14px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.18s ease;
        }
        .switch-btn.active {
            background: linear-gradient(135deg, #bd6547 0%, #a34d32 100%);
            color: white;
            border-color: transparent;
        }
        label { font-weight: 700; display: block; margin-bottom: 5px; }
        input {
            width: 100%;
            border-radius: 12px;
            border: 1px solid #d7ccc2;
            padding: 10px 12px;
            font-family: Georgia, "Times New Roman", serif;
            font-size: 1.08rem;
            margin-bottom: 10px;
            background: #fff;
            transition: border-color 0.18s ease, box-shadow 0.18s ease;
        }
        input:focus {
            outline: none;
            border-color: #be6a4a;
            box-shadow: 0 0 0 3px rgba(181, 91, 62, 0.14);
        }
        .input-row {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 6px;
            align-items: start;
        }
        .tiny {
            border-radius: 999px;
            border: 1px solid #d8ccc1;
            background: #f6eee7;
            padding: 8px 10px;
            margin-top: 2px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.18s ease;
        }
        .tiny:hover { background: #efe1d5; }
        .primary {
            width: fit-content;
            border-radius: 999px;
            border: 0;
            padding: 10px 20px;
            font-weight: 700;
            color: #fff;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            box-shadow: 0 8px 18px rgba(159, 71, 47, 0.3);
            cursor: pointer;
            transition: transform 0.16s ease, box-shadow 0.16s ease;
        }
        .primary:hover { transform: translateY(-1px); box-shadow: 0 12px 24px rgba(159, 71, 47, 0.35); }
        .auth-form {
            opacity: 1;
            transform: translateY(0);
            transition: opacity 0.2s ease, transform 0.2s ease;
        }
        .hidden {
            display: none;
            opacity: 0;
            transform: translateY(5px);
        }
        .error { color: #8a2d2d; font-weight: 700; margin-bottom: 10px; }
        .success { color: #256c3f; font-weight: 700; margin-bottom: 10px; }
        .footer-note { margin-top: 14px; color: #6e675f; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <main class="shell">
        <h1>UniFlow</h1>
        <p class="lead">Create an account or log in to open your UniFlow dashboard for essays, goals, and application prep.</p>
        <section class="grid">
            <article class="card">
                <h3>What You Get</h3>
                <ul class="info-list">
                    <li>A UniFlow dashboard with tasks and objectives for your application journey</li>
                    <li>An essay checker with saved drafts and writing feedback</li>
                    <li>Region-based planning for future IELTS writing practice</li>
                </ul>
                <p class="hint">Already signed in? Jump straight into your UniFlow dashboard.</p>
                <a class="link-button" href="{{ url_for('mainpage') }}">Open Dashboard</a>
            </article>
            <article class="card">
                <div class="auth-switch">
                    <button type="button" class="switch-btn active" data-target="login-form">Log In</button>
                    <button type="button" class="switch-btn" data-target="register-form">Sign Up</button>
                </div>
                {% if error %}
                    <div class="error">{{ error }}</div>
                {% endif %}
                {% if success %}
                    <div class="success">{{ success }}</div>
                {% endif %}
                <form id="login-form" class="auth-form" method="post">
                    <input type="hidden" name="action" value="login">
                    <label for="login-username">Username</label>
                    <input id="login-username" name="username" value="{{ username }}" required>
                    <label for="login-password">Password</label>
                    <div class="input-row">
                        <input id="login-password" name="password" type="password" required>
                        <button class="tiny" type="button" data-toggle-password="login-password">Show</button>
                    </div>
                    <button class="primary" type="submit">Log In</button>
                </form>
                <form id="register-form" method="post" class="auth-form hidden">
                    <input type="hidden" name="action" value="register">
                    <label for="register-name">Name (optional)</label>
                    <input id="register-name" name="name" placeholder="Your name">
                    <label for="register-username">Username</label>
                    <input id="register-username" name="username" required>
                    <label for="register-email">Email</label>
                    <input id="register-email" name="email" type="email" required>
                    <label for="register-password">Password</label>
                    <div class="input-row">
                        <input id="register-password" name="password" type="password" required>
                        <button class="tiny" type="button" data-toggle-password="register-password">Show</button>
                    </div>
                    <button class="primary" type="submit">Create Account</button>
                </form>
            </article>
        </section>
        <p class="footer-note">{{ message }}</p>
    </main>
    <script>
        const switchButtons = document.querySelectorAll('.switch-btn');
        const forms = {
            'login-form': document.getElementById('login-form'),
            'register-form': document.getElementById('register-form')
        };

        switchButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                switchButtons.forEach((item) => item.classList.remove('active'));
                btn.classList.add('active');
                const target = btn.dataset.target;
                Object.entries(forms).forEach(([id, form]) => {
                    form.classList.toggle('hidden', id !== target);
                });
            });
        });

        document.querySelectorAll('[data-toggle-password]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const input = document.getElementById(btn.dataset.togglePassword);
                const show = input.type === 'password';
                input.type = show ? 'text' : 'password';
                btn.textContent = show ? 'Hide' : 'Show';
            });
        });
    </script>
</body>
</html>
"""


DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>UniFlow Dashboard</title>
    <style>
        :root {
            --bg: #f3f0ed;
            --panel: #fffdfb;
            --ink: #2a2a2a;
            --muted: #6b645c;
            --accent: #b55b3e;
            --accent-2: #d98663;
            --line: #ece6e0;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Georgia, "Times New Roman", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 8% 8%, #fff8f1 0%, transparent 38%),
                linear-gradient(135deg, #f4f0eb 0%, #eee6dd 100%);
        }
        .wrap { width: min(1100px, calc(100% - 44px)); margin: 30px auto; }
        .panel {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 26px;
            box-shadow: 0 18px 45px rgba(62, 45, 34, 0.1);
            position: relative;
            overflow: hidden;
        }
        .panel::after {
            content: "";
            position: absolute;
            top: -120px;
            right: -120px;
            width: 260px;
            height: 260px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(217, 134, 99, 0.25) 0%, transparent 70%);
            pointer-events: none;
        }
        .top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
        h1 { margin: 0; font-size: clamp(2.1rem, 6vw, 3.2rem); }
        .sub { margin: 8px 0 0; color: var(--muted); }
        .links { display: flex; gap: 14px; align-items: center; position: relative; }
        .links a { color: #2e2a26; font-weight: 700; text-decoration: none; transition: color 0.16s ease; }
        .links a:hover { color: #9f472f; }
        .nav-btn {
            border: 1px solid #c9b3a4;
            border-radius: 999px;
            padding: 8px 14px;
            background: #fff;
            box-shadow: 0 4px 10px rgba(62, 45, 34, 0.08);
        }
        .badge {
            width: 48px;
            height: 48px;
            border-radius: 999px;
            border: 1px solid #cfb8aa;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            color: #fff;
            font-weight: 700;
            font-size: 1.15rem;
            display: grid;
            place-items: center;
            cursor: pointer;
        }
        .profile-menu {
            position: absolute;
            top: calc(100% + 8px);
            right: 0;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 12px;
            min-width: 170px;
            box-shadow: 0 10px 24px rgba(62, 45, 34, 0.18);
            padding: 8px;
            display: none;
            z-index: 5;
        }
        .profile-menu.show { display: block; }
        .menu-item {
            width: 100%;
            border: 0;
            background: transparent;
            text-align: left;
            padding: 8px 10px;
            border-radius: 8px;
            cursor: pointer;
            font: inherit;
            color: #2e2a26;
            text-decoration: none;
            display: block;
        }
        .menu-item:hover { background: #f7eee7; }
        .grid { margin-top: 16px; display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
        .progress-wrap {
            margin-top: 14px;
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #fff8f2;
            padding: 12px;
        }
        .progress-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
            color: var(--muted);
            font-weight: 700;
        }
        .progress-track {
            width: 100%;
            height: 12px;
            border-radius: 999px;
            background: #eadfd4;
            overflow: hidden;
        }
        .progress-fill {
            width: 0%;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #bd6547 0%, #d98663 100%);
            transition: width 0.2s ease;
        }
        .card {
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 18px;
            background: linear-gradient(180deg, #fff 0%, #fff8f2 100%);
            box-shadow: 0 8px 22px rgba(70, 50, 38, 0.06);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }
        .card:hover { transform: translateY(-2px); box-shadow: 0 12px 26px rgba(70, 50, 38, 0.12); }
        h2 { margin-top: 0; }
        .row { margin: 10px 0; }
        label { display: block; font-weight: 700; margin-bottom: 6px; }
        select { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid #d8cec4; font: inherit; }
        .btn {
            border: 0;
            border-radius: 999px;
            padding: 10px 18px;
            font-weight: 700;
            color: #fff;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            box-shadow: 0 8px 18px rgba(159, 71, 47, 0.28);
            cursor: pointer;
            margin-top: 8px;
            transition: transform 0.16s ease, box-shadow 0.16s ease;
        }
        .btn:hover { transform: translateY(-1px); box-shadow: 0 12px 24px rgba(159, 71, 47, 0.34); }
        .btn[disabled] {
            opacity: 0.55;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }
        .muted { color: var(--muted); }
        .checklist {
            list-style: none;
            padding: 0;
            margin: 12px 0 0;
            display: grid;
            gap: 8px;
        }
        .check-item {
            border: 1px solid #e2d3c7;
            border-radius: 10px;
            padding: 8px 10px;
            background: #fff;
            color: #5c524a;
            font-weight: 700;
        }
        .check-item.done {
            border-color: #90bf9c;
            background: #edf7ef;
            color: #27583a;
        }
        .snapshot-list {
            display: grid;
            gap: 12px;
            margin-top: 10px;
        }
        .snapshot-outline {
            border: 1px solid #c9b3a4;
            border-radius: 999px;
            padding: 12px 16px;
            background: #fff;
            box-shadow: 0 4px 10px rgba(62, 45, 34, 0.08);
        }
        .snapshot-outline strong {
            display: block;
            margin-bottom: 3px;
        }
        .settings-msg { color: #256c3f; font-weight: 700; margin: 8px 0 0; }
        .modal-backdrop {
            position: fixed;
            inset: 0;
            background: rgba(16, 10, 8, 0.4);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 30;
            padding: 18px;
        }
        .modal-backdrop.show { display: flex; }
        .modal-card {
            width: min(520px, 100%);
            border-radius: 16px;
            background: #fff;
            border: 1px solid var(--line);
            box-shadow: 0 20px 50px rgba(30, 20, 14, 0.25);
            padding: 20px;
        }
        .modal-row { margin-bottom: 10px; }
        .modal-row input {
            width: 100%;
            border: 1px solid #d8cec4;
            border-radius: 10px;
            padding: 10px;
            font: inherit;
        }
        .switch {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 12px 0 16px;
        }
        .switch input { width: auto; }
        [data-theme="dark"] body {
            --bg: #181513;
            --panel: #211d1a;
            --ink: #f2ece8;
            --muted: #c6b9b0;
            --line: #3f342e;
            background: linear-gradient(135deg, #151210 0%, #1f1a17 100%);
        }
        [data-theme="dark"] .panel,
        [data-theme="dark"] .card,
        [data-theme="dark"] .modal-card,
        [data-theme="dark"] .profile-menu { background: #231e1b; color: var(--ink); }
        [data-theme="dark"] .snapshot-outline { background: #2c2521; border-color: #4a3d36; box-shadow: 0 4px 10px rgba(10, 8, 7, 0.22); }
        [data-theme="dark"] .links a,
        [data-theme="dark"] .menu-item { color: #f2ece8; }
        [data-theme="dark"] select,
        [data-theme="dark"] .modal-row input { background: #2c2521; color: #f2ece8; border-color: #4a3d36; }
        .fade-card { opacity: 0; transform: translateY(8px); }
        .fade-card.show { opacity: 1; transform: translateY(0); transition: opacity 0.28s ease, transform 0.28s ease; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <main class="wrap">
        <section class="panel">
            <div class="top">
                <div>
                    <h1>UniFlow</h1>
                    <p class="sub">Your application workspace for university goals, writing prep, and daily tasks.</p>
                </div>
                <nav class="links">
                    <a class="nav-btn" href="{{ url_for('mainpage') }}">Main Page</a>
                    <button type="button" id="profile-badge" class="badge">{{ badge_initial }}</button>
                    <div id="profile-menu" class="profile-menu">
                        <button type="button" id="open-settings" class="menu-item">Settings</button>
                        <a class="menu-item" href="{{ url_for('logout') }}">Log Out</a>
                    </div>
                </nav>
            </div>
            <section class="progress-wrap">
                <div class="progress-meta">
                    <span>Task Progress</span>
                    <span id="task-count">0/3 tasks completed</span>
                </div>
                <div class="progress-track">
                    <div id="task-progress-fill" class="progress-fill"></div>
                </div>
            </section>
            {% if settings_message %}
                <p class="settings-msg">{{ settings_message }}</p>
            {% endif %}
            <div class="grid">
                <article class="card fade-card">
                    <h2>Tasks & Objectives</h2>
                    <div class="row">
                        <label for="region">Choose your application region</label>
                        <select id="region">
                            <option value="none">Select region</option>
                            <option value="usa">USA</option>
                            <option value="uk">United Kingdom</option>
                            <option value="canada">Canada</option>
                            <option value="china">China</option>
                            <option value="europe">Europe</option>
                        </select>
                    </div>
                    <div style="display: flex; gap: 10px; margin-top: 8px;">
                        <button id="save-region" class="btn" type="button">Save Region</button>
                        <button id="view-universities" class="btn" type="button">View Universities</button>
                    </div>
                    <p id="region-status" class="muted"></p>
                    <hr>
                    <p><strong>Essay Tracker:</strong> Save drafts and review score trends.</p>
                    <a href="{{ url_for('essay_checker') }}"><button class="btn" type="button">Open Essay Checker</button></a>
                    <p><strong>IELTS Writing Section:</strong> Practice prompt planning by target region.</p>
                    {% if ielts_locked %}
                        <button class="btn" type="button" disabled>Finish Essay First</button>
                        <p class="muted">Complete at least one essay draft to unlock IELTS practice.</p>
                    {% else %}
                        <a href="{{ url_for('ielts_practice') }}"><button class="btn" type="button">Open IELTS Practice</button></a>
                    {% endif %}
                    <ul class="checklist">
                        <li class="check-item {% if essay_done %}done{% endif %}">
                            {% if essay_done %}✓{% else %}○{% endif %} Essay task completed
                        </li>
                        <li class="check-item {% if ielts_done %}done{% endif %}">
                            {% if ielts_done %}✓{% else %}○{% endif %} IELTS task completed
                        </li>
                    </ul>
                </article>
                <article class="card fade-card">
                    <h2>Progress Snapshot</h2>
                    <div class="snapshot-list">
                        <div class="snapshot-outline">
                            <strong>Brand</strong>
                            UniFlow is now live in your workspace.
                        </div>
                        <div class="snapshot-outline">
                            <strong>Saved essay drafts</strong>
                            {{ drafts_count }} draft{{ '' if drafts_count == 1 else 's' }} currently saved.
                        </div>
                        <div class="snapshot-outline">
                            <strong>Application target</strong>
                            <span id="target-preview">{{ saved_region }}</span>
                        </div>
                    </div>
                </article>
            </div>
        </section>
    </main>
    <div id="settings-modal" class="modal-backdrop">
        <div class="modal-card">
            <h3>Settings</h3>
            <form method="post" action="{{ url_for('settings') }}">
                <div class="modal-row">
                    <label for="settings-name">Name</label>
                    <input id="settings-name" name="name" value="{{ display_name }}" placeholder="Your name">
                </div>
                <div class="modal-row">
                    <label for="settings-email">Email</label>
                    <input id="settings-email" name="email" value="{{ email }}" type="email" required>
                </div>
                <div class="modal-row">
                    <label for="settings-current-password">Current Password</label>
                    <input id="settings-current-password" name="current_password" type="password" placeholder="Required only to change password">
                </div>
                <div class="modal-row">
                    <label for="settings-new-password">New Password</label>
                    <input id="settings-new-password" name="new_password" type="password" placeholder="Leave empty to keep current">
                </div>
                <label class="switch"><input id="theme-toggle" type="checkbox"> Use dark theme</label>
                <button class="btn" type="submit">Save Settings</button>
                <button class="btn" id="close-settings" type="button">Close</button>
            </form>
        </div>
    </div>
    <script>
        const THEME_KEY = 'uniflow_theme';
        const setTheme = (theme) => {
            if (theme === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
            } else {
                document.documentElement.removeAttribute('data-theme');
            }
        };
        setTheme(localStorage.getItem(THEME_KEY) || 'light');

        const profileBadge = document.getElementById('profile-badge');
        const profileMenu = document.getElementById('profile-menu');
        profileBadge.addEventListener('click', () => profileMenu.classList.toggle('show'));
        document.addEventListener('click', (event) => {
            if (!profileMenu.contains(event.target) && event.target !== profileBadge) {
                profileMenu.classList.remove('show');
            }
        });

        const settingsModal = document.getElementById('settings-modal');
        document.getElementById('open-settings').addEventListener('click', () => {
            settingsModal.classList.add('show');
            profileMenu.classList.remove('show');
        });
        document.getElementById('close-settings').addEventListener('click', () => settingsModal.classList.remove('show'));
        settingsModal.addEventListener('click', (event) => {
            if (event.target === settingsModal) settingsModal.classList.remove('show');
        });

        const themeToggle = document.getElementById('theme-toggle');
        themeToggle.checked = (localStorage.getItem(THEME_KEY) || 'light') === 'dark';
        themeToggle.addEventListener('change', () => {
            const theme = themeToggle.checked ? 'dark' : 'light';
            localStorage.setItem(THEME_KEY, theme);
            setTheme(theme);
        });

        const regionSelect = document.getElementById('region');
        const status = document.getElementById('region-status');
        const preview = document.getElementById('target-preview');
        const key = 'uniflow_region';

        const prettify = (value) => {
            const map = { usa: 'USA', uk: 'United Kingdom', canada: 'Canada', china: 'China', europe: 'Europe', none: 'Not set yet' };
            return map[value] || 'Not set yet';
        };

        const saved = localStorage.getItem(key) || 'none';
        regionSelect.value = saved;
        preview.textContent = prettify(saved);

        document.getElementById('save-region').addEventListener('click', () => {
            localStorage.setItem(key, regionSelect.value);
            preview.textContent = prettify(regionSelect.value);
            status.textContent = 'Application destination updated.';
        });

        document.getElementById('view-universities').addEventListener('click', () => {
            const selected = regionSelect.value;
            if (selected === 'none') {
                status.textContent = 'Please select a region first.';
                return;
            }
            const regionMap = { usa: 'USA', uk: 'UK', canada: 'Canada', china: 'China', europe: 'Europe' };
            const countryName = regionMap[selected];
            const encoded = encodeURIComponent(countryName);
            window.location.href = '{{ universities_url }}?country=' + encoded;
        });

        const TASK_KEY = 'uniflow_task_checks';
        const taskCountText = document.getElementById('task-count');
        const taskFill = document.getElementById('task-progress-fill');
        const taskChecks = JSON.parse(localStorage.getItem(TASK_KEY) || '{"region":false,"essay":false,"ielts":false}');

        const syncTaskProgress = () => {
            const done = Number(taskChecks.region) + Number(taskChecks.essay) + Number(taskChecks.ielts);
            const total = 3;
            const pct = Math.round((done / total) * 100);
            taskCountText.textContent = `${done}/${total} tasks completed`;
            taskFill.style.width = `${pct}%`;
        };

        if (regionSelect.value !== 'none') taskChecks.region = true;
        taskChecks.essay = {{ 1 if drafts_count > 0 else 0 }} === 1;
        taskChecks.ielts = {{ 1 if ielts_drafts_count > 0 else 0 }} === 1;
        localStorage.setItem(TASK_KEY, JSON.stringify(taskChecks));
        syncTaskProgress();

        document.querySelectorAll('.fade-card').forEach((card, index) => {
            setTimeout(() => card.classList.add('show'), 80 + (index * 90));
        });
    </script>
</body>
</html>
"""


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>UniFlow Essay Checker</title>
    <style>
        :root {
            --bg: #f3f0ed;
            --panel: #fffdfb;
            --ink: #2a2a2a;
            --muted: #6b645c;
            --accent: #b55b3e;
            --accent-2: #d98663;
            --line: #ece6e0;
            --good: #256c3f;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Georgia, "Times New Roman", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 5%, #fff8f1 0%, transparent 35%),
                linear-gradient(135deg, #f4f0eb 0%, #eee6dd 100%);
        }
        .page { width: min(960px, calc(100% - 32px)); margin: 28px auto; }
        .hero, .results {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: 0 16px 40px rgba(62, 45, 34, 0.1);
        }
        .hero { padding: 28px; }
        .topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
        .links { display: flex; gap: 14px; align-items: center; position: relative; }
        .links a { color: #2e2a26; text-decoration: none; font-weight: 700; transition: color 0.16s ease; }
        .links a:hover { color: #9f472f; }
        .nav-btn {
            border: 1px solid #c9b3a4;
            border-radius: 999px;
            padding: 8px 14px;
            background: #fff;
            box-shadow: 0 4px 10px rgba(62, 45, 34, 0.08);
        }
        .nav-btn {
            border: 1px solid #c9b3a4;
            border-radius: 999px;
            padding: 8px 14px;
            background: #fff;
            box-shadow: 0 4px 10px rgba(62, 45, 34, 0.08);
        }
        .badge {
            width: 48px;
            height: 48px;
            border-radius: 999px;
            border: 1px solid #cfb8aa;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            color: #fff;
            font-weight: 700;
            font-size: 1.15rem;
            display: grid;
            place-items: center;
            cursor: pointer;
        }
        .profile-menu {
            position: absolute;
            top: calc(100% + 8px);
            right: 0;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 12px;
            min-width: 170px;
            box-shadow: 0 10px 24px rgba(62, 45, 34, 0.18);
            padding: 8px;
            display: none;
            z-index: 5;
        }
        .profile-menu.show { display: block; }
        .menu-item {
            width: 100%;
            border: 0;
            background: transparent;
            text-align: left;
            padding: 8px 10px;
            border-radius: 8px;
            cursor: pointer;
            font: inherit;
            color: #2e2a26;
            text-decoration: none;
            display: block;
        }
        .menu-item:hover { background: #f7eee7; }
        h1 { font-size: clamp(2rem, 5vw, 3.2rem); margin: 0; }
        p { line-height: 1.6; }
        .lead { max-width: 760px; color: var(--muted); margin-bottom: 18px; }
        form { display: grid; gap: 12px; }
        .checker-layout {
            display: grid;
            grid-template-columns: 270px 1fr;
            gap: 14px;
            align-items: start;
        }
        .draft-sidebar {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #fff9f4;
            padding: 12px;
            position: sticky;
            top: 14px;
        }
        .draft-list {
            display: grid;
            gap: 8px;
            margin-top: 8px;
            max-height: 420px;
            overflow: auto;
        }
        .session-chip {
            border: 1px dashed #cdb8a8;
            border-radius: 10px;
            padding: 8px 10px;
            background: #fff7f0;
            color: #6a5a50;
            font-weight: 700;
        }
        .draft-entry {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 6px;
            align-items: center;
        }
        .draft-item {
            width: 100%;
            border: 1px solid #e3d5c9;
            background: #fff;
            color: #3a332d;
            border-radius: 10px;
            text-align: left;
            padding: 9px 10px;
            box-shadow: none;
        }
        .draft-delete {
            width: auto;
            border: 1px solid #ddb9b0;
            background: #fff1ef;
            color: #8a2d2d;
            border-radius: 10px;
            padding: 8px 10px;
            box-shadow: none;
            font-size: 0.92rem;
        }
        .draft-delete:hover {
            transform: none;
            box-shadow: none;
            background: #ffdedd;
        }
        .draft-item.active {
            border-color: #be6a4a;
            background: #fff1e7;
        }
        .draft-empty {
            color: #6a6159;
            margin: 8px 0 0;
        }
        .editor-panel {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #fff;
            padding: 12px;
        }
        .type-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }
        .type-card {
            border: 1px solid #dfd0c3;
            border-radius: 14px;
            padding: 12px;
            background: #fffaf6;
            line-height: 1.5;
        }
        .type-card input {
            width: auto;
            margin-right: 8px;
        }
        .type-card strong {
            display: inline-block;
            margin-bottom: 4px;
        }
        .section-label {
            margin: 4px 0 0;
            color: #534a43;
            font-weight: 700;
            font-size: 1.02rem;
        }
        input, textarea {
            width: 100%;
            border-radius: 12px;
            border: 1px solid #d8cec4;
            padding: 12px;
            font: inherit;
            background: #fff;
            transition: border-color 0.18s ease, box-shadow 0.18s ease;
        }
        input:focus, textarea:focus {
            outline: none;
            border-color: #be6a4a;
            box-shadow: 0 0 0 3px rgba(181, 91, 62, 0.14);
        }
        textarea { min-height: 260px; resize: vertical; }
        button {
            width: fit-content;
            border: 0;
            border-radius: 999px;
            padding: 10px 20px;
            font-size: 1rem;
            font-weight: 700;
            color: #fff;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            box-shadow: 0 8px 18px rgba(159, 71, 47, 0.28);
            cursor: pointer;
            transition: transform 0.16s ease, box-shadow 0.16s ease;
        }
        button:hover { transform: translateY(-1px); box-shadow: 0 12px 24px rgba(159, 71, 47, 0.34); }
        .results { margin-top: 20px; padding: 22px 24px; }
        .score { display: inline-flex; gap: 10px; font-size: 1.1rem; font-weight: 700; color: var(--good); background: #edf7ef; border-radius: 999px; padding: 8px 14px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin: 16px 0 18px; }
        .card { padding: 12px; background: #fff; border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 5px 14px rgba(70, 50, 38, 0.06); }
        .label { display: block; font-size: 0.9rem; color: var(--muted); margin-bottom: 4px; }
        ul { padding-left: 20px; line-height: 1.6; }
        .empty { color: #8a2d2d; font-weight: 700; }
        .settings-msg { color: #256c3f; font-weight: 700; margin: 8px 0 0; }
        .modal-backdrop {
            position: fixed;
            inset: 0;
            background: rgba(16, 10, 8, 0.4);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 30;
            padding: 18px;
        }
        .modal-backdrop.show { display: flex; }
        .modal-card {
            width: min(520px, 100%);
            border-radius: 16px;
            background: #fff;
            border: 1px solid var(--line);
            box-shadow: 0 20px 50px rgba(30, 20, 14, 0.25);
            padding: 20px;
        }
        .modal-row { margin-bottom: 10px; }
        .modal-row input {
            width: 100%;
            border: 1px solid #d8cec4;
            border-radius: 10px;
            padding: 10px;
            font: inherit;
        }
        .switch {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 12px 0 16px;
        }
        .switch input { width: auto; }
        [data-theme="dark"] body {
            --bg: #181513;
            --panel: #211d1a;
            --ink: #f2ece8;
            --muted: #c6b9b0;
            --line: #3f342e;
            background: linear-gradient(135deg, #151210 0%, #1f1a17 100%);
        }
        [data-theme="dark"] .hero,
        [data-theme="dark"] .results,
        [data-theme="dark"] .card,
        [data-theme="dark"] .modal-card,
        [data-theme="dark"] .profile-menu { background: #231e1b; color: var(--ink); }
        [data-theme="dark"] .links a,
        [data-theme="dark"] .menu-item { color: #f2ece8; }
        [data-theme="dark"] input,
        [data-theme="dark"] textarea,
        [data-theme="dark"] .modal-row input { background: #2c2521; color: #f2ece8; border-color: #4a3d36; }
        [data-theme="dark"] .draft-sidebar,
        [data-theme="dark"] .editor-panel { background: #231e1b; }
        [data-theme="dark"] .draft-item { background: #2c2521; color: #f2ece8; border-color: #4a3d36; }
        [data-theme="dark"] .draft-item.active { background: #3a2d27; border-color: #be6a4a; }
        [data-theme="dark"] .type-card { background: #2c2521; border-color: #4a3d36; }
        @media (max-width: 900px) {
            .checker-layout { grid-template-columns: 1fr; }
            .draft-sidebar { position: static; }
            .type-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <main class="page">
        <section class="hero">
            <div class="topbar">
                <h1>UniFlow Essay Checker</h1>
                <nav class="links">
                    <a class="nav-btn" href="{{ url_for('mainpage') }}">Main Page</a>
                    <button type="button" id="profile-badge" class="badge">{{ badge_initial }}</button>
                    <div id="profile-menu" class="profile-menu">
                        <button type="button" id="open-settings" class="menu-item">Settings</button>
                        <a class="menu-item" href="{{ url_for('logout') }}">Log Out</a>
                    </div>
                </nav>
            </div>
            {% if settings_message %}
                <p class="settings-msg">{{ settings_message }}</p>
            {% endif %}
            <p class="lead">
                Choose the university writing section you are working on, then get
                Gemini-powered feedback on structure, clarity, specificity, and application strength.
            </p>
            <div class="checker-layout">
                <aside class="draft-sidebar">
                    <p class="section-label">Saved essays</p>
                    <div class="draft-list">
                        <div class="session-chip">Current session essay</div>
                        {% for draft in drafts %}
                            <div class="draft-entry">
                                <form method="post">
                                    <input type="hidden" name="action" value="load_draft">
                                    <input type="hidden" name="draft_index" value="{{ loop.index0 }}">
                                    <button class="draft-item {% if selected_draft_index == loop.index0 %}active{% endif %}" type="submit">
                                        {{ draft.title or "Untitled draft " ~ loop.index }} · {{ format_essay_type(draft.essay_type or 'personal_statement') }}
                                    </button>
                                </form>
                                <form method="post">
                                    <input type="hidden" name="action" value="delete_draft">
                                    <input type="hidden" name="draft_index" value="{{ loop.index0 }}">
                                    <button class="draft-delete" type="submit">Delete</button>
                                </form>
                            </div>
                        {% endfor %}
                        {% if not drafts %}
                            <p class="draft-empty">No drafts yet. Save one from the right panel.</p>
                        {% endif %}
                    </div>
                </aside>
                <form method="post" class="editor-panel">
                    <input type="hidden" name="draft_index" value="{{ selected_draft_index if selected_draft_index is not none else '' }}">
                    <p class="section-label">Essay type</p>
                    <div class="type-grid">
                        <label class="type-card" for="type-personal">
                            <div>
                                <input id="type-personal" type="radio" name="essay_type" value="personal_statement" {% if essay_type == 'personal_statement' %}checked{% endif %}>
                                <strong>Personal Statement for Universities</strong>
                            </div>
                            <span>Use this for personal background, values, growth, and what makes you stand out.</span>
                        </label>
                        <label class="type-card" for="type-motivational">
                            <div>
                                <input id="type-motivational" type="radio" name="essay_type" value="motivational_essay" {% if essay_type == 'motivational_essay' %}checked{% endif %}>
                                <strong>Motivational Essay for University</strong>
                            </div>
                            <span>Use this for academic goals, program fit, motivation, and future plans.</span>
                        </label>
                    </div>
                    <label for="essay_title"><strong>Essay title</strong></label>
                    <input id="essay_title" name="essay_title" value="{{ essay_title }}" placeholder="My persuasive essay">
                    <p class="section-label">Essay checking</p>
                    <label for="essay"><strong>{{ format_essay_type(essay_type) }}</strong></label>
                    <textarea id="essay" name="essay" placeholder="Paste your university writing draft here...">{{ essay }}</textarea>
                    <div style="display:flex; gap:10px; flex-wrap:wrap;">
                        <button type="submit" name="action" value="save_draft">Save Draft</button>
                        <button type="submit" name="action" value="check_essay">Check Essay</button>
                    </div>
                </form>
            </div>
            {% if error %}
                <p class="empty">{{ error }}</p>
            {% endif %}
        </section>
        {% if result %}
            <section class="results">
                <h2>Evaluation Result</h2>
                <div class="score">Score: {{ result.score }}/100</div>
                <div class="grid">
                    <div class="card"><span class="label">Word Count</span><strong>{{ result.word_count }}</strong></div>
                    <div class="card"><span class="label">Sentences</span><strong>{{ result.sentence_count }}</strong></div>
                    <div class="card"><span class="label">Paragraphs</span><strong>{{ result.paragraph_count }}</strong></div>
                    <div class="card"><span class="label">Average Sentence Length</span><strong>{{ result.average_sentence_length }} words</strong></div>
                </div>
                <h3>Overall Feedback</h3>
                <p>{{ result.summary }}</p>
                <h3>Detailed Feedback</h3>
                <ul>
                    {% for item in result.feedback %}
                        <li>{{ item }}</li>
                    {% endfor %}
                </ul>
            </section>
        {% endif %}
    </main>
    <div id="settings-modal" class="modal-backdrop">
        <div class="modal-card">
            <h3>Settings</h3>
            <form method="post" action="{{ url_for('settings') }}">
                <div class="modal-row">
                    <label for="settings-name">Name</label>
                    <input id="settings-name" name="name" value="{{ display_name }}" placeholder="Your name">
                </div>
                <div class="modal-row">
                    <label for="settings-email">Email</label>
                    <input id="settings-email" name="email" value="{{ email }}" type="email" required>
                </div>
                <div class="modal-row">
                    <label for="settings-current-password">Current Password</label>
                    <input id="settings-current-password" name="current_password" type="password" placeholder="Required only to change password">
                </div>
                <div class="modal-row">
                    <label for="settings-new-password">New Password</label>
                    <input id="settings-new-password" name="new_password" type="password" placeholder="Leave empty to keep current">
                </div>
                <label class="switch"><input id="theme-toggle" type="checkbox"> Use dark theme</label>
                <button type="submit">Save Settings</button>
                <button type="button" id="close-settings">Close</button>
            </form>
        </div>
    </div>
    <script>
        const THEME_KEY = 'uniflow_theme';
        const setTheme = (theme) => {
            if (theme === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
            } else {
                document.documentElement.removeAttribute('data-theme');
            }
        };
        setTheme(localStorage.getItem(THEME_KEY) || 'light');

        const profileBadge = document.getElementById('profile-badge');
        const profileMenu = document.getElementById('profile-menu');
        profileBadge.addEventListener('click', () => profileMenu.classList.toggle('show'));
        document.addEventListener('click', (event) => {
            if (!profileMenu.contains(event.target) && event.target !== profileBadge) {
                profileMenu.classList.remove('show');
            }
        });

        const settingsModal = document.getElementById('settings-modal');
        document.getElementById('open-settings').addEventListener('click', () => {
            settingsModal.classList.add('show');
            profileMenu.classList.remove('show');
        });
        document.getElementById('close-settings').addEventListener('click', () => settingsModal.classList.remove('show'));
        settingsModal.addEventListener('click', (event) => {
            if (event.target === settingsModal) settingsModal.classList.remove('show');
        });

        const themeToggle = document.getElementById('theme-toggle');
        themeToggle.checked = (localStorage.getItem(THEME_KEY) || 'light') === 'dark';
        themeToggle.addEventListener('change', () => {
            const theme = themeToggle.checked ? 'dark' : 'light';
            localStorage.setItem(THEME_KEY, theme);
            setTheme(theme);
        });
    </script>
</body>
</html>
"""


IELTS_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>UniFlow IELTS Practice</title>
    <style>
        :root {
            --bg: #f3f0ed;
            --panel: #fffdfb;
            --ink: #2a2a2a;
            --muted: #6b645c;
            --accent: #b55b3e;
            --line: #ece6e0;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Georgia, "Times New Roman", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 5%, #fff8f1 0%, transparent 35%),
                linear-gradient(135deg, #f4f0eb 0%, #eee6dd 100%);
        }
        .page { width: min(1060px, calc(100% - 32px)); margin: 28px auto; }
        .hero, .notes {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: 0 16px 40px rgba(62, 45, 34, 0.1);
        }
        .hero { padding: 28px; }
        .topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
        .links { display: flex; gap: 14px; align-items: center; position: relative; }
        .links a { color: #2e2a26; text-decoration: none; font-weight: 700; transition: color 0.16s ease; }
        .links a:hover { color: #9f472f; }
        .badge {
            width: 48px;
            height: 48px;
            border-radius: 999px;
            border: 1px solid #cfb8aa;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            color: #fff;
            font-weight: 700;
            font-size: 1.15rem;
            display: grid;
            place-items: center;
            cursor: pointer;
        }
        .profile-menu {
            position: absolute;
            top: calc(100% + 8px);
            right: 0;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 12px;
            min-width: 170px;
            box-shadow: 0 10px 24px rgba(62, 45, 34, 0.18);
            padding: 8px;
            display: none;
            z-index: 5;
        }
        .profile-menu.show { display: block; }
        .menu-item {
            width: 100%;
            border: 0;
            background: transparent;
            text-align: left;
            padding: 8px 10px;
            border-radius: 8px;
            cursor: pointer;
            font: inherit;
            color: #2e2a26;
            text-decoration: none;
            display: block;
        }
        .menu-item:hover { background: #f7eee7; }
        h1 { font-size: clamp(2rem, 5vw, 3.2rem); margin: 0; }
        .lead { max-width: 760px; color: var(--muted); margin-bottom: 18px; line-height: 1.6; }
        .practice-layout { display: grid; grid-template-columns: 270px 1fr; gap: 14px; align-items: start; }
        .draft-sidebar {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #fff9f4;
            padding: 12px;
            position: sticky;
            top: 14px;
        }
        .draft-list { display: grid; gap: 8px; margin-top: 8px; max-height: 420px; overflow: auto; }
        .draft-item {
            width: 100%;
            border: 1px solid #e3d5c9;
            background: #fff;
            color: #3a332d;
            border-radius: 10px;
            text-align: left;
            padding: 9px 10px;
            box-shadow: none;
        }
        .draft-item.active { border-color: #be6a4a; background: #fff1e7; }
        .draft-empty { color: #6a6159; margin: 8px 0 0; }
        .editor-panel { border: 1px solid var(--line); border-radius: 12px; background: #fff; padding: 12px; }
        .results {
            margin-top: 18px;
            padding: 20px 22px;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 16px 40px rgba(62, 45, 34, 0.08);
        }
        .score {
            display: inline-flex;
            gap: 10px;
            font-size: 1.05rem;
            font-weight: 700;
            color: #256c3f;
            background: #edf7ef;
            border-radius: 999px;
            padding: 8px 14px;
        }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 14px; }
        .card {
            border: 1px solid var(--line);
            border-radius: 14px;
            background: #fff;
            padding: 14px;
        }
        .label { display: block; color: var(--muted); font-size: 0.95rem; margin-bottom: 6px; }
        .section-label { margin: 4px 0 0; color: #534a43; font-weight: 700; font-size: 1.02rem; }
        input, textarea {
            width: 100%;
            border-radius: 12px;
            border: 1px solid #d8cec4;
            padding: 12px;
            font: inherit;
            background: #fff;
        }
        textarea { min-height: 260px; resize: vertical; }
        button {
            width: fit-content;
            border: 0;
            border-radius: 999px;
            padding: 10px 20px;
            font-size: 1rem;
            font-weight: 700;
            color: #fff;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            box-shadow: 0 8px 18px rgba(159, 71, 47, 0.28);
            cursor: pointer;
        }
        .settings-msg { color: #256c3f; font-weight: 700; margin: 8px 0 0; }
        .empty { color: #8a2d2d; font-weight: 700; }
        .notes { margin-top: 18px; padding: 18px; }
        .modal-backdrop { position: fixed; inset: 0; background: rgba(16, 10, 8, 0.4); display: none; align-items: center; justify-content: center; z-index: 30; padding: 18px; }
        .modal-backdrop.show { display: flex; }
        .modal-card { width: min(520px, 100%); border-radius: 16px; background: #fff; border: 1px solid var(--line); box-shadow: 0 20px 50px rgba(30, 20, 14, 0.25); padding: 20px; }
        .modal-row { margin-bottom: 10px; }
        .switch { display: flex; align-items: center; gap: 10px; margin: 12px 0 16px; }
        .switch input { width: auto; }
        [data-theme="dark"] body {
            --bg: #181513;
            --panel: #211d1a;
            --ink: #f2ece8;
            --muted: #c6b9b0;
            --line: #3f342e;
            background: linear-gradient(135deg, #151210 0%, #1f1a17 100%);
        }
        [data-theme="dark"] .hero, [data-theme="dark"] .notes, [data-theme="dark"] .draft-sidebar, [data-theme="dark"] .editor-panel, [data-theme="dark"] .results, [data-theme="dark"] .modal-card, [data-theme="dark"] .profile-menu { background: #231e1b; color: var(--ink); }
        [data-theme="dark"] .links a, [data-theme="dark"] .menu-item { color: #f2ece8; }
        [data-theme="dark"] input, [data-theme="dark"] textarea, [data-theme="dark"] .modal-row input { background: #2c2521; color: #f2ece8; border-color: #4a3d36; }
        [data-theme="dark"] .draft-item { background: #2c2521; color: #f2ece8; border-color: #4a3d36; }
        [data-theme="dark"] .draft-item.active { background: #3a2d27; border-color: #be6a4a; }
        [data-theme="dark"] .card { background: #2c2521; border-color: #4a3d36; }
        [data-theme="dark"] .score { background: #213428; color: #c8efcf; }
        @media (max-width: 900px) {
            .practice-layout { grid-template-columns: 1fr; }
            .draft-sidebar { position: static; }
        }
    </style>
</head>
<body>
    <main class="page">
        <section class="hero">
            <div class="topbar">
                <h1>UniFlow IELTS Practice</h1>
                <nav class="links">
                    <a class="nav-btn" href="{{ url_for('mainpage') }}">Main Page</a>
                    <button type="button" id="profile-badge" class="badge">{{ badge_initial }}</button>
                    <div id="profile-menu" class="profile-menu">
                        <button type="button" id="open-settings" class="menu-item">Settings</button>
                        <a class="menu-item" href="{{ url_for('logout') }}">Log Out</a>
                    </div>
                </nav>
            </div>
            {% if settings_message %}
                <p class="settings-msg">{{ settings_message }}</p>
            {% endif %}
            <p class="lead">Practice IELTS writing prompts, save drafts, and build your own response library over time.</p>
            <div class="practice-layout">
                <aside class="draft-sidebar">
                    <p class="section-label">Saved IELTS drafts</p>
                    <div class="draft-list">
                        {% for draft in ielts_drafts %}
                            <form method="post">
                                <input type="hidden" name="action" value="load_draft">
                                <input type="hidden" name="draft_index" value="{{ loop.index0 }}">
                                <button class="draft-item {% if selected_draft_index == loop.index0 %}active{% endif %}" type="submit">
                                    {{ draft.title or "Untitled draft " ~ loop.index }}
                                </button>
                            </form>
                        {% endfor %}
                        {% if not ielts_drafts %}
                            <p class="draft-empty">No IELTS drafts yet. Save one from the right panel.</p>
                        {% endif %}
                    </div>
                </aside>
                <form method="post" class="editor-panel">
                    <input type="hidden" name="draft_index" value="{{ selected_draft_index if selected_draft_index is not none else '' }}">
                    <label for="practice_title"><strong>Prompt title</strong></label>
                    <input id="practice_title" name="practice_title" value="{{ practice_title }}" placeholder="Some people think... Discuss both views">
                    <p class="section-label">Writing response</p>
                    <textarea id="practice_response" name="practice_response" placeholder="Write your IELTS response here...">{{ practice_response }}</textarea>
                    <div style="display:flex; gap:10px; flex-wrap:wrap;">
                        <button type="submit" name="action" value="save_draft">Save Draft</button>
                        <button type="submit" name="action" value="check_response">Check Response</button>
                    </div>
                </form>
            </div>
            {% if error %}
                <p class="empty">{{ error }}</p>
            {% endif %}
        </section>
        {% if result %}
            <section class="results">
                <h2>Feedback Result</h2>
                <div class="score">Score: {{ result.score }}/100</div>
                <div class="grid">
                    <div class="card"><span class="label">Word Count</span><strong>{{ result.word_count }}</strong></div>
                    <div class="card"><span class="label">Sentences</span><strong>{{ result.sentence_count }}</strong></div>
                    <div class="card"><span class="label">Paragraphs</span><strong>{{ result.paragraph_count }}</strong></div>
                    <div class="card"><span class="label">Average Sentence Length</span><strong>{{ result.average_sentence_length }} words</strong></div>
                </div>
                <h3>Overall Feedback</h3>
                <p>{{ result.summary }}</p>
                <h3>Detailed Feedback</h3>
                <ul>
                    {% for item in result.feedback %}
                        <li>{{ item }}</li>
                    {% endfor %}
                </ul>
            </section>
        {% endif %}
        <section class="notes">
            <h3>Practice note</h3>
            <p>For stronger IELTS writing, aim for clear structure: introduction, two body paragraphs, and a concise conclusion.</p>
        </section>
    </main>
    <div id="settings-modal" class="modal-backdrop">
        <div class="modal-card">
            <h3>Settings</h3>
            <form method="post" action="{{ url_for('settings') }}">
                <div class="modal-row">
                    <label for="settings-name">Name</label>
                    <input id="settings-name" name="name" value="{{ display_name }}" placeholder="Your name">
                </div>
                <div class="modal-row">
                    <label for="settings-email">Email</label>
                    <input id="settings-email" name="email" value="{{ email }}" type="email" required>
                </div>
                <div class="modal-row">
                    <label for="settings-current-password">Current Password</label>
                    <input id="settings-current-password" name="current_password" type="password" placeholder="Required only to change password">
                </div>
                <div class="modal-row">
                    <label for="settings-new-password">New Password</label>
                    <input id="settings-new-password" name="new_password" type="password" placeholder="Leave empty to keep current">
                </div>
                <label class="switch"><input id="theme-toggle" type="checkbox"> Use dark theme</label>
                <button type="submit">Save Settings</button>
                <button type="button" id="close-settings">Close</button>
            </form>
        </div>
    </div>
    <script>
        const THEME_KEY = 'uniflow_theme';
        const setTheme = (theme) => {
            if (theme === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
            } else {
                document.documentElement.removeAttribute('data-theme');
            }
        };
        setTheme(localStorage.getItem(THEME_KEY) || 'light');

        const profileBadge = document.getElementById('profile-badge');
        const profileMenu = document.getElementById('profile-menu');
        profileBadge.addEventListener('click', () => profileMenu.classList.toggle('show'));
        document.addEventListener('click', (event) => {
            if (!profileMenu.contains(event.target) && event.target !== profileBadge) {
                profileMenu.classList.remove('show');
            }
        });

        const settingsModal = document.getElementById('settings-modal');
        document.getElementById('open-settings').addEventListener('click', () => {
            settingsModal.classList.add('show');
            profileMenu.classList.remove('show');
        });
        document.getElementById('close-settings').addEventListener('click', () => settingsModal.classList.remove('show'));
        settingsModal.addEventListener('click', (event) => {
            if (event.target === settingsModal) settingsModal.classList.remove('show');
        });

        const themeToggle = document.getElementById('theme-toggle');
        themeToggle.checked = (localStorage.getItem(THEME_KEY) || 'light') === 'dark';
        themeToggle.addEventListener('change', () => {
            const theme = themeToggle.checked ? 'dark' : 'light';
            localStorage.setItem(THEME_KEY, theme);
            setTheme(theme);
        });
    </script>
</body>
</html>
"""


UNIVERSITIES_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>University Finder | UniFlow</title>
    <style>
        :root {
            --bg: #f3f0ed;
            --panel: #fffdfb;
            --ink: #2a2a2a;
            --muted: #6b645c;
            --accent: #b55b3e;
            --accent-2: #d98663;
            --line: #ece6e0;
            --good: #256c3f;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Georgia, "Times New Roman", serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 5%, #fff8f1 0%, transparent 35%),
                linear-gradient(135deg, #f4f0eb 0%, #eee6dd 100%);
        }
        .page { width: min(960px, calc(100% - 32px)); margin: 28px auto; }
        .hero {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: 0 16px 40px rgba(62, 45, 34, 0.1);
            padding: 28px;
        }
        .topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 28px; }
        .links { display: flex; gap: 14px; align-items: center; position: relative; }
        .links a { color: #2e2a26; text-decoration: none; font-weight: 700; transition: color 0.16s ease; }
        .links a:hover { color: #9f472f; }
        .nav-btn {
            border: 1px solid #c9b3a4;
            border-radius: 999px;
            padding: 8px 14px;
            background: #fff;
            box-shadow: 0 4px 10px rgba(62, 45, 34, 0.08);
        }
        .badge {
            width: 48px;
            height: 48px;
            border-radius: 999px;
            border: 1px solid #cfb8aa;
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            color: #fff;
            font-weight: 700;
            font-size: 1.15rem;
            display: grid;
            place-items: center;
            cursor: pointer;
        }
        .profile-menu {
            position: absolute;
            top: calc(100% + 8px);
            right: 0;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 12px;
            min-width: 170px;
            box-shadow: 0 10px 24px rgba(62, 45, 34, 0.18);
            padding: 8px;
            display: none;
            z-index: 5;
        }
        .profile-menu.show { display: block; }
        .profile-menu a {
            display: block;
            padding: 10px 14px;
            border-radius: 8px;
            text-decoration: none;
            color: var(--ink);
            font-size: 0.95rem;
            transition: background 0.16s ease;
        }
        .profile-menu a:hover { background: #f0e8e0; }
        h1 { margin: 0 0 8px 0; font-size: 2.2rem; font-weight: 700; color: var(--accent); }
        .subtitle { color: var(--muted); margin: 0 0 24px 0; font-size: 1.05rem; }
        .search-section {
            margin-bottom: 28px;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--line);
        }
        .form-group { margin-bottom: 16px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: var(--ink); }
        select {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--line);
            border-radius: 12px;
            font-family: Georgia, serif;
            font-size: 1rem;
            background: #fff;
            cursor: pointer;
            color: var(--ink);
        }
        select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(181, 91, 62, 0.1); }
        button {
            background: linear-gradient(135deg, #bd6547 0%, #9f472f 100%);
            color: #fff;
            border: none;
            padding: 12px 24px;
            border-radius: 999px;
            font-weight: 700;
            cursor: pointer;
            transition: transform 0.16s ease, box-shadow 0.16s ease;
            font-size: 1rem;
            font-family: Georgia, serif;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(159, 71, 47, 0.3); }
        .universities-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-top: 28px;
        }
        .university-card {
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 20px;
            transition: transform 0.16s ease, box-shadow 0.16s ease;
        }
        .university-card:hover { transform: translateY(-4px); box-shadow: 0 12px 28px rgba(62, 45, 34, 0.12); }
        .university-card h3 { margin: 0 0 12px 0; color: var(--accent); font-size: 1.2rem; }
        .university-card a { color: var(--accent); text-decoration: none; font-weight: 600; }
        .university-card a:hover { text-decoration: underline; }
        .university-info { margin: 12px 0; font-size: 0.95rem; }
        .university-info strong { color: var(--ink); }
        .rankings {
            display: flex;
            gap: 12px;
            margin-top: 12px;
            font-size: 0.9rem;
        }
        .ranking-badge {
            background: #f0e8e0;
            padding: 6px 10px;
            border-radius: 6px;
            color: var(--ink);
            font-weight: 600;
        }
        .no-results {
            text-align: center;
            padding: 40px 20px;
            color: var(--muted);
            font-size: 1.05rem;
        }
        .dark {
            --bg: #1a1916;
            --panel: #2a2520;
            --ink: #f0ede8;
            --muted: #a89f98;
            --line: #3d3832;
        }
        .dark .university-card { background: #1a1916; border-color: var(--line); }
        .dark select { background: #2a2520; color: var(--ink); }
        .dark .ranking-badge { background: #3d3832; }
    </style>
</head>
<body>
    <div class="page">
        <div class="topbar">
            <h1>🎓 University Finder</h1>
            <div class="links">
                <a href="/" class="nav-btn">Essay Checker</a>
                <a href="/mainpage" class="nav-btn">Dashboard</a>
                {% if username %}
                    <div style="position: relative;">
                        <div class="badge" id="profile-badge">{{ badge_initial }}</div>
                        <div class="profile-menu" id="profile-menu">
                            <a href="/settings" id="open-settings">Settings</a>
                            <a href="/logout">Logout</a>
                        </div>
                    </div>
                {% else %}
                    <a href="/" class="nav-btn">Login</a>
                {% endif %}
            </div>
        </div>

        <div class="hero">
            <h2 style="margin: 0 0 8px 0; color: var(--accent);">Find Universities Worldwide</h2>
            <p class="subtitle">Explore top universities from across the globe</p>

            <div class="search-section">
                <form method="POST">
                    <div class="form-group">
                        <label for="country">Select Country or Region:</label>
                        <select name="country" id="country">
                            <option value="">-- Choose a country --</option>
                            {% for country in countries %}
                                <option value="{{ country }}" {% if selected_country == country %}selected{% endif %}>
                                    {{ country }}
                                </option>
                            {% endfor %}
                        </select>
                    </div>
                    <button type="submit">Search Universities</button>
                </form>
            </div>

            {% if universities %}
                <div style="margin-top: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--line);">
                    <p style="margin: 0; color: var(--muted); font-size: 0.95rem;">
                        Found <strong>{{ universities|length }} universities</strong> in <strong>{{ selected_country }}</strong>
                    </p>
                </div>

                <div class="universities-grid">
                    {% for uni in universities %}
                        <div class="university-card">
                            <h3>{{ uni.name }}</h3>
                            <div class="university-info">
                                <strong>Location:</strong> {{ uni.city }}
                            </div>
                            <div class="rankings">
                                {% if uni.qs_ranking %}
                                    <span class="ranking-badge">QS #{{ uni.qs_ranking }}</span>
                                {% endif %}
                                {% if uni.the_ranking %}
                                    <span class="ranking-badge">THE #{{ uni.the_ranking }}</span>
                                {% endif %}
                            </div>
                            <div style="margin-top: 14px;">
                                <a href="{{ uni.website_url }}" target="_blank" rel="noopener noreferrer">Visit Website →</a>
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% elif selected_country %}
                <div class="no-results">
                    No universities found for {{ selected_country }}
                </div>
            {% else %}
                <div class="no-results">
                    Select a country to view universities
                </div>
            {% endif %}
        </div>
    </div>

    <script>
        const profileBadge = document.getElementById('profile-badge');
        const profileMenu = document.getElementById('profile-menu');
        if (profileBadge && profileMenu) {
            profileBadge.addEventListener('click', () => profileMenu.classList.toggle('show'));
            document.addEventListener('click', (event) => {
                if (!profileMenu.contains(event.target) && event.target !== profileBadge) {
                    profileMenu.classList.remove('show');
                }
            });
        }

        const THEME_KEY = 'app-theme';
        function setTheme(theme) {
            document.body.classList.toggle('dark', theme === 'dark');
            localStorage.setItem(THEME_KEY, theme);
        }
        const savedTheme = localStorage.getItem(THEME_KEY) || 'light';
        setTheme(savedTheme);
    </script>
</body>
</html>
"""


def split_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence for sentence in sentences if sentence.strip()]


def split_paragraphs(text):
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [paragraph for paragraph in paragraphs if paragraph.strip()]


def get_essay_metrics(text):
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = split_sentences(text)
    paragraphs = split_paragraphs(text)
    average_sentence_length = round(len(words) / len(sentences), 1) if sentences else 0

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "average_sentence_length": average_sentence_length,
    }


def extract_json_from_text(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def gemini_api_request(path, payload=None):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it in your Render environment variables.")

    url = f"https://generativelanguage.googleapis.com/v1beta/{path}?key={GEMINI_API_KEY}"
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API error: {exc.code} {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach the Gemini API from this app.") from exc


def list_gemini_models():
    response = gemini_api_request("models")
    return response.get("models", [])


def pick_gemini_model():
    if MODEL_CACHE["name"]:
        return MODEL_CACHE["name"]

    preferred_models = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

    try:
        models = list_gemini_models()
    except RuntimeError:
        MODEL_CACHE["name"] = GEMINI_MODEL
        return GEMINI_MODEL

    supported = []
    for model in models:
        methods = model.get("supportedGenerationMethods", [])
        name = model.get("name", "")
        if "generateContent" in methods and name.startswith("models/"):
            supported.append(name.split("/", 1)[1])

    for candidate in preferred_models:
        if candidate in supported:
            MODEL_CACHE["name"] = candidate
            return candidate

    for candidate in supported:
        if "flash" in candidate:
            MODEL_CACHE["name"] = candidate
            return candidate

    for candidate in supported:
        if "gemini" in candidate:
            MODEL_CACHE["name"] = candidate
            return candidate

    raise RuntimeError("No Gemini model with generateContent support was found for this API key.")


def format_essay_type(essay_type):
    if essay_type == "motivational_essay":
        return "Motivational Essay for University"
    return "Personal Statement for Universities"


def check_essay_with_gemini(text, essay_type="general"):
    essay_type_label = format_essay_type(essay_type) if essay_type in {"personal_statement", "motivational_essay"} else "Essay"
    prompt = f"""
You are an evaluator for university writing tasks. You are strict, dont give high scores for weak or generic writing. If the essay is too short like 3 sentences maximum dont be generous.
The student submitted this writing type: {essay_type_label}.
Read the writing and respond with JSON only using this exact schema:
{{
  "score": 0,
  "summary": "one short paragraph",
  "feedback": [
    "feedback point 1",
    "feedback point 2",
    "feedback point 3",
    "feedback point 4"
  ]
}}

Rules:
- Score must be an integer from 0 to 100.
- Feedback should be specific, helpful, and easy for a student to understand.
- Mention strengths and weaknesses.
- If this is a personal statement or motivational essay, pay attention to authenticity, fit for university applications, reflection, goals, and specificity.
- Do not include markdown fences or any text outside the JSON.

Essay:
\"\"\"
{text}
\"\"\"
""".strip()

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }
    model_name = pick_gemini_model()

    try:
        raw_response = gemini_api_request(f"models/{model_name}:generateContent", payload)
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise

        MODEL_CACHE["name"] = None
        model_name = pick_gemini_model()
        raw_response = gemini_api_request(f"models/{model_name}:generateContent", payload)

    candidates = raw_response.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    response_text = "".join(part.get("text", "") for part in parts).strip()
    if not response_text:
        raise RuntimeError("Gemini returned an empty response.")

    parsed = extract_json_from_text(response_text)
    score = int(parsed.get("score", 0))
    feedback = parsed.get("feedback", [])

    if not isinstance(feedback, list) or not feedback:
        raise RuntimeError("Gemini response did not include valid feedback.")

    return {
        "score": max(0, min(score, 100)),
        "summary": str(parsed.get("summary", "")).strip() or "No summary was returned.",
        "feedback": [str(item).strip() for item in feedback if str(item).strip()],
    }


def analyze_essay(text, essay_type="general"):
    metrics = get_essay_metrics(text)
    gemini_result = check_essay_with_gemini(text, essay_type=essay_type)
    return {**metrics, **gemini_result}


@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("mainpage"))

    error = None
    success = None
    username = ""
    message = session.pop("auth_message", "")
    if request.method == "POST":
        action = request.form.get("action", "login")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if action == "register":
            email = request.form.get("email", "").strip()
            full_name = request.form.get("name", "").strip()
            if len(username) < 3:
                error = "Username must be at least 3 characters."
            elif "@" not in email or "." not in email:
                error = "Please enter a valid email."
            elif len(password) < 4:
                error = "Password must be at least 4 characters."
            elif username in USERS:
                error = "This username is already registered."
            else:
                USERS[username] = password
                REGISTERED_EMAILS[username] = email
                REGISTERED_NAMES[username] = full_name
                save_user_store()
                success = "Registered successfully. You can now log in."
                message = ""
        elif USERS.get(username) == password:
            session["logged_in"] = True
            session["username"] = username
            session["display_name"] = REGISTERED_NAMES.get(username, "")
            return redirect(url_for("mainpage"))
        else:
            error = "Invalid username or password."

    return render_template_string(
        AUTH_TEMPLATE,
        error=error,
        success=success,
        username=username,
        message=message,
    )


@app.route("/settings", methods=["POST"])
def settings():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    username = session.get("username", "")
    if not username or username not in USERS:
        session["settings_message"] = "Could not find your account."
        return redirect(url_for("mainpage"))

    email = request.form.get("email", "").strip()
    name = request.form.get("name", "").strip()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")

    if email and ("@" not in email or "." not in email):
        session["settings_message"] = "Email format is invalid."
        return redirect(url_for("mainpage"))

    if new_password:
        if USERS.get(username) != current_password:
            session["settings_message"] = "Current password is incorrect."
            return redirect(url_for("mainpage"))
        if len(new_password) < 4:
            session["settings_message"] = "New password must be at least 4 characters."
            return redirect(url_for("mainpage"))
        USERS[username] = new_password

    if email:
        REGISTERED_EMAILS[username] = email
    if name or username not in REGISTERED_NAMES:
        REGISTERED_NAMES[username] = name

    session["display_name"] = REGISTERED_NAMES.get(username, "")
    save_user_store()
    session["settings_message"] = "Settings updated."
    return redirect(url_for("mainpage"))


@app.route("/mainpage", methods=["GET", "POST"])
def mainpage():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    username = session.get("username", "")
    display_name = REGISTERED_NAMES.get(username, "") or session.get("display_name", "")
    badge_source = display_name or username or "U"
    badge_initial = badge_source[0].upper()
    settings_message = session.pop("settings_message", "")
    essay_drafts_count = len(DRAFTS.get(username, []))
    ielts_drafts_count = len(IELTS_DRAFTS.get(username, []))
    ielts_locked = essay_drafts_count == 0
    essay_done = essay_drafts_count > 0
    ielts_done = ielts_drafts_count > 0

    return render_template_string(
        DASHBOARD_TEMPLATE,
        drafts_count=essay_drafts_count,
        ielts_drafts_count=ielts_drafts_count,
        ielts_locked=ielts_locked,
        essay_done=essay_done,
        ielts_done=ielts_done,
        saved_region="Not set yet",
        username=username,
        display_name=display_name,
        email=REGISTERED_EMAILS.get(username, ""),
        badge_initial=badge_initial,
        settings_message=settings_message,
        universities_url=url_for("universities"),
    )


@app.route("/essay-checker", methods=["GET", "POST"])
def essay_checker():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    username = session.get("username", "")
    display_name = REGISTERED_NAMES.get(username, "") or session.get("display_name", "")
    badge_source = display_name or username or "U"
    badge_initial = badge_source[0].upper()
    settings_message = session.pop("settings_message", "")

    essay = ""
    essay_title = ""
    essay_type = "personal_statement"
    result = None
    error = None
    drafts = DRAFTS.get(username, [])
    selected_draft_index = None

    if request.method == "POST":
        action = request.form.get("action", "check_essay")
        essay_title = request.form.get("essay_title", "").strip()
        essay = request.form.get("essay", "").strip()
        essay_type = request.form.get("essay_type", "personal_statement").strip()
        if essay_type not in {"personal_statement", "motivational_essay"}:
            essay_type = "personal_statement"
        selected_draft = request.form.get("draft_index", "").strip()

        if selected_draft.isdigit():
            selected_draft_index = int(selected_draft)

        if action == "load_draft":
            if selected_draft_index is None or selected_draft_index >= len(drafts):
                error = "Draft was not found."
            else:
                picked = drafts[selected_draft_index]
                essay_title = picked.get("title", "")
                essay = picked.get("essay", "")
                essay_type = picked.get("essay_type", "personal_statement")
        elif action == "delete_draft":
            if selected_draft_index is None or selected_draft_index >= len(drafts):
                error = "Draft was not found."
            else:
                del drafts[selected_draft_index]
                DRAFTS[username] = drafts
                save_drafts()
                selected_draft_index = None
                essay_title = ""
                essay = ""
        elif action == "save_draft":
            if not essay_title and not essay:
                error = "Write a title or essay before saving a draft."
            else:
                if selected_draft_index is not None and selected_draft_index < len(drafts):
                    drafts[selected_draft_index] = {"title": essay_title, "essay": essay, "essay_type": essay_type}
                    selected_draft_index = selected_draft_index
                else:
                    drafts.append({"title": essay_title, "essay": essay, "essay_type": essay_type})
                    selected_draft_index = len(drafts) - 1
                DRAFTS[username] = drafts
                save_drafts()
        else:
            if not essay:
                error = "Please enter an essay before submitting."
            else:
                try:
                    result = analyze_essay(essay, essay_type=essay_type)
                except Exception as exc:
                    error = str(exc)

    drafts = DRAFTS.get(username, [])

    return render_template_string(
        PAGE_TEMPLATE,
        essay=essay,
        essay_title=essay_title,
        essay_type=essay_type,
        result=result,
        error=error,
        drafts=drafts,
        selected_draft_index=selected_draft_index,
        username=username,
        display_name=display_name,
        email=REGISTERED_EMAILS.get(username, ""),
        badge_initial=badge_initial,
        settings_message=settings_message,
        format_essay_type=format_essay_type,
    )


@app.route("/ielts-practice", methods=["GET", "POST"])
def ielts_practice():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    username = session.get("username", "")
    if len(DRAFTS.get(username, [])) == 0:
        session["settings_message"] = "Finish at least one essay draft before opening IELTS practice."
        return redirect(url_for("mainpage"))

    display_name = REGISTERED_NAMES.get(username, "") or session.get("display_name", "")
    badge_source = display_name or username or "U"
    badge_initial = badge_source[0].upper()
    settings_message = session.pop("settings_message", "")

    practice_title = ""
    practice_response = ""
    result = None
    error = None
    ielts_drafts = IELTS_DRAFTS.get(username, [])
    selected_draft_index = None

    if request.method == "POST":
        action = request.form.get("action", "save_draft")
        practice_title = request.form.get("practice_title", "").strip()
        practice_response = request.form.get("practice_response", "").strip()
        selected_draft = request.form.get("draft_index", "").strip()

        if selected_draft.isdigit():
            selected_draft_index = int(selected_draft)

        if action == "load_draft":
            if selected_draft_index is None or selected_draft_index >= len(ielts_drafts):
                error = "Draft was not found."
            else:
                picked = ielts_drafts[selected_draft_index]
                practice_title = picked.get("title", "")
                practice_response = picked.get("response", "")
        elif action == "save_draft":
            if not practice_title and not practice_response:
                error = "Write a title or response before saving."
            else:
                if selected_draft_index is not None and selected_draft_index < len(ielts_drafts):
                    ielts_drafts[selected_draft_index] = {"title": practice_title, "response": practice_response}
                else:
                    ielts_drafts.append({"title": practice_title, "response": practice_response})
                    selected_draft_index = len(ielts_drafts) - 1
                IELTS_DRAFTS[username] = ielts_drafts
                save_ielts_drafts()
        else:
            if not practice_response:
                error = "Please enter an IELTS response before checking."
            else:
                try:
                    result = analyze_essay(practice_response)
                except Exception as exc:
                    error = str(exc)

    ielts_drafts = IELTS_DRAFTS.get(username, [])

    return render_template_string(
        IELTS_TEMPLATE,
        practice_title=practice_title,
        practice_response=practice_response,
        result=result,
        ielts_drafts=ielts_drafts,
        selected_draft_index=selected_draft_index,
        error=error,
        username=username,
        display_name=display_name,
        email=REGISTERED_EMAILS.get(username, ""),
        badge_initial=badge_initial,
        settings_message=settings_message,
    )


@app.route("/universities", methods=["GET", "POST"])
def universities():
    countries = get_all_countries()
    selected_country = None
    universities_list = []

    if request.method == "POST":
        selected_country = request.form.get("country", "")
        if selected_country:
            universities_list = get_universities_by_country(selected_country)
    elif request.method == "GET":
        selected_country = request.args.get("country", "")
        if selected_country:
            universities_list = get_universities_by_country(selected_country)

    username = session.get("username", "")
    display_name = REGISTERED_NAMES.get(username, username)
    badge_initial = display_name[0].upper() if display_name else "U"

    return render_template_string(
        UNIVERSITIES_TEMPLATE,
        countries=countries,
        selected_country=selected_country,
        universities=universities_list,
        username=username,
        badge_initial=badge_initial,
    )


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("username", None)
    session["auth_message"] = "You have been logged out."
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "").lower() == "true",
    )
