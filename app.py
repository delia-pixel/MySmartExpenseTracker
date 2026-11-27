
from flask import Flask, render_template, request, redirect, url_for
from database import get_db_connection
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from validators import validate_transaction
from PIL import Image, UnidentifiedImageError, ImageOps
import base64
from io import BytesIO
from receipt_ocr import process_receipt

app= Flask(__name__)

# Receipt upload configuration
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}
MAX_IMAGE_PIXELS = 12_000_000


@app.route("/")
def home():
    conn = get_db_connection()

    # Calculate total amount for each transaction type
    totals = conn.execute("""
        SELECT
            transaction_type,
            SUM(amount) AS total
        FROM transactions
        GROUP BY transaction_type
    """).fetchall()

    # Initialize totals
    total_income = 0
    total_expenses = 0

    # Separate income and expense totals
    for t in totals:
        if t["transaction_type"] == "income":
            total_income = t["total"]
        elif t["transaction_type"] == "expense":
            total_expenses = t["total"]

    # Calculate net balance
    net_balance = total_income - total_expenses

    # Count all transactions
    result = conn.execute("""
        SELECT COUNT(*) AS transaction_count
        FROM transactions
    """).fetchone()

    transaction_count = result["transaction_count"]

    # Close database connection
    conn.close()

    # Pass calculated values to the dashboard template
    return render_template(
        "index.html",
        total_income=total_income,
        total_expenses=total_expenses,
        net_balance=net_balance,
        transaction_count=transaction_count
    )


@app.route("/transactions")
def transactions():

    filters = {
        "transaction_type": request.args.get("transaction_type", ""),
        "category_id": request.args.get("category_id", ""),
        "account_id": request.args.get("account_id", ""),
        "start_date": request.args.get("start_date", ""),
        "end_date": request.args.get("end_date", "")
    }

    conn = get_db_connection()

    categories = conn.execute(
        "SELECT * FROM categories ORDER BY category_name"
    ).fetchall()

    accounts= conn.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()


    

    query = """
        SELECT
            t.transaction_id,
            t.transaction_date,
            t.description,
            t.amount,
            t.transaction_type,
            t.custom_category,
            c.category_name,
            c.category_type,
            a.account_name
        FROM transactions t
        JOIN categories c
            ON t.category_id = c.category_id
        JOIN accounts a
            ON t.account_id = a.account_id
            WHERE 1=1
    """

    params=[]

    # Filter by transaction type
    if filters["transaction_type"]:
        query += " AND t.transaction_type = ?"
        params.append(filters["transaction_type"])

    # Filter by account
    if filters["account_id"]:
        query += " AND t.account_id = ?"
        params.append(filters["account_id"])

    # Filter by category
    if filters["category_id"]:
        query += " AND c.category_id = ?"
        params.append(filters["category_id"])

    # Filter by start date
    if filters["start_date"]:
        query += " AND t.transaction_date >= ?"
        params.append(filters["start_date"])

    # Filter by end date
    if filters["end_date"]:
        query += " AND t.transaction_date <= ?"
        params.append(filters["end_date"])

    # print(query)
    # print(params)   

    query += " ORDER BY t.transaction_date DESC, t.transaction_id DESC"

    transactions_list=conn.execute(query, params).fetchall()

    conn.close()

   

    return render_template(
        "transactions.html",
        accounts=accounts,
        transactions=transactions_list,
        categories=categories,
        filters=filters
    )

def render_add_transaction_form(
    prefill=None,
    ocr_warnings=None,
    upload_error=None,
    receipt_preview=None
):

    conn = get_db_connection()

    try:

        categories = conn.execute(
            "SELECT * FROM categories"
        ).fetchall()

        accounts = conn.execute(
            "SELECT * FROM accounts"
        ).fetchall()

    finally:

        conn.close()

    return render_template(
        "transaction_form.html",
        transaction=None,
        today=datetime.now().strftime("%Y-%m-%d"),
        categories=categories,
        accounts=accounts,
        prefill=prefill,
        ocr_warnings=ocr_warnings or [],
        upload_error=upload_error,
        receipt_preview=receipt_preview
    )


