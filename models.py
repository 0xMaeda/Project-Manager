from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False, index=True)
    role = db.Column(db.String(50), default="engineer")  # engineer, programmer, operator, manager, admin
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Flask-Login integration
    def get_id(self):
        return str(self.id)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    type = db.Column(db.String(80))
    status = db.Column(db.String(30), default="available")  # available, down, setup, offline
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    customer = db.Column(db.String(120))
    rev = db.Column(db.String(20))
    due_date = db.Column(db.Date)
    priority = db.Column(db.Integer, default=3)  # 1 hot .. 5 low
    status = db.Column(db.String(30), default="active")
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship('Task', backref='project', lazy=True, cascade="all, delete-orphan")

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    state = db.Column(db.String(30), default="backlog")  # backlog, ready, in_progress, blocked, review, done
    priority = db.Column(db.Integer, default=3)
    est_hours = db.Column(db.Float, default=0)
    due_date = db.Column(db.Date)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assignments = db.relationship('TaskAssignment', backref='task', lazy=True, cascade="all, delete-orphan")

class TaskAssignment(db.Model):
    __table_args__ = (db.UniqueConstraint('task_id','user_id', name='uq_task_user'),)
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    machine_id = db.Column(db.Integer, db.ForeignKey('machine.id'))
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', lazy=True)
    machine = db.relationship('Machine', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', lazy=True)

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50))  # e.g., 'task', 'project'
    entity_id = db.Column(db.Integer)
    action = db.Column(db.String(50))       # e.g., 'create', 'update', 'delete', 'comment'
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    diff = db.Column(db.Text)               # JSON string
    at = db.Column(db.DateTime, default=datetime.utcnow)

def to_date(s):
    if not s:
        return None
    if isinstance(s, date):
        return s
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        try:
            return datetime.strptime(s, "%m/%d/%Y").date()
        except Exception:
            return None
