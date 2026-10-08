# SMART CHILD ADOPTION SUPPORT & FAMILY MATCHING PLATFORM
**CO9 Mini Project:** Design and develop a mini project using GPT-based AI tools for real-world applications.

---

## 📌 Project Overview
The **Smart Child Adoption Support & Family Matching Platform** is an educational full-stack web application designed to address administrative transparency challenges in child adoption procedures (inspired by platforms such as CARINGS).

> **Educational Prototype Disclaimer:**  
> This platform is strictly an educational prototype designed to demonstrate AI-assisted workflow guidance and transparent administrative tracking. It does **NOT** replace CARA/CARINGS, authorized adoption agencies, legal courts, or official child welfare authorities.

---

## 🚀 Key Features

- **Role-Based Portals & Dashboards**:
  1. **Adopter Dashboard**: Transparent 7-stage adoption journey tracking, profile & family preference management, verified adoption trusts directory, and bilingual AI Assistant.
  2. **Trust Agency Dashboard**: Manage adopter requests, view applicant family profiles, trigger real-time approval email dispatches, and update journey milestones.
  3. **Admin Dashboard**: System administration, trust verification/moderation (Verify, Reject, Suspend), and platform activity monitoring.
- **GPT-Based AI Agent**:
  - Context-aware assistance reading MongoDB user profile, active request, chosen trust, journey stage, notifications, and email logs.
  - Strict **Trustworthy AI Rules**: No legal decisions, no ranking of children, no child profile displays, no discriminatory evaluations, and neutral process guidance.
  - **Bilingual Support**: English & Tamil (தமிழ்) toggle for explanations and process answers.
- **Real-Time Automated Email Workflow**:
  - **SMTP Integration**: Dispatches instant registration confirmation and trust approval notifications directly to adopters' registered email addresses.
  - **IMAP Integration**: Reads and retrieves trust-related email updates.
- **Modern Pink UI Theme**:
  - Fixed Charcoal/Dark Navy Sidebar (`#111827`), Primary Soft Pink Accents (`#E8A0BF`), Pale Pink Highlights (`#FCE7F3`), and white card-based dashboard layout.

---

## 🛠 Technology Stack

- **Backend**: Python 3.14+, Flask
- **Database**: MongoDB (PyMongo with automatic in-memory fallback for zero-configuration execution)
- **Frontend**: HTML5, CSS3, JavaScript (ES6), Bootstrap 5, FontAwesome 6 Icons
- **AI Integration**: OpenAI API (`gpt-3.5-turbo`) with structured system prompts & context injection
- **Email Communications**: Python `smtplib`, `imaplib`, `email`
- **Authentication**: Flask session-based authentication with Werkzeug password hashing

---

## 📁 Project Directory Structure

```
smart_adoption_platform/
│
├── app.py                      # Flask application factory and entrypoint
├── config.py                   # Environment configuration loader
├── requirements.txt            # Python dependencies
├── .env.example                # Template for environment variables
├── .env                        # Local environment settings
├── README.md                   # Comprehensive documentation
│
├── database/
│   ├── __init__.py
│   └── mongodb.py              # MongoDB & MongoMock fallback connection layer
│
├── utils/
│   ├── __init__.py
│   ├── auth.py                 # Password hashing & session management helpers
│   └── decorators.py           # Role-based protection middleware (@adopter_required, etc.)
│
├── services/
│   ├── __init__.py
│   ├── ai_agent.py             # GPT AI Agent & Trustworthy AI safety logic
│   ├── email_service.py        # SMTP real-time email sending & IMAP email reading
│   └── notification_service.py # In-app notification management
│
├── routes/
│   ├── __init__.py
│   ├── auth.py                 # Login, Registration, Logout routes
│   ├── adopter.py              # Adopter dashboard, profile, trusts, journey, AI routes
│   ├── trust.py                # Trust portal dashboard, requests, applications routes
│   ├── admin.py                # Admin dashboard, verification, monitoring routes
│   ├── ai.py                   # AI Agent REST endpoint
│   └── notifications.py        # Notification badge REST endpoint
│
├── templates/
│   ├── base.html               # Master layout with dark sidebar and top header
│   ├── index.html              # Landing page
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── adopter/
│   │   ├── dashboard.html
│   │   ├── profile.html
│   │   ├── trusts.html
│   │   ├── journey.html
│   │   └── ai_assistant.html
│   ├── trust/
│   │   ├── dashboard.html
│   │   ├── profile.html
│   │   ├── requests.html
│   │   └── applications.html
│   └── admin/
│       ├── dashboard.html
│       ├── profile.html
│       ├── trust_verification.html
│       └── monitoring.html
│
├── static/
│   ├── css/
│   │   └── style.css          # Custom Pink Color Theme & Dashboard Layout CSS
│   ├── js/
│   │   ├── main.js             # General UI interactivity & notification badge JS
│   │   └── ai.js               # AI Assistant interactive chat JS
│   └── images/
│
└── seed/
    └── seed_data.py            # Database seeding script for sample accounts & trusts
```

