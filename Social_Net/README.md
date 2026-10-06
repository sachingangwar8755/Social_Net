# Social Network Friend Management System — Corrected

This corrected version uses **Flask + SQLite**. It does not require MySQL, MySQL Workbench, or a database password.

## Why this version fixes the registration problem

The old project mixed a MySQL backend with a registration form that did not send `username`. The old `database.py` expected MySQL and a `users` schema containing `password`, while the Flask code expected fields such as `is_admin`, `is_blocked`, and `profile_image`. That mismatch caused registration/database failures.

This version uses one consistent SQLite schema and one consistent Flask application.

## Features

- Registration with Full Name, Username, Email/Gmail, Password, Confirm Password
- Login using **Username + Password**
- 10 demo users automatically created
- Friend search
- Send, accept, reject and cancel requests
- Friend removal
- Favourites
- User profile and profile picture upload
- Private database-backed chat
- Admin login/dashboard
- Admin can search, block/unblock and delete users
- Password hashing
- Parameterized SQLite queries
- 2 MB profile image limit
- Responsive modern UI

## Install

Open this folder in VS Code Terminal:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open:

http://127.0.0.1:5000

## Demo accounts

Admin:
- username: `admin`
- password: `admin123`

Users:
- `user01` through `user10`
- password: `user123`

Every demo user is a separate account.

## Important

The SQLite file `database.db` is created automatically by `app.py`.

If you have an old `database.db` from a previous version and it gives schema errors, stop Flask and delete that old `database.db`. Then run:

```bash
python app.py
```

A fresh database will be created.

Do not put a real `.env` file or real passwords into GitHub.

## Test

1. Login as `user01`.
2. Search `user02`.
3. Send Invite.
4. Logout.
5. Login as `user02`.
6. Open Invitations and Accept.
7. Login as `user01` again and open Friends.
8. Add `user02` to Favourites.
9. Open Chat and send a message.
10. Open Profile and upload a picture.
11. Open Admin Login and check the users.
12. Admin can block/unblock or delete a user.

## Run

```bash
python app.py
```
