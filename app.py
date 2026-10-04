from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
import os
import uuid
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = "digital-lost-found-secret-key"

DATABASE = "database.db"

UPLOAD_FOLDER = os.path.join(
    "static",
    "uploads"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    connection = sqlite3.connect(DATABASE)

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# DATABASE CREATION
# ============================================================

def create_database():

    connection = get_db_connection()

    cursor = connection.cursor()


    # USERS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)


    # LOST ITEMS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lost_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            item_date TEXT NOT NULL,
            photo TEXT,
            status TEXT DEFAULT 'Lost',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)


    # FOUND ITEMS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS found_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            item_date TEXT NOT NULL,
            photo TEXT,
            status TEXT DEFAULT 'Found',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)


    # CLAIMS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            found_item_id INTEGER NOT NULL,
            claim_reason TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            claim_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (found_item_id) REFERENCES found_items(id)
        )
    """)


    # Add claim_date to old databases
    columns = cursor.execute(
        "PRAGMA table_info(claims)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    if "claim_date" not in column_names:

        cursor.execute("""
            ALTER TABLE claims
            ADD COLUMN claim_date TEXT
        """)


    cursor.execute("""
        UPDATE claims
        SET claim_date = ?
        WHERE claim_date IS NULL
    """, (
        datetime.now().strftime("%b %d, %Y"),
    ))


    # ADMIN ACCOUNT
    admin_email = "admin@app.com"
    admin_password = "Admin@123"
    admin_name = "Administrator"


    admin = cursor.execute("""
        SELECT *
        FROM users
        WHERE email = ?
    """, (
        admin_email,
    )).fetchone()


    hashed_admin_password = generate_password_hash(
        admin_password
    )


    if admin is None:

        cursor.execute("""
            INSERT INTO users
            (
                name,
                email,
                password,
                role
            )
            VALUES (?, ?, ?, 'admin')
        """, (
            admin_name,
            admin_email,
            hashed_admin_password
        ))

    else:

        cursor.execute("""
            UPDATE users
            SET
                name = ?,
                password = ?,
                role = 'admin'
            WHERE email = ?
        """, (
            admin_name,
            hashed_admin_password,
            admin_email
        ))


    connection.commit()

    connection.close()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    if "user_id" in session:

        if session.get("role") == "admin":
            return redirect("/admin-dashboard")

        return redirect("/dashboard")

    return redirect("/login")


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()

        email = request.form["email"].strip().lower()

        password = request.form["password"]


        if not name or not email or not password:

            return render_template(
                "register.html",
                error="All fields are required."
            )


        connection = get_db_connection()


        existing_user = connection.execute("""
            SELECT id
            FROM users
            WHERE email = ?
        """, (
            email,
        )).fetchone()


        if existing_user:

            connection.close()

            return render_template(
                "register.html",
                error="Email already registered."
            )


        hashed_password = generate_password_hash(
            password
        )


        connection.execute("""
            INSERT INTO users
            (
                name,
                email,
                password,
                role
            )
            VALUES (?, ?, ?, 'user')
        """, (
            name,
            email,
            hashed_password
        ))


        connection.commit()

        connection.close()


        return redirect("/login")


    return render_template("register.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()

        password = request.form["password"]


        connection = get_db_connection()


        user = connection.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (
            email,
        )).fetchone()


        connection.close()


        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            session["role"] = user["role"]


            if user["role"] == "admin":

                session["admin_id"] = user["id"]
                session["admin_name"] = user["name"]

                return redirect(
                    "/admin-dashboard"
                )


            return redirect("/dashboard")


        return render_template(
            "login.html",
            error="Invalid email or password."
        )


    return render_template("login.html")


# ============================================================
# USER DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    if (
        "user_id" not in session
        or session.get("role") != "user"
    ):

        return redirect("/login")


    connection = get_db_connection()


    total_lost = connection.execute("""
        SELECT COUNT(*) AS count
        FROM lost_items
    """).fetchone()["count"]


    total_found = connection.execute("""
        SELECT COUNT(*) AS count
        FROM found_items
    """).fetchone()["count"]


    my_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE user_id = ?
    """, (
        session["user_id"],
    )).fetchone()["count"]


    pending_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE user_id = ?
        AND status = 'Pending'
    """, (
        session["user_id"],
    )).fetchone()["count"]


    connection.close()


    return render_template(
        "dashboard.html",
        name=session["user_name"],
        total_lost=total_lost,
        total_found=total_found,
        my_claims=my_claims,
        pending_claims=pending_claims
    )


# ============================================================
# REPORT LOST
# ============================================================

@app.route("/report-lost", methods=["GET", "POST"])
def report_lost():

    if (
        "user_id" not in session
        or session.get("role") != "user"
    ):

        return redirect("/login")


    if request.method == "POST":

        item_name = request.form["item_name"].strip()

        description = request.form["description"].strip()

        location = request.form["location"].strip()

        item_date = request.form["item_date"]

        photo = request.files.get("photo")


        if not item_name or not description or not location or not item_date:

            return render_template(
                "report_lost.html",
                error="Please fill all required fields."
            )


        photo_filename = None


        if photo and photo.filename:

            extension = photo.filename.rsplit(
                ".",
                1
            )[1].lower()

            filename = (
                str(uuid.uuid4())
                + "."
                + extension
            )

            photo_filename = filename

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )


        connection = get_db_connection()


        connection.execute("""
            INSERT INTO lost_items
            (
                user_id,
                item_name,
                description,
                location,
                item_date,
                photo,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Lost')
        """, (
            session["user_id"],
            item_name,
            description,
            location,
            item_date,
            photo_filename
        ))


        connection.commit()

        connection.close()


        return redirect("/items")


    return render_template("report_lost.html")


# ============================================================
# REPORT FOUND
# ============================================================

@app.route("/report-found", methods=["GET", "POST"])
def report_found():

    if (
        "user_id" not in session
        or session.get("role") != "user"
    ):

        return redirect("/login")


    if request.method == "POST":

        item_name = request.form["item_name"].strip()

        description = request.form["description"].strip()

        location = request.form["location"].strip()

        item_date = request.form["item_date"]

        photo = request.files.get("photo")


        if not item_name or not description or not location or not item_date:

            return render_template(
                "report_found.html",
                error="Please fill all required fields."
            )


        photo_filename = None


        if photo and photo.filename:

            extension = photo.filename.rsplit(
                ".",
                1
            )[1].lower()

            filename = (
                str(uuid.uuid4())
                + "."
                + extension
            )

            photo_filename = filename

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )


        connection = get_db_connection()


        connection.execute("""
            INSERT INTO found_items
            (
                user_id,
                item_name,
                description,
                location,
                item_date,
                photo,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Found')
        """, (
            session["user_id"],
            item_name,
            description,
            location,
            item_date,
            photo_filename
        ))


        connection.commit()

        connection.close()


        return redirect("/items")


    return render_template("report_found.html")


# ============================================================
# ITEMS
# ============================================================

@app.route("/items")
def items():

    if "user_id" not in session:

        return redirect("/login")


    search = request.args.get(
        "search",
        ""
    ).strip()


    item_type = request.args.get(
        "type",
        ""
    ).strip()


    connection = get_db_connection()

    items_list = []


    if not item_type or item_type.lower() == "lost":

        query = """
            SELECT
                id,
                item_name,
                description,
                location,
                item_date,
                photo,
                status,
                'Lost' AS item_type
            FROM lost_items
            WHERE 1 = 1
        """

        parameters = []


        if search:

            query += """
                AND (
                    item_name LIKE ?
                    OR description LIKE ?
                    OR location LIKE ?
                )
            """

            value = f"%{search}%"

            parameters = [
                value,
                value,
                value
            ]


        rows = connection.execute(
            query,
            parameters
        ).fetchall()

        items_list.extend(rows)


    if not item_type or item_type.lower() == "found":

        query = """
            SELECT
                id,
                item_name,
                description,
                location,
                item_date,
                photo,
                status,
                'Found' AS item_type
            FROM found_items
            WHERE 1 = 1
        """

        parameters = []


        if search:

            query += """
                AND (
                    item_name LIKE ?
                    OR description LIKE ?
                    OR location LIKE ?
                )
            """

            value = f"%{search}%"

            parameters = [
                value,
                value,
                value
            ]


        rows = connection.execute(
            query,
            parameters
        ).fetchall()

        items_list.extend(rows)


    connection.close()


    return render_template(
        "items.html",
        items=items_list,
        search=search,
        item_type=item_type
    )


# ============================================================
# CLAIM ITEM
# ============================================================

@app.route(
    "/claim/<int:item_id>",
    methods=["GET", "POST"]
)
def claim(item_id):

    if (
        "user_id" not in session
        or session.get("role") != "user"
    ):

        return redirect("/login")


    connection = get_db_connection()


    found_item = connection.execute("""
        SELECT *
        FROM found_items
        WHERE id = ?
    """, (
        item_id,
    )).fetchone()


    if found_item is None:

        connection.close()

        return redirect("/items")


    if request.method == "POST":

        claim_reason = request.form[
            "claim_reason"
        ].strip()


        if not claim_reason:

            connection.close()

            return render_template(
                "claim.html",
                item=found_item,
                error="Claim reason is required."
            )


        existing_claim = connection.execute("""
            SELECT id
            FROM claims
            WHERE user_id = ?
            AND found_item_id = ?
        """, (
            session["user_id"],
            item_id
        )).fetchone()


        if existing_claim:

            connection.close()

            return redirect("/my-claims")


        claim_date = datetime.now().strftime(
            "%b %d, %Y"
        )


        connection.execute("""
            INSERT INTO claims
            (
                user_id,
                found_item_id,
                claim_reason,
                status,
                claim_date
            )
            VALUES (?, ?, ?, 'Pending', ?)
        """, (
            session["user_id"],
            item_id,
            claim_reason,
            claim_date
        ))


        connection.commit()

        connection.close()


        return redirect("/my-claims")


    connection.close()


    return render_template(
        "claim.html",
        item=found_item
    )


# ============================================================
# MY CLAIMS
# ============================================================

@app.route("/my-claims")
def my_claims():

    if (
        "user_id" not in session
        or session.get("role") != "user"
    ):

        return redirect("/login")


    connection = get_db_connection()


    claims = connection.execute("""
        SELECT

            claims.id,
            claims.claim_reason,
            claims.status,
            claims.claim_date,

            found_items.item_name,
            found_items.description,
            found_items.location,
            found_items.item_date,
            found_items.photo

        FROM claims

        JOIN found_items
            ON claims.found_item_id = found_items.id

        WHERE claims.user_id = ?

        ORDER BY claims.id DESC

    """, (
        session["user_id"],
    )).fetchall()


    connection.close()


    return render_template(
        "my_claims.html",
        claims=claims
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin-login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        email = request.form[
            "email"
        ].strip().lower()


        password = request.form[
            "password"
        ]


        connection = get_db_connection()


        admin = connection.execute("""
            SELECT *
            FROM users
            WHERE email = ?
            AND role = 'admin'
        """, (
            email,
        )).fetchone()


        connection.close()


        if admin and check_password_hash(
            admin["password"],
            password
        ):

            session.clear()

            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["name"]
            session["role"] = "admin"

            return redirect(
                "/admin-dashboard"
            )


        return render_template(
            "admin_login.html",
            error="Invalid admin email or password."
        )


    return render_template(
        "admin_login.html"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin-dashboard")
def admin_dashboard():

    if (
        "admin_id" not in session
        or session.get("role") != "admin"
    ):

        return redirect("/admin-login")


    connection = get_db_connection()


    total_users = connection.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE role = 'user'
    """).fetchone()["count"]


    total_lost = connection.execute("""
        SELECT COUNT(*) AS count
        FROM lost_items
    """).fetchone()["count"]


    total_found = connection.execute("""
        SELECT COUNT(*) AS count
        FROM found_items
    """).fetchone()["count"]


    pending_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE status = 'Pending'
    """).fetchone()["count"]


    claims = connection.execute("""
        SELECT

            claims.id,
            claims.claim_reason,
            claims.status,
            claims.claim_date,

            users.name AS user_name,
            users.email AS user_email,

            found_items.item_name,
            found_items.description,
            found_items.location,
            found_items.photo

        FROM claims

        JOIN users
            ON claims.user_id = users.id

        JOIN found_items
            ON claims.found_item_id = found_items.id

        ORDER BY claims.id DESC

    """).fetchall()


    connection.close()


    return render_template(
        "admin_dashboard.html",

        claims=claims,

        name=session["admin_name"],

        total_users=total_users,

        total_lost=total_lost,

        total_found=total_found,

        pending_claims=pending_claims
    )


# ============================================================
# ADMIN REPORTS
# ============================================================

@app.route("/admin-reports")
def admin_reports():

    if (
        "admin_id" not in session
        or session.get("role") != "admin"
    ):

        return redirect("/admin-login")


    connection = get_db_connection()


    total_lost = connection.execute("""
        SELECT COUNT(*) AS count
        FROM lost_items
    """).fetchone()["count"]


    total_found = connection.execute("""
        SELECT COUNT(*) AS count
        FROM found_items
    """).fetchone()["count"]


    total_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
    """).fetchone()["count"]


    pending_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE status = 'Pending'
    """).fetchone()["count"]


    approved_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE status = 'Approved'
    """).fetchone()["count"]


    rejected_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE status = 'Rejected'
    """).fetchone()["count"]


    total_users = connection.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE role = 'user'
    """).fetchone()["count"]


    connection.close()


    return render_template(
        "admin_reports.html",

        total_lost=total_lost,

        total_found=total_found,

        total_claims=total_claims,

        pending_claims=pending_claims,

        approved_claims=approved_claims,

        rejected_claims=rejected_claims,

        total_users=total_users
    )


