from datetime import date
from decimal import Decimal, InvalidOperation


def validate_transaction(conn, form):

    # Extract form inputs
    transaction_date = form.get("transaction_date", "")
    description = form.get("description", "").strip()
    amount_text = form.get("amount", "")
    transaction_type = form.get("transaction_type", "")
    category_id = form.get("category_id", "")
    account_id = form.get("account_id", "")
    custom_category = form.get("custom_category", "").strip()

    error = None

    # Validate date
    try:
        date.fromisoformat(transaction_date)
    except ValueError:
        error = "Please enter a valid date."

    # Validate amount
    try:
        amount = Decimal(amount_text)

        # Handle zero, negative and infinite amounts
        if not amount.is_finite() or amount <= 0:
            error = "Amount must be greater than zero."

        # Allow a maximum of two decimal places
        elif amount.as_tuple().exponent < -2:
            error = "Amount can have at most two decimal places."

    except InvalidOperation:
        amount = None
        error = "Please enter a valid amount."

    # Validate description
    if not description:
        error = "Description is required."

    if len(description) > 200:
        error = "Description must be 200 characters or fewer."

    # Validate transaction type
    if transaction_type not in ("income", "expense"):
        error = "Invalid transaction type."

    # Retrieve selected category
    category = conn.execute(
        "SELECT * FROM categories WHERE category_id = ?",
        (category_id,)
    ).fetchone() if category_id.isdigit() else None

    # Retrieve selected account
    account = conn.execute(
        "SELECT * FROM accounts WHERE account_id = ?",
        (account_id,)
    ).fetchone() if account_id.isdigit() else None

    # Validate category
    if category is None or category["category_type"] != transaction_type:
        error = "Please select a valid category for this type."

    # Validate account
    if account is None:
        error = "Please select a valid account."

    # Validate custom category when "Other" is selected
    if category is not None:
        if category["category_name"] == "Other":
            if not custom_category:
                error = "Please specify the other category."
            elif len(custom_category) > 100:
                error = "Other category must be 100 characters or fewer."
        else:
            custom_category = None

    # Return validation error
    if error:
        return None, error

    # Prepare validated transaction data
    transaction_data = {
        "transaction_date": transaction_date,
        "description": description,
        "amount": float(amount),
        "transaction_type": transaction_type,
        "category_id": int(category_id),
        "account_id": int(account_id),
        "custom_category": custom_category
    }

    return transaction_data, None