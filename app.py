from flask import Flask, render_template, request, redirect, url_for, session
import os, sqlite3, uuid
import qrcode
import win32print, win32api

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    template_folder=os.path.join(BASE_DIR, "templates")
)
app.secret_key = "secret123"
UPLOAD_FOLDER = "uploads"
QR_FOLDER = "static/qr_codes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

# ---------------- DATABASE ----------------

def get_db():
    return sqlite3.connect("database.db")

with get_db() as db:
    db.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT,
            customer TEXT,
            filename TEXT,
            copies INTEGER,
            duplex TEXT,
            color TEXT,
            notes TEXT
        )
    """)

# ---------------- ADMIN LOGIN ----------------

@app.route("/", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["password"] == "admin123":
            session["admin"] = True
            return redirect("/dashboard")
    return render_template("admin_login.html")


# ---------------- QR CODE ----------------

@app.route("/dashboard")
def dashboard():
    print("DASHBOARD ROUTE HIT")

    if not session.get("admin"):
        print("ADMIN NOT LOGGED IN")
        return redirect("/")

    import os, qrcode

    customer_url = request.host_url.rstrip("/") + "/upload"
    print("CUSTOMER URL:", customer_url)

    qr_dir = os.path.join(os.getcwd(), "static", "qr_codes")
    print("QR DIR:", qr_dir)

    os.makedirs(qr_dir, exist_ok=True)

    qr_path = os.path.join(qr_dir, "store_qr.png")
    print("QR FULL PATH:", qr_path)

    img = qrcode.make(customer_url)
    img.save(qr_path)

    print("QR SAVED:", os.path.exists(qr_path))

    db = get_db()
    jobs = db.execute("SELECT * FROM jobs").fetchall()

    printers = [
        p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
    ]

    return render_template(
        "admin_dashboard.html",
        qr="store_qr.png",
        jobs=jobs,
        printers=printers
    )


# ---------------- CUSTOMER UPLOAD ----------------

@app.route("/upload", methods=["GET", "POST"])
def customer_upload():
    customer_name = session.get("customer")
    if not customer_name:
        customer_name = f"Customer-{uuid.uuid4().hex[:4]}"
        session["customer"] = customer_name

    # keep list of uploaded files in session
    uploaded_files = session.get("uploaded_files", [])
    success = False

    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename:
            job_id = uuid.uuid4().hex
            filename = f"{job_id}_{file.filename}"
            file.save(os.path.join(UPLOAD_FOLDER, filename))

            db = get_db()
            db.execute("""
                INSERT INTO jobs VALUES (?,?,?,?,?,?,?)
            """, (
                job_id,
                customer_name,
                filename,
                request.form.get("copies", 1),
                request.form.get("duplex", "single"),
                request.form.get("color", "bw"),
                request.form.get("notes", "")
            ))
            db.commit()

            # store original filename for display
            uploaded_files.append(file.filename)
            session["uploaded_files"] = uploaded_files

            success = True

    return render_template(
        "customer_upload.html",
        customer=customer_name,
        success=success,
        uploaded_files=uploaded_files
    )

# ---------------- PRINT ----------------

@app.route("/print", methods=["POST"])
def print_job():
    if not session.get("admin"):
        return redirect("/")

    job_id = request.form["job_id"]
    printer = request.form["printer"]

    db = get_db()
    job = db.execute(
        "SELECT filename FROM jobs WHERE id=?",
        (job_id,)
    ).fetchone()

    if not job:
        return "Job not found", 404

    filepath = os.path.abspath(os.path.join(UPLOAD_FOLDER, job[0]))

    send_to_printer(filepath, printer)

    return redirect("/dashboard")


def send_to_printer(filepath, printer):
    # Set default printer (this is allowed)
    win32print.SetDefaultPrinter(printer)

    # Let Windows Explorer handle printing
    os.startfile(filepath, "print")



if __name__ == "__main__":
    app.run()