---

## ⚙️ Environment Variables Setup

Create a `.env` file in the root directory (or use `.env.example`):

```ini
MONGO_URI=mongodb://localhost:27017/smart_adoption
MONGO_DB_NAME=smart_adoption

OPENAI_API_KEY=your_openai_api_key_here

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com

IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_app_password

SECRET_KEY=smart_child_adoption_secret_key_2026_dev
```

---

## ⚡ How to Run the Application (Windows PowerShell)

1. **Navigate to project folder**:
   ```powershell
   cd C:\Users\91812\.gemini\antigravity\scratch\smart_adoption_platform
   ```

2. **Create and Activate Virtual Environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

4. **Seed Database**:
   ```powershell
   python seed/seed_data.py
   ```

5. **Start Flask Application**:
   ```powershell
   python app.py
   ```

6. **Open in Web Browser**:
   Navigate to [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

---

## 🔑 Demo Accounts & Credentials

| Role | Email | Password | Details |
| :--- | :--- | :--- | :--- |
| **Adopter** | `user@example.com` | `User@123` | Applicant: Ajitha D R (Madurai, Tamil/English) |
| **Trust Agency** | `trust.abc@smartadoption.org` | `Trust@123` | ABC Adoption Trust (Madurai, Verified) |
| **Trust Agency** | `trust.hope@smartadoption.org` | `Trust@123` | Hope Adoption Trust (Chennai, Verified) |
| **Pending Trust**| `trust.sunshine@smartadoption.org` | `Trust@123` | Sunshine Child Care Trust (Pending Verification) |
| **Admin** | `admin@smartadoption.org` | `Admin@123` | System Administrator |

---

## 📋 Required Demo Flow Walkthrough

### DEMO 1: Registration & Instant Email Notification
1. Open `/register` as **Adopter**.
2. Enter Name, Email, Password, Phone, Address.
3. Upon registration, user is stored in MongoDB, in-app notification is generated, and an automated SMTP welcome email is sent to the registered email.

### DEMO 2: Trust Selection & Adoption Request
1. Log in as **Adopter** (`user@example.com`).
2. Go to **Profile Management** to inspect preferences.
3. Open **Verified Trusts Directory** and view available verified trusts in Madurai or Chennai.
4. Click **[Choose Trust & Send Request]**.
5. The request is created in MongoDB (`request_id: ADP1024`), and the journey timeline updates to `TRUST_REVIEW`.

### DEMO 3: Trust Handler Approval Workflow
1. Log in as **Trust Agency** (`trust.abc@smartadoption.org`).
2. Open **Adopter Requests**.
3. Locate request `ADP1024` from Ajitha D R.
4. Click **[APPROVE]**.
5. Flask backend updates MongoDB status to `APPROVED`, updates journey stage to `APPROVED`, generates notification, and dispatches real-time SMTP approval email immediately.

### DEMO 4: Adoption Journey Timeline
1. Log in as **Adopter**.
2. Open **My Adoption Journey**.
3. Observe the highlighted 7-stage visual timeline showing `APPROVED` highlighted in pink with complete timestamp details.

### DEMO 5 & 6: AI Adoption Assistant Context-Aware Guidance
1. Open **AI Adoption Assistant**.
2. Select language toggle (**English** or **தமிழ்**).
3. Ask: *"What is my current status?"*
4. AI Agent reads MongoDB context and explains the current `APPROVED` stage.
5. Ask: *"Did I receive any update from my trust?"*
6. AI Agent checks recent email/notification logs and summarizes the approval update.

---

## 🛡 AI Safety & Compliance Rules

The AI Agent strictly adheres to CO9 Trustworthy AI principles:
- Does **NOT** make legal eligibility decisions or approve/reject adoption cases.
- Does **NOT** display private child profiles, child photos, or rank children.
- Does **NOT** discriminate on caste, religion, gender, or socio-economic criteria.
- Always advises users when official confirmation with authorized adoption trusts is required.
