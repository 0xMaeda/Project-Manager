import os, json, argparse, io
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit
from io import StringIO
import csv

from models import db, User, Machine, Project, Task, TaskAssignment, Audit, Comment, to_date

# ----------------------
# App & Config
# ----------------------
load_dotenv()
def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    db_url = os.getenv("DATABASE_URL", "sqlite:///machine_shop.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # Auth
    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # SocketIO
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

    # ------------- Routes -------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for("dashboard"))
            flash("Invalid credentials", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        # Optional per-user filter
        try:
            filter_user_id = int(request.args.get('user')) if request.args.get('user') else None
        except Exception:
            filter_user_id = None

        # Load tasks & assignments for Kanban (optionally filtered by user)
        base_q = Task.query.join(Project).filter(Project.status != "archived")
        if filter_user_id:
            base_q = base_q.join(TaskAssignment).filter(TaskAssignment.user_id == filter_user_id)
        tasks = base_q.all()

        assignments = {}
        for t in tasks:
            assignments[t.id] = TaskAssignment.query.filter_by(task_id=t.id).all()
        # For workload widget (est hours per user, for open tasks)
        open_tasks = [t for t in tasks if t.state != "done"]
        workload = {}
        for t in open_tasks:
            tas = TaskAssignment.query.filter_by(task_id=t.id).all()
            for ta in tas:
                if ta.user:
                    workload.setdefault(ta.user.name, 0.0)
                    workload[ta.user.name] += (t.est_hours or 0.0)
        # Due soon (3 days)
        today = date.today()
        due_soon = Task.query.filter(Task.due_date != None, Task.due_date <= today + timedelta(days=3), Task.state != "done").order_by(Task.due_date.asc()).limit(20).all()
        blocked = Task.query.filter_by(state="blocked").order_by(Task.priority.asc()).all()

        users = User.query.order_by(User.name.asc()).all()
        # --- Project progress for initial render ---
        projects_all = Project.query.order_by(Project.created_at.desc()).all()
        progress = []
        for p in projects_all:
            total = len(p.tasks)
            done = sum(1 for t in p.tasks if t.state == "done")
            pct = int(round((done / total) * 100)) if total else 0
            progress.append({
                "id": p.id,
                "code": p.code,
                "title": p.title,
                "done": done,
                "total": total,
                "pct": pct,
            })

        return render_template("dashboard.html", tasks=tasks, assignments=assignments, workload=workload, due_soon=due_soon, blocked=blocked, users=users, filter_user_id=filter_user_id, progress=progress)
        
    @app.route("/dashboard/widgets")
    @login_required
    def dashboard_widgets():
        # same filtering logic as dashboard
        try:
            filter_user_id = int(request.args.get('user')) if request.args.get('user') else None
        except Exception:
            filter_user_id = None
        base_q = Task.query.join(Project).filter(Project.status != "archived")
        if filter_user_id:
            base_q = base_q.join(TaskAssignment).filter(TaskAssignment.user_id == filter_user_id)
        tasks = base_q.all()

        # assignments (for avatar initials in blocked list if needed)
        assignments = {}
        for t in tasks:
            assignments[t.id] = TaskAssignment.query.filter_by(task_id=t.id).all()

        # workload from open tasks only
        open_tasks = [t for t in tasks if t.state != "done"]
        workload = {}
        for t in open_tasks:
            tas = TaskAssignment.query.filter_by(task_id=t.id).all()
            for ta in tas:
                if ta.user:
                    workload.setdefault(ta.user.name, 0.0)
                    workload[ta.user.name] += (t.est_hours or 0.0)

        # due soon / blocked
        from datetime import date, timedelta
        today = date.today()
        due_soon = Task.query.filter(Task.due_date != None, Task.due_date <= today + timedelta(days=3), Task.state != "done").order_by(Task.due_date.asc()).limit(20).all()
        blocked = Task.query.filter_by(state="blocked").order_by(Task.priority.asc()).all()

        return render_template("_dashboard_widgets.html", due_soon=due_soon, blocked=blocked, filter_user_id=filter_user_id)


    @app.route("/projects", methods=["GET", "POST"])
    @login_required
    def projects():
        if request.method == "POST":
            code = request.form.get("code").strip()
            title = request.form.get("title").strip()
            customer = request.form.get("customer", "").strip()
            rev = request.form.get("rev", "").strip()
            due_date = to_date(request.form.get("due_date"))
            priority = int(request.form.get("priority") or 3)
            p = Project(code=code, title=title, customer=customer, rev=rev, due_date=due_date, priority=priority, created_by=current_user.id)
            db.session.add(p)
            db.session.commit()
            _audit("project", p.id, "create", {"code": code, "title": title})
            return redirect(url_for("projects"))
        items = Project.query.order_by(Project.created_at.desc()).all()
        return render_template("projects.html", projects=items)

    @app.route("/projects/<int:pid>", methods=["GET", "POST"])
    @login_required
    def project_detail(pid):
        p = db.session.get(Project, pid)
        if not p:
            flash("Project not found", "error")
            return redirect(url_for("projects"))
        if request.method == "POST":
            # Create a task
            title = request.form.get("title").strip()
            description = request.form.get("description", "").strip()
            state = request.form.get("state", "backlog")
            priority = int(request.form.get("priority") or 3)
            est_hours = float(request.form.get("est_hours") or 0.0)
            due_date = to_date(request.form.get("due_date"))
            t = Task(project_id=p.id, title=title, description=description, state=state, priority=priority, est_hours=est_hours, due_date=due_date, created_by=current_user.id)
            db.session.add(t)
            db.session.commit()
            _audit("task", t.id, "create", {"title": title, "project_id": p.id})
            return redirect(url_for("project_detail", pid=pid))

        tasks = Task.query.filter_by(project_id=p.id).order_by(Task.created_at.desc()).all()
        users = User.query.order_by(User.name.asc()).all()
        machines = Machine.query.order_by(Machine.name.asc()).all()
        return render_template("project_detail.html", project=p, tasks=tasks, users=users, machines=machines)

    @app.route("/tasks/<int:tid>", methods=["PATCH", "POST"])
    @login_required
    def update_task(tid):
        t = db.session.get(Task, tid)
        if not t:
            return "Not Found", 404
        old = {"state": t.state, "priority": t.priority, "due_date": str(t.due_date) if t.due_date else None, "title": t.title}
        if request.method == "PATCH":
            data = request.get_json(force=True, silent=True) or {}
            changed = {}
            if "state" in data:
                t.state = data["state"]
                changed["state"] = t.state
            if "priority" in data:
                t.priority = int(data["priority"])
                changed["priority"] = t.priority
            if "title" in data:
                t.title = data["title"]
                changed["title"] = t.title
            if "due_date" in data:
                t.due_date = to_date(data["due_date"])
                changed["due_date"] = str(t.due_date) if t.due_date else None
            db.session.commit()
            _audit("task", t.id, "update", {"before": old, "after": changed})
            socketio.emit("task_updated", {"id": t.id, **changed})
            return "", 204
        else:
            # HTML form submit (edit minimal fields)
            t.title = request.form.get("title", t.title)
            t.state = request.form.get("state", t.state)
            t.priority = int(request.form.get("priority", t.priority))
            t.due_date = to_date(request.form.get("due_date")) or t.due_date
            db.session.commit()
            _audit("task", t.id, "update", {"before": old, "after": {"state": t.state}})
            socketio.emit("task_updated", {"id": t.id, "state": t.state})
            return redirect(request.referrer or url_for("dashboard"))

    @app.route("/tasks/<int:tid>/assign", methods=["POST"])
    @login_required
    def assign_task(tid):
        t = db.session.get(Task, tid)
        if not t: return "Not Found", 404
        # Accept multiple users via 'user_ids' (multi-select) or single 'user_id'
        user_ids = request.form.getlist("user_ids")
        if not user_ids:
            single = request.form.get("user_id")
            if single:
                user_ids = [single]
        machine_id = request.form.get("machine_id")
        created = 0
        for uid in user_ids:
            if not uid:
                continue
            exists = TaskAssignment.query.filter_by(task_id=t.id, user_id=int(uid)).first()
            if not exists:
                ta = TaskAssignment(task_id=t.id, user_id=int(uid), machine_id=int(machine_id) if machine_id else None)
                db.session.add(ta)
                created += 1
        if created:
            db.session.commit()
            _audit("task", t.id, "assign", {"user_ids": user_ids, "machine_id": machine_id})
        return redirect(request.referrer or url_for("project_detail", pid=t.project_id))

    @app.route("/tasks/<int:tid>/assignments/<int:aid>/delete", methods=["POST"])
    @login_required
    def unassign_task(tid, aid):
        t = db.session.get(Task, tid)
        if not t: return "Not Found", 404
        ta = db.session.get(TaskAssignment, aid)
        if not ta or ta.task_id != t.id:
            return "Not Found", 404
        db.session.delete(ta)
        db.session.commit()
        _audit("task", t.id, "unassign", {"assignment_id": aid})
        return redirect(request.referrer or url_for("project_detail", pid=t.project_id))

    @app.route("/users", methods=["GET", "POST"])
    @login_required
    def users():
        if current_user.role not in ("manager", "admin"):
            flash("Only managers/admin can manage users.", "error")
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            name = request.form.get("name").strip()
            email = request.form.get("email").strip().lower()
            role = request.form.get("role", "engineer")
            password = request.form.get("password", "Password")
            u = User(name=name, email=email, role=role, password_hash=generate_password_hash(password))
            db.session.add(u)
            db.session.commit()
            _audit("user", u.id, "create", {"name": name, "email": email, "role": role})
            return redirect(url_for("users"))
        items = User.query.order_by(User.created_at.desc()).all()
        return render_template("users.html", users=items)

    @app.route("/users/<int:uid>/delete", methods=["POST"])
    @login_required
    def delete_user(uid):
        if current_user.role != "admin":
            flash("Only admin can delete users.", "error")
            return redirect(url_for("users"))
        u = db.session.get(User, uid)
        if not u:
            flash("User not found", "error")
            return redirect(url_for("users"))
        if u.id == current_user.id:
            flash("You cannot delete your own account while logged in.", "error")
            return redirect(url_for("users"))
        db.session.delete(u)
        db.session.commit()
        flash(f"User {u.name} deleted", "info")
        _audit("user", uid, "delete", {"id": uid})
        return redirect(url_for("users"))

    @app.route("/projects/<int:pid>/delete", methods=["POST"])
    @login_required
    def delete_project(pid):
        if current_user.role != "admin":
            flash("Only admin can delete projects.", "error")
            return redirect(url_for("projects"))
        p = db.session.get(Project, pid)
        if not p:
            flash("Project not found", "error")
            return redirect(url_for("projects"))
        db.session.delete(p)
        db.session.commit()
        flash(f"Project {p.code} deleted", "info")
        _audit("project", pid, "delete", {"id": pid})
        return redirect(url_for("projects"))

    # -------- Comments --------
    @app.route("/tasks/<int:tid>/comments.json")
    @login_required
    def task_comments_json(tid):
        t = db.session.get(Task, tid)
        if not t:
            return jsonify({"error":"not found"}), 404
        items = Comment.query.filter_by(task_id=tid).order_by(Comment.created_at.asc()).all()
        return jsonify([{
            "id": c.id,
            "user": c.user.name if c.user else "Unknown",
            "body": c.body,
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M")
        } for c in items])

    @app.route("/tasks/<int:tid>/comment", methods=["POST"])
    @login_required
    def task_comment_add(tid):
        t = db.session.get(Task, tid)
        if not t:
            return "Not Found", 404
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Comment cannot be empty.", "error")
            return redirect(request.referrer or url_for("dashboard"))
        c = Comment(task_id=tid, user_id=current_user.id, body=body)
        db.session.add(c)
        db.session.commit()
        _audit("task", tid, "comment", {"by": current_user.id})
        try:
            app.socketio.emit("task_commented", {"task_id": tid, "by": current_user.name, "body": body})
        except Exception:
            pass
        return redirect(request.referrer or url_for("dashboard"))

    @app.route("/export/tasks.csv")
    @login_required
    def export_tasks_csv():
        si = StringIO()
        writer = csv.writer(si, lineterminator='\n')
        writer.writerow(["Project", "Task", "State", "Assignees", "Priority", "Est Hours", "Due Date", "Created"])
        tasks = Task.query.order_by(Task.created_at.desc()).all()
        for t in tasks:
            assignees = ", ".join([ta.user.name for ta in TaskAssignment.query.filter_by(task_id=t.id).all() if ta.user])
            writer.writerow([t.project.code if t.project else "", t.title, t.state, assignees, t.priority, t.est_hours, t.due_date or "", t.created_at.strftime("%Y-%m-%d %H:%M")])
        data = si.getvalue().encode('utf-8')
        bio = io.BytesIO(data)
        bio.seek(0)
        return send_file(
            bio,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"tasks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

    @app.route("/dashboard/progress")
    @login_required
    def dashboard_progress():
        # Compute per-project progress (overall, not filtered by user)
        projs = Project.query.order_by(Project.created_at.desc()).all()
        progress = []
        for p in projs:
            total = len(p.tasks)
            done = sum(1 for t in p.tasks if t.state == "done")
            pct = int(round((done / total) * 100)) if total else 0
            progress.append({
                "id": p.id,
                "code": p.code,
                "title": p.title,
                "done": done,
                "total": total,
                "pct": pct
            })
        return render_template("_dashboard_progress.html", progress=progress)

    @app.route("/dashboard/progress.json")
    @login_required
    def dashboard_progress_json():
        projs = Project.query.order_by(Project.created_at.desc()).all()
        out = []
        for p in projs:
            total = len(p.tasks)
            done = sum(1 for t in p.tasks if t.state == "done")
            pct = int(round((done / total) * 100)) if total else 0
            out.append({"id": p.id, "code": p.code, "title": p.title, "done": done, "total": total, "pct": pct})
        return jsonify(out)

    @app.route("/dashboard/workload")
    @login_required
    def dashboard_workload():
        # respect user filter if present
        try:
            filter_user_id = int(request.args.get('user')) if request.args.get('user') else None
        except Exception:
            filter_user_id = None

        base_q = Task.query.join(Project).filter(Project.status != "archived")
        if filter_user_id:
            base_q = base_q.join(TaskAssignment).filter(TaskAssignment.user_id == filter_user_id)
        tasks = base_q.all()

        # Open tasks only for workload
        open_tasks = [t for t in tasks if t.state != "done"]

        # Hours + Count per user
        workload_hours = {}
        workload_counts = {}
        for t in open_tasks:
            tas = TaskAssignment.query.filter_by(task_id=t.id).all()
            for ta in tas:
                if ta.user:
                    name = ta.user.name
                    workload_hours[name] = workload_hours.get(name, 0.0) + (t.est_hours or 0.0)
                    workload_counts[name] = workload_counts.get(name, 0) + 1

        # Sort by hours desc
        items = sorted(workload_hours.items(), key=lambda kv: kv[1], reverse=True)
        rows = [(name, workload_counts.get(name, 0), hrs) for name, hrs in items]
        return render_template("_dashboard_workload.html", workload_rows=rows, filter_user_id=filter_user_id)

    # ------------- Helpers -------------
    def _audit(entity_type, entity_id, action, diff_dict):
        a = Audit(entity_type=entity_type, entity_id=entity_id, action=action,
                  actor_id=current_user.id if current_user.is_authenticated else None,
                  diff=json.dumps(diff_dict))
        db.session.add(a)
        db.session.commit()

    # Expose socketio on app for run()
    app.socketio = socketio
    return app

# ----------------------
# CLI helpers
# ----------------------
def init_db(app):
    with app.app_context():
        db.drop_all()
        db.create_all()

def seed_demo(app):
    from werkzeug.security import generate_password_hash
    with app.app_context():
        admin = User(name="Admin", email="admin@example.com", role="admin", password_hash=generate_password_hash("Password"))
        eng = User(name="Alex Eng", email="alex@example.com", role="engineer", password_hash=generate_password_hash("Password"))
        prog = User(name="Sam Prog", email="sam@example.com", role="programmer", password_hash=generate_password_hash("Password"))
        db.session.add_all([admin, eng, prog])

        m1 = Machine(name="Haas VF2", type="Mill", status="available")
        m2 = Machine(name="Mazak QT-200", type="Lathe", status="available")
        db.session.add_all([m1, m2])

        p1 = Project(code="JOB-1001", title="Bracket Assembly Rev A", customer="Acme", rev="A", priority=2, due_date=date.today()+timedelta(days=5), created_by=1)
        p2 = Project(code="JOB-1002", title="Manifold Block Rev B", customer="Globex", rev="B", priority=1, due_date=date.today()+timedelta(days=2), created_by=1)
        db.session.add_all([p1, p2])
        db.session.flush()

        t1 = Task(project_id=p1.id, title="Program OP10", description="Facing + drill", state="ready", priority=2, est_hours=3.5, due_date=date.today()+timedelta(days=2), created_by=1)
        t2 = Task(project_id=p1.id, title="Fixture design", description="3-jaw soft jaws", state="in_progress", priority=1, est_hours=6, due_date=date.today()+timedelta(days=3), created_by=1)
        t3 = Task(project_id=p2.id, title="Post-process NC", description="Verify tool numbers", state="blocked", priority=1, est_hours=2, due_date=date.today()+timedelta(days=1), created_by=1)
        t4 = Task(project_id=p2.id, title="QC first article", description="Check CMM program", state="backlog", priority=3, est_hours=4, due_date=date.today()+timedelta(days=6), created_by=1)
        db.session.add_all([t1, t2, t3, t4])
        db.session.flush()

        db.session.add_all([
            TaskAssignment(task_id=t1.id, user_id=2, machine_id=m1.id),
            TaskAssignment(task_id=t2.id, user_id=3, machine_id=m1.id),
            TaskAssignment(task_id=t3.id, user_id=3, machine_id=m2.id),
        ])
        db.session.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--initdb", action="store_true", help="Drop & create tables")
    parser.add_argument("--seed", action="store_true", help="Seed demo data")
    args = parser.parse_args()

    app = create_app()
    if args.initdb:
        init_db(app)
    if args.seed:
        seed_demo(app)

    # Run with eventlet for Socket.IO
    app.socketio.run(app, host="0.0.0.0", port=5000, debug=True)


