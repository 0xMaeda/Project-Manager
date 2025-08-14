# Machine Shop Project Tracker (Flask)

A compact, production-grade starter for tracking projects, tasks, and assignments in a machine-shop engineering/programming department. Includes a Kanban dashboard with drag-and-drop, multi-user updates via Socket.IO, CSV export, and simple role-aware auth.

## Quick start

```bash
# 1) Create & activate a virtualenv (recommended)
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) (Optional) Configure env
cp .env.example .env

# 4) Initialize the database and seed demo data
python app.py --initdb --seed

# 5) Run the server (eventlet for Socket.IO)
python app.py
# Then open http://127.0.0.1:5000
```

**Default demo login:**  
- Email: `admin@example.com`  
- Password: `Password` (case-sensitive)

> ⚠️ For production: set a strong `SECRET_KEY`, use Postgres, put the app behind nginx + gunicorn, and disable the `--initdb` flag.