@app.route("/add-transaction", methods=["GET", "POST"])
def add_transaction():
    conn = get_db_connection()

    

    if request.method == "POST":

        # Extract and validate the inputs
        transaction_data, error = validate_transaction(
            conn, request.form
        )

        # Handle validation errors
        if error:
            conn.close()
            return error, 400

        # Insert the validated transaction
        conn.execute("""
            INSERT INTO transactions (
                transaction_date,
                description,
                amount,
                transaction_type,
                category_id,
                account_id,
                custom_category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction_data["transaction_date"],
            transaction_data["description"],
            transaction_data["amount"],
            transaction_data["transaction_type"],
            transaction_data["category_id"],
            transaction_data["account_id"],
            transaction_data["custom_category"]
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("transactions"))

    # Handle GET request
    conn.close()

    return render_add_transaction_form()



def generate_receipt_preview(image):
    preview = ImageOps.exif_transpose(image).convert("RGB")
    preview.thumbnail((2000, 3000))
    with BytesIO() as buffer:
        preview.save(buffer, format="JPEG", quality=90)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


@app.route("/scan-receipt", methods=["POST"])
def scan_receipt():

    receipt = request.files.get("receipt")

    # Validate that a file was uploaded
    if not receipt or not receipt.filename:

        return render_add_transaction_form(
            upload_error="Please select a receipt image."
        ), 400

    try:

        # Open the uploaded image
        with Image.open(receipt.stream) as image:

            # Validate the actual image format
            if image.format not in ALLOWED_IMAGE_FORMATS:

                return render_add_transaction_form(
                    upload_error="Only JPEG and PNG images are supported."
                ), 400

            # Validate image dimensions
            width, height = image.size

            if width * height > MAX_IMAGE_PIXELS:

                return render_add_transaction_form(
                    upload_error="The image dimensions are too large."
                ), 400

            # Run our OCR pipeline
            receipt_preview = generate_receipt_preview(image)
            result = process_receipt(image)

    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError
    ):

        return render_add_transaction_form(
            upload_error="The uploaded file could not be processed."
        ), 400

    except Exception:

        app.logger.exception("Receipt OCR processing failed")

        return render_add_transaction_form(
            upload_error=(
                "Receipt recognition failed. "
                "Please try another image or enter the transaction manually."
            )
        ), 500

    # Prepare extracted information
    prefill = {
        "description": result["description"],
        "amount": result["amount"],
        "transaction_date": result["transaction_date"],
        "transaction_type": result["transaction_type"]
    }

    # Display the transaction form
    return render_add_transaction_form(
        prefill=prefill,
        receipt_preview=receipt_preview,
        ocr_warnings=result["warnings"]
    )

@app.route("/edit/<int:transaction_id>", methods=["GET","POST"])
def edit_transaction(transaction_id):
    conn=get_db_connection()

    transaction=conn.execute("""
        SELECT * 
        FROM transactions 
        WHERE transaction_id=?
   
    """, (transaction_id,)
    ).fetchone()

    # Check if the transaction exists
    if transaction is None:
        conn.close()
        return "Transaction not found.", 404
    
    # Retrieve all categories
    categories = conn.execute(
        "SELECT * FROM categories ORDER BY category_name"
    ).fetchall()

    # Retrieve all accounts
    accounts = conn.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()

    if request.method == "POST":

        # Validate the updated transaction
        transaction_data, error = validate_transaction(
            conn, request.form
        )

        if error:
            conn.close()
            return error, 400

        # Update the transaction
        conn.execute("""
            UPDATE transactions
            SET
                transaction_date = ?,
                description = ?,
                amount = ?,
                transaction_type = ?,
                category_id = ?,
                account_id = ?,
                custom_category = ?
            WHERE transaction_id = ?
        """, (
            transaction_data["transaction_date"],
            transaction_data["description"],
            transaction_data["amount"],
            transaction_data["transaction_type"],
            transaction_data["category_id"],
            transaction_data["account_id"],
            transaction_data["custom_category"],
            transaction_id
        ))

        conn.commit()
        conn.close()
        return redirect(url_for("transactions"))

    conn.close()
    return render_template(
        "transaction_form.html",
        transaction=transaction,
        today=date.today().isoformat(),
        categories=categories,
        accounts=accounts
    )

@app.route("/delete/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    conn = get_db_connection()

    # Check whether the transaction exists
    transaction = conn.execute("""
        SELECT transaction_id
        FROM transactions
        WHERE transaction_id = ?
    """, (transaction_id,)).fetchone()

    if transaction is None:
        conn.close()
        return "Transaction not found.", 404

    # Delete the selected transaction
    conn.execute("""
        DELETE FROM transactions
        WHERE transaction_id = ?
    """, (transaction_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("transactions"))



@app.errorhandler(413)
def file_too_large(error):

    return render_add_transaction_form(
        upload_error="The upload exceeds the 10 MB request limit."
    ), 413

if __name__ == "__main__":
    app.run(debug=True)
