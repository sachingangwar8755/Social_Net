import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_UPLOAD_SIZE = 2 * 1024 * 1024

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-this-secret-key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    bio TEXT DEFAULT '',
    profile_picture TEXT NOT NULL DEFAULT 'default-avatar.svg',
    is_blocked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS friend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','accepted','rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_request
ON friend_requests(sender_id, receiver_id)
WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS friendships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    friend_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, friend_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS favourites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    favourite_user_id INTEGER NOT NULL,
    UNIQUE(user_id, favourite_user_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(favourite_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL
);
"""

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    con = get_db()
    con.executescript(SCHEMA)

    if con.execute("SELECT COUNT(*) FROM admin").fetchone()[0] == 0:
        con.execute(
            "INSERT INTO admin(username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123"))
        )

    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        for i in range(1, 11):
            con.execute(
                """INSERT INTO users(name, username, email, password_hash, bio)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    f"Demo User {i}",
                    f"user{i:02d}",
                    f"user{i:02d}@example.com",
                    generate_password_hash("user123"),
                    "Demo SocialNet user"
                )
            )
    con.commit()
    con.close()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            flash("Admin login required.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user(user_id):
    con = get_db()
    user = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    con.close()
    return user

def relationship_status(con, me, other):
    if me == other:
        return "self"
    row = con.execute(
        """SELECT 1 FROM friendships
           WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)
           LIMIT 1""", (me, other, other, me)
    ).fetchone()
    if row:
        return "friends"
    row = con.execute(
        """SELECT 1 FROM friend_requests
           WHERE sender_id=? AND receiver_id=? AND status='pending'""",
        (me, other)
    ).fetchone()
    if row:
        return "pending_sent"
    row = con.execute(
        """SELECT 1 FROM friend_requests
           WHERE sender_id=? AND receiver_id=? AND status='pending'""",
        (other, me)
    ).fetchone()
    if row:
        return "pending_received"
    return "none"

@app.context_processor
def common_context():
    pending = 0
    if "user_id" in session:
        con = get_db()
        pending = con.execute(
            "SELECT COUNT(*) FROM friend_requests WHERE receiver_id=? AND status='pending'",
            (session["user_id"],)
        ).fetchone()[0]
        con.close()
    return {"pending_count": pending, "logged_in": "user_id" in session}

@app.route("/")
def home():
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not all([name, username, email, password, confirm]):
            flash("All fields are required.", "error")
            return render_template("register.html")
        if len(username) < 3 or " " in username:
            flash("Username must be at least 3 characters and contain no spaces.", "error")
            return render_template("register.html")
        if "@" not in email or "." not in email.split("@")[-1]:
            flash("Please enter a valid email address.", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        con = get_db()
        try:
            if con.execute("SELECT 1 FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone():
                flash("That username is already taken. Choose another.", "error")
                return render_template("register.html")
            if con.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone():
                flash("An account with that email already exists.", "error")
                return render_template("register.html")

            con.execute(
                """INSERT INTO users(name, username, email, password_hash)
                   VALUES (?, ?, ?, ?)""",
                (name, username, email, generate_password_hash(password))
            )
            con.commit()
        except sqlite3.Error:
            con.rollback()
            flash("Registration could not be completed. Please try again.", "error")
            return render_template("register.html")
        finally:
            con.close()

        flash("Registration successful! Login with your username and password.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        con = get_db()
        user = con.execute(
            "SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)
        ).fetchone()
        con.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return render_template("login.html")
        if user["is_blocked"]:
            flash("This account is blocked by the administrator.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["user_name"] = user["name"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    con = get_db()
    me = con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    friends = con.execute(
        """SELECT u.* FROM users u JOIN friendships f ON f.friend_id=u.id
           WHERE f.user_id=? ORDER BY u.name""", (session["user_id"],)
    ).fetchall()
    favourites = con.execute(
        """SELECT u.* FROM users u JOIN favourites f ON f.favourite_user_id=u.id
           WHERE f.user_id=? ORDER BY u.name""", (session["user_id"],)
    ).fetchall()
    con.close()
    return render_template("dashboard.html", user=me, friends=friends, favourites=favourites)

@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        con = get_db()
        rows = con.execute(
            """SELECT id,name,username,email,profile_picture,bio FROM users
               WHERE id != ? AND is_blocked=0
               AND (name LIKE ? OR username LIKE ? OR email LIKE ?)
               ORDER BY name LIMIT 50""",
            (session["user_id"], f"%{q}%", f"%{q}%", f"%{q}%")
        ).fetchall()
        for row in rows:
            item = dict(row)
            item["status"] = relationship_status(con, session["user_id"], row["id"])
            results.append(item)
        con.close()
    return render_template("search.html", query=q, results=results)

@app.route("/requests")
@login_required
def requests_page():
    uid = session["user_id"]
    con = get_db()
    incoming = con.execute(
        """SELECT fr.id AS request_id,u.id,u.name,u.username,u.profile_picture
           FROM friend_requests fr JOIN users u ON u.id=fr.sender_id
           WHERE fr.receiver_id=? AND fr.status='pending'
           ORDER BY fr.id DESC""", (uid,)
    ).fetchall()
    sent = con.execute(
        """SELECT fr.id AS request_id,u.id,u.name,u.username,u.profile_picture
           FROM friend_requests fr JOIN users u ON u.id=fr.receiver_id
           WHERE fr.sender_id=? AND fr.status='pending'
           ORDER BY fr.id DESC""", (uid,)
    ).fetchall()
    con.close()
    return render_template("requests.html", incoming=incoming, sent=sent)

@app.post("/requests/send/<int:receiver_id>")
@login_required
def send_request(receiver_id):
    uid = session["user_id"]
    con = get_db()
    target = con.execute("SELECT id FROM users WHERE id=? AND is_blocked=0", (receiver_id,)).fetchone()
    if not target or receiver_id == uid:
        flash("Invalid user.", "error")
    elif relationship_status(con, uid, receiver_id) == "friends":
        flash("You are already friends.", "error")
    elif relationship_status(con, uid, receiver_id) in ("pending_sent", "pending_received"):
        flash("A friend request already exists.", "error")
    else:
        con.execute(
            "INSERT INTO friend_requests(sender_id,receiver_id,status) VALUES(?,?, 'pending')",
            (uid, receiver_id)
        )
        con.commit()
        flash("Friend request sent.", "success")
    con.close()
    return redirect(request.referrer or url_for("search"))

@app.post("/requests/cancel/<int:receiver_id>")
@login_required
def cancel_request(receiver_id):
    con = get_db()
    con.execute(
        "DELETE FROM friend_requests WHERE sender_id=? AND receiver_id=? AND status='pending'",
        (session["user_id"], receiver_id)
    )
    con.commit()
    con.close()
    flash("Friend request canceled.", "success")
    return redirect(request.referrer or url_for("requests_page"))

@app.post("/requests/accept/<int:request_id>")
@login_required
def accept_request(request_id):
    uid = session["user_id"]
    con = get_db()
    row = con.execute(
        """SELECT sender_id,receiver_id FROM friend_requests
           WHERE id=? AND receiver_id=? AND status='pending'""", (request_id, uid)
    ).fetchone()
    if not row:
        flash("Request not found.", "error")
    else:
        sender = row["sender_id"]
        con.execute("UPDATE friend_requests SET status='accepted' WHERE id=?", (request_id,))
        con.execute("INSERT OR IGNORE INTO friendships(user_id,friend_id) VALUES(?,?)", (sender, uid))
        con.execute("INSERT OR IGNORE INTO friendships(user_id,friend_id) VALUES(?,?)", (uid, sender))
        con.commit()
        flash("Friend request accepted.", "success")
    con.close()
    return redirect(url_for("requests_page"))

@app.post("/requests/reject/<int:request_id>")
@login_required
def reject_request(request_id):
    con = get_db()
    con.execute(
        "UPDATE friend_requests SET status='rejected' WHERE id=? AND receiver_id=? AND status='pending'",
        (request_id, session["user_id"])
    )
    con.commit()
    con.close()
    flash("Friend request rejected.", "success")
    return redirect(url_for("requests_page"))

@app.route("/friends")
@login_required
def friends():
    uid = session["user_id"]
    con = get_db()
    friends_list = con.execute(
        """SELECT u.* FROM users u JOIN friendships f ON f.friend_id=u.id
           WHERE f.user_id=? ORDER BY u.name""", (uid,)
    ).fetchall()
    fav_ids = {r["favourite_user_id"] for r in con.execute(
        "SELECT favourite_user_id FROM favourites WHERE user_id=?", (uid,)
    ).fetchall()}
    con.close()
    return render_template("friends.html", friends=friends_list, fav_ids=fav_ids)

@app.post("/friends/remove/<int:friend_id>")
@login_required
def remove_friend(friend_id):
    uid = session["user_id"]
    con = get_db()
    con.execute(
        """DELETE FROM friendships
           WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)""",
        (uid, friend_id, friend_id, uid)
    )
    con.execute(
        """DELETE FROM favourites
           WHERE (user_id=? AND favourite_user_id=?) OR (user_id=? AND favourite_user_id=?)""",
        (uid, friend_id, friend_id, uid)
    )
    con.commit()
    con.close()
    flash("Friend removed.", "success")
    return redirect(url_for("friends"))

@app.post("/favourites/add/<int:user_id>")
@login_required
def add_favourite(user_id):
    con = get_db()
    if user_id != session["user_id"]:
        con.execute("INSERT OR IGNORE INTO favourites(user_id,favourite_user_id) VALUES(?,?)",
                    (session["user_id"], user_id))
        con.commit()
    con.close()
    return redirect(request.referrer or url_for("friends"))

@app.post("/favourites/remove/<int:user_id>")
@login_required
def remove_favourite(user_id):
    con = get_db()
    con.execute("DELETE FROM favourites WHERE user_id=? AND favourite_user_id=?",
                (session["user_id"], user_id))
    con.commit()
    con.close()
    return redirect(request.referrer or url_for("friends"))

@app.route("/user/<int:user_id>")
@login_required
def view_user(user_id):
    con = get_db()
    other = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not other:
        con.close()
        flash("User not found.", "error")
        return redirect(url_for("search"))
    status = relationship_status(con, session["user_id"], user_id)
    mutual = con.execute(
        """SELECT u.* FROM users u
           JOIN friendships f1 ON f1.friend_id=u.id AND f1.user_id=?
           JOIN friendships f2 ON f2.friend_id=u.id AND f2.user_id=?
           WHERE u.id NOT IN (?,?)""",
        (session["user_id"], user_id, session["user_id"], user_id)
    ).fetchall()
    con.close()
    return render_template("view_user.html", other=other, status=status, mutual=mutual)

@app.route("/chat/<int:user_id>")
@login_required
def chat(user_id):
    uid = session["user_id"]
    con = get_db()
    other = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not other or user_id == uid:
        con.close()
        flash("User not found.", "error")
        return redirect(url_for("friends"))
    friends_list = con.execute(
        """SELECT u.* FROM users u JOIN friendships f ON f.friend_id=u.id
           WHERE f.user_id=? ORDER BY u.name""", (uid,)
    ).fetchall()
    messages = con.execute(
        """SELECT * FROM messages
           WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
           ORDER BY id""", (uid,user_id,user_id,uid)
    ).fetchall()
    con.close()
    return render_template("chat.html", other=other, friends=friends_list, messages=messages, uid=uid)

@app.post("/send-message")
@login_required
def send_message():
    receiver_id = request.form.get("receiver_id", type=int)
    message = request.form.get("message", "").strip()
    if not receiver_id or not message:
        return redirect(url_for("friends"))
    if len(message) > 2000:
        flash("Message is too long.", "error")
        return redirect(url_for("chat", user_id=receiver_id))
    con = get_db()
    exists = con.execute("SELECT id FROM users WHERE id=?", (receiver_id,)).fetchone()
    if exists and receiver_id != session["user_id"]:
        con.execute(
            "INSERT INTO messages(sender_id,receiver_id,message) VALUES(?,?,?)",
            (session["user_id"], receiver_id, message)
        )
        con.commit()
    con.close()
    return redirect(url_for("chat", user_id=receiver_id))

@app.route("/profile")
@login_required
def profile():
    uid = session["user_id"]
    con = get_db()
    user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    friends_count = con.execute("SELECT COUNT(*) FROM friendships WHERE user_id=?", (uid,)).fetchone()[0]
    fav_count = con.execute("SELECT COUNT(*) FROM favourites WHERE user_id=?", (uid,)).fetchone()[0]
    con.close()
    return render_template("profile.html", user=user, friends_count=friends_count, fav_count=fav_count)

@app.post("/profile/edit")
@login_required
def edit_profile():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    bio = request.form.get("bio", "").strip()
    if not name or not email:
        flash("Name and email are required.", "error")
        return redirect(url_for("profile"))
    con = get_db()
    duplicate = con.execute(
        "SELECT id FROM users WHERE email=? COLLATE NOCASE AND id!=?", (email, session["user_id"])
    ).fetchone()
    if duplicate:
        flash("That email is already used by another account.", "error")
    else:
        con.execute("UPDATE users SET name=?,email=?,bio=? WHERE id=?",
                    (name,email,bio,session["user_id"]))
        con.commit()
        session["user_name"] = name
        flash("Profile updated successfully.", "success")
    con.close()
    return redirect(url_for("profile"))

@app.post("/profile/password")
@login_required
def change_password():
    old = request.form.get("old_password", "")
    new = request.form.get("new_password", "")
    con = get_db()
    user = con.execute("SELECT password_hash FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not check_password_hash(user["password_hash"], old):
        flash("Current password is incorrect.", "error")
    elif len(new) < 6:
        flash("New password must be at least 6 characters.", "error")
    else:
        con.execute("UPDATE users SET password_hash=? WHERE id=?",
                    (generate_password_hash(new), session["user_id"]))
        con.commit()
        flash("Password changed successfully.", "success")
    con.close()
    return redirect(url_for("profile"))

@app.post("/profile/photo")
@login_required
def upload_photo():
    file = request.files.get("profile_picture")
    if not file or not file.filename:
        flash("Please select an image.", "error")
        return redirect(url_for("profile"))
    if not allowed_file(file.filename):
        flash("Allowed image types: PNG, JPG, JPEG, GIF, WEBP.", "error")
        return redirect(url_for("profile"))

    ext = secure_filename(file.filename).rsplit(".", 1)[-1].lower()
    filename = f"user_{session['user_id']}.{ext}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    con = get_db()
    con.execute("UPDATE users SET profile_picture=? WHERE id=?", (filename, session["user_id"]))
    con.commit()
    con.close()
    flash("Profile picture updated.", "success")
    return redirect(url_for("profile"))

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        con = get_db()
        admin = con.execute("SELECT * FROM admin WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        con.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin username or password.", "error")
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    con = get_db()
    users = con.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    stats = {
        "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "pending": con.execute("SELECT COUNT(*) FROM friend_requests WHERE status='pending'").fetchone()[0],
        "friendships": con.execute("SELECT COUNT(*) FROM friendships").fetchone()[0] // 2,
        "favourites": con.execute("SELECT COUNT(*) FROM favourites").fetchone()[0],
    }
    requests = con.execute(
        """SELECT fr.*,s.username sender,r.username receiver
           FROM friend_requests fr
           JOIN users s ON s.id=fr.sender_id
           JOIN users r ON r.id=fr.receiver_id
           ORDER BY fr.id DESC LIMIT 100"""
    ).fetchall()
    con.close()
    return render_template("admin_dashboard.html", users=users, stats=stats, requests=requests)

@app.post("/admin/block/<int:user_id>")
@admin_required
def admin_block(user_id):
    con = get_db()
    con.execute("UPDATE users SET is_blocked=CASE is_blocked WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (user_id,))
    con.commit()
    con.close()
    flash("User block status updated.", "success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/delete/<int:user_id>")
@admin_required
def admin_delete(user_id):
    con = get_db()
    con.execute("DELETE FROM users WHERE id=?", (user_id,))
    con.commit()
    con.close()
    flash("User deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(413)
def too_large(error):
    flash("Image is too large. Maximum size is 2 MB.", "error")
    return redirect(url_for("profile"))

if __name__ == "__main__":
    init_db()
    print("\nSocial Network Friend Management System")
    print("User demo: user01 / user123")
    print("Admin demo: admin / admin123")
    print("Open: http://127.0.0.1:5000\n")
    app.run(debug=True)