# ============================================================
# DOWNLOAD PDF REPORT
# ============================================================

@app.route("/admin-reports/download")
def download_report():

    if (
        "admin_id" not in session
        or session.get("role") != "admin"
    ):

        return redirect("/admin-login")


    connection = get_db_connection()


    total_lost = connection.execute("""
        SELECT COUNT(*) AS count
        FROM lost_items
    """).fetchone()["count"]


    total_found = connection.execute("""
        SELECT COUNT(*) AS count
        FROM found_items
    """).fetchone()["count"]


    total_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
    """).fetchone()["count"]


    pending_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE status = 'Pending'
    """).fetchone()["count"]


    approved_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE status = 'Approved'
    """).fetchone()["count"]


    rejected_claims = connection.execute("""
        SELECT COUNT(*) AS count
        FROM claims
        WHERE status = 'Rejected'
    """).fetchone()["count"]


    total_users = connection.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE role = 'user'
    """).fetchone()["count"]


    claims = connection.execute("""
        SELECT

            claims.id,
            claims.claim_reason,
            claims.status,
            claims.claim_date,

            users.name AS user_name,
            users.email AS user_email,

            found_items.item_name,
            found_items.location

        FROM claims

        JOIN users
            ON claims.user_id = users.id

        JOIN found_items
            ON claims.found_item_id = found_items.id

        ORDER BY claims.id DESC

    """).fetchall()


    connection.close()


    # --------------------------------------------------------
    # CREATE PDF
    # --------------------------------------------------------

    buffer = BytesIO()


    pdf = canvas.Canvas(
        buffer,
        pagesize=A4
    )


    width, height = A4


    # TITLE

    pdf.setFont(
        "Helvetica-Bold",
        20
    )

    pdf.drawString(
        50,
        height - 55,
        "Digital Lost & Found System"
    )


    pdf.setFont(
        "Helvetica-Bold",
        16
    )

    pdf.drawString(
        50,
        height - 82,
        "System Report"
    )


    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        50,
        height - 105,
        "Generated on: "
        + datetime.now().strftime(
            "%d %B %Y, %I:%M %p"
        )
    )


    # STATISTICS

    y = height - 145


    pdf.setFont(
        "Helvetica-Bold",
        13
    )

    pdf.drawString(
        50,
        y,
        "System Statistics"
    )


    y -= 25


    pdf.setFont(
        "Helvetica",
        11
    )


    statistics = [

        ("Registered Users", total_users),

        ("Lost Items", total_lost),

        ("Found Items", total_found),

        ("Total Claims", total_claims),

        ("Pending Claims", pending_claims),

        ("Approved Claims", approved_claims),

        ("Rejected Claims", rejected_claims)

    ]


    for label, value in statistics:

        pdf.drawString(
            70,
            y,
            f"{label}: {value}"
        )

        y -= 20


    # CLAIM DETAILS

    y -= 15


    pdf.setFont(
        "Helvetica-Bold",
        13
    )

    pdf.drawString(
        50,
        y,
        "Claim Details"
    )


    y -= 25


    if not claims:

        pdf.setFont(
            "Helvetica",
            10
        )

        pdf.drawString(
            70,
            y,
            "No claim requests found."
        )

    else:

        for claim in claims:

            if y < 100:

                pdf.showPage()

                y = height - 50


            pdf.setFont(
                "Helvetica-Bold",
                10
            )

            pdf.drawString(
                55,
                y,
                f"Claim #{claim['id']} - {claim['item_name']}"
            )

            y -= 16


            pdf.setFont(
                "Helvetica",
                9
            )


            details = [

                f"User: {claim['user_name']}",

                f"Email: {claim['user_email']}",

                f"Location: {claim['location']}",

                f"Claim Date: {claim['claim_date']}",

                f"Status: {claim['status']}",

                f"Reason: {claim['claim_reason']}"

            ]


            for detail in details:

                if len(detail) > 105:

                    detail = detail[:105] + "..."


                pdf.drawString(
                    70,
                    y,
                    detail
                )

                y -= 14


            y -= 12


    # FOOTER

    pdf.setFont(
        "Helvetica",
        8
    )

    pdf.drawString(
        50,
        30,
        "Digital Lost & Found System - Admin Report"
    )


    pdf.save()


    buffer.seek(0)


    return send_file(
        buffer,
        as_attachment=True,
        download_name="Digital_Lost_Found_Report.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# APPROVE CLAIM
# ============================================================

@app.route(
    "/admin/claim/<int:claim_id>/approve"
)
def approve_claim(claim_id):

    if (
        "admin_id" not in session
        or session.get("role") != "admin"
    ):

        return redirect("/admin-login")


    connection = get_db_connection()


    claim = connection.execute("""
        SELECT found_item_id
        FROM claims
        WHERE id = ?
    """, (
        claim_id,
    )).fetchone()


    if claim:

        connection.execute("""
            UPDATE claims
            SET status = 'Approved'
            WHERE id = ?
        """, (
            claim_id,
        ))


        connection.execute("""
            UPDATE found_items
            SET status = 'Claimed'
            WHERE id = ?
        """, (
            claim["found_item_id"],
        ))


        connection.commit()


    connection.close()


    return redirect(
        "/admin-dashboard"
    )


# ============================================================
# REJECT CLAIM
# ============================================================

@app.route(
    "/admin/claim/<int:claim_id>/reject"
)
def reject_claim(claim_id):

    if (
        "admin_id" not in session
        or session.get("role") != "admin"
    ):

        return redirect("/admin-login")


    connection = get_db_connection()


    connection.execute("""
        UPDATE claims
        SET status = 'Rejected'
        WHERE id = ?
    """, (
        claim_id,
    ))


    connection.commit()

    connection.close()


    return redirect(
        "/admin-dashboard"
    )


# ============================================================
# USER LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin-logout")
def admin_logout():

    session.clear()

    return redirect("/admin-login")


# ============================================================
# CREATE DATABASE
# ============================================================

create_database()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )