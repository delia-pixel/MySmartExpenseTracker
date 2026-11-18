
from flask import Flask, render_template, request, redirect, url_for
from database import get_db_connection
from datetime import date
from decimal import Decimal, InvalidOperation

app= Flask(__name__)

@app.route('/')
def home():
    income=5000
    expenses=3200
    balance=income-expenses
    transaction_count=12
    return render_template('index.html', income=income, expenses=expenses,balance=balance, transaction_count=transaction_count)


@app.route("/transactions")
def transactions():
    conn = get_db_connection()

    categories = conn.execute(
        "SELECT * FROM categories ORDER BY category_name"
    ).fetchall()

    transactions_list = conn.execute("""
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
        ORDER BY t.transaction_date DESC
    """).fetchall()

    conn.close()

    filters = {
        "transaction_type": request.args.get("transaction_type", ""),
        "category_id": request.args.get("category_id", ""),
        "start_date": request.args.get("start_date", ""),
        "end_date": request.args.get("end_date", "")
    }

    return render_template(
        "transactions.html",
        transactions=transactions_list,
        categories=categories,
        filters=filters
    )

@app.route("/add-transaction", methods=["GET", "POST"])
def add_transaction():
    conn = get_db_connection()

    categories = conn.execute(
        "SELECT * FROM categories ORDER BY category_name"
    ).fetchall()

    accounts = conn.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()

    if request.method == "POST":
        transaction_date = request.form.get("transaction_date", "")
        description = request.form.get("description", "").strip()
        amount_text = request.form.get("amount", "")
        transaction_type = request.form.get("transaction_type", "")
        category_id = request.form.get("category_id", "")
        account_id = request.form.get("account_id", "")
        custom_category = request.form.get("custom_category", "").strip()

        # Input validation
        # Variable to store errors
        error = None

        # Validate date 
        try:
            date.fromisoformat(transaction_date)
        except ValueError:
            error = "Please enter a valid date."

        try:
            amount = Decimal(amount_text)
            # Handle zero, negative and infinite amount
            if not amount.is_finite() or amount <= 0:
                error = "Amount must be greater than zero."
            # Ensures we have 2 decimal point number for amount    
            elif amount.as_tuple().exponent < -2:
                error = "Amount can have at most two decimal places."
        except InvalidOperation:
            amount = None
            error = "Please enter a valid amount."

        if not description:
            error = "Description is required."

        if len(description) > 200:
            error = "Description must be 200 characters or fewer."

        if transaction_type not in ("income", "expense"):
            error = "Invalid transaction type."

        # Select Categories for the 
        category = conn.execute(
            "SELECT * FROM categories WHERE category_id = ?",
            (category_id,)
        ).fetchone() if category_id.isdigit() else None

        account = conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?",
            (account_id,)
        ).fetchone() if account_id.isdigit() else None

        if category is None or category["category_type"] != transaction_type:
            error = "Please select a valid category for this type."

        if account is None:
            error = "Please select a valid account."

        if category is not None:
            if category["category_name"] == "Other":
                if not custom_category:
                    error = "Please specify the other category."
                elif len(custom_category) > 100:
                    error = "Other category must be 100 characters or fewer."
            else:
                custom_category = None

        if error:
            conn.close()
            return error, 400

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
            transaction_date,
            description,
            float(amount),
            transaction_type,
            int(category_id),
            int(account_id),
            custom_category
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("transactions"))

    conn.close()

    return render_template(
        "transaction_form.html",
        transaction=None,
        today=date.today().isoformat(),
        categories=categories,
        accounts=accounts
    )


if __name__=="__main__":
    app.run(debug=True)
