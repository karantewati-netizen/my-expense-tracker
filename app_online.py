
import streamlit as st
import pandas as pd
from supabase import create_client

# --------------------------------
# PAGE CONFIGURATION
# --------------------------------

st.set_page_config(
    page_title="My Expense Tracker",
    page_icon="💰",
    layout="wide"
)

# --------------------------------
# SUPABASE CONNECTION
# --------------------------------

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error("Supabase connection details nahi mile. secrets.toml check karo.")
    st.stop()


# --------------------------------
# SESSION AND AUTHENTICATION
# --------------------------------

if "access_token" not in st.session_state:
    st.session_state.access_token = None

if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if "user_email" not in st.session_state:
    st.session_state.user_email = None


# Restore login session after Streamlit reruns
if st.session_state.access_token:
    try:
        auth_session = supabase.auth.set_session(
            st.session_state.access_token,
            st.session_state.refresh_token
        )

        if auth_session.session:
            st.session_state.access_token = auth_session.session.access_token
            st.session_state.refresh_token = auth_session.session.refresh_token

    except Exception:
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.user_id = None
        st.session_state.user_email = None


def save_login_session(response):
    """Save logged-in user's session."""
    if response.session and response.user:
        st.session_state.access_token = response.session.access_token
        st.session_state.refresh_token = response.session.refresh_token
        st.session_state.user_id = response.user.id
        st.session_state.user_email = response.user.email
        return True

    return False


# --------------------------------
# LOGIN AND SIGNUP PAGE
# --------------------------------

if not st.session_state.access_token:

    st.title("💰 My Expense Tracker")
    st.write("Manage your personal expenses securely.")

    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:

        st.subheader("Login to Your Account")

        with st.form("login_form"):

            email = st.text_input("Email Address")
            password = st.text_input("Password", type="password")

            login_button = st.form_submit_button(
                "Login",
                type="primary",
                width="stretch"
            )

        if login_button:

            if email.strip() and password:

                try:
                    response = supabase.auth.sign_in_with_password({
                        "email": email.strip(),
                        "password": password
                    })

                    if save_login_session(response):
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Login session nahi mili. Dobara try karo.")

                except Exception as e:
                    st.error(f"Login failed: {e}")

            else:
                st.warning("Email aur password dono enter karo.")

    with signup_tab:

        st.subheader("Create New Account")

        with st.form("signup_form"):

            signup_email = st.text_input("Email Address")
            signup_password = st.text_input(
                "Create Password",
                type="password"
            )
            confirm_password = st.text_input(
                "Confirm Password",
                type="password"
            )

            signup_button = st.form_submit_button(
                "Create Account",
                type="primary",
                width="stretch"
            )

        if signup_button:

            if not signup_email.strip():
                st.warning("Email enter karo.")

            elif len(signup_password) < 6:
                st.warning("Password kam se kam 6 characters ka hona chahiye.")

            elif signup_password != confirm_password:
                st.error("Dono passwords match nahi karte.")

            else:

                try:
                    response = supabase.auth.sign_up({
                        "email": signup_email.strip(),
                        "password": signup_password
                    })

                    if save_login_session(response):
                        st.success("Account created successfully!")
                        st.rerun()
                    else:
                        st.success(
                            "Account created! Apna email check karo "
                            "aur confirmation link par click karo. "
                            "Uske baad login karo."
                        )

                except Exception as e:
                    st.error(f"Signup failed: {e}")

    st.stop()


# --------------------------------
# LOGGED-IN USER
# --------------------------------

user_id = st.session_state.user_id

if not user_id:
    st.error("User session nahi mili. Dobara login karo.")
    st.stop()


# --------------------------------
# DATABASE FUNCTIONS
# --------------------------------

def load_expenses():

    response = (
        supabase.table("expenses")
        .select("*")
        .eq("user_id", user_id)
        .order("expense_date", desc=True)
        .execute()
    )

    data = response.data or []

    columns = [
        "id",
        "user_id",
        "name",
        "amount",
        "category",
        "expense_date"
    ]

    df = pd.DataFrame(data)

    if df.empty:
        return pd.DataFrame(columns=columns)

    df["amount"] = pd.to_numeric(
        df["amount"], errors="coerce"
    ).fillna(0)

    df["expense_date"] = pd.to_datetime(
        df["expense_date"], errors="coerce"
    )

    return df


def load_budget():

    response = (
        supabase.table("budgets")
        .select("monthly_budget")
        .eq("user_id", user_id)
        .execute()
    )

    if response.data:
        return float(response.data[0]["monthly_budget"])

    return 5000.0


def save_budget(amount):

    response = (
        supabase.table("budgets")
        .select("user_id")
        .eq("user_id", user_id)
        .execute()
    )

    if response.data:

        supabase.table("budgets").update({
            "monthly_budget": amount
        }).eq("user_id", user_id).execute()

    else:

        supabase.table("budgets").insert({
            "user_id": user_id,
            "monthly_budget": amount
        }).execute()


# --------------------------------
# LOAD USER DATA
# --------------------------------

try:
    df = load_expenses()
    saved_budget = load_budget()

except Exception as e:
    st.error(f"Database se data load nahi hua: {e}")
    st.stop()


# --------------------------------
# SIDEBAR AND NAVIGATION
# --------------------------------

st.sidebar.title("💰 My Expense Tracker")

st.sidebar.write("Welcome!")
st.sidebar.caption(st.session_state.user_email)

st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Add Expense",
        "View Expenses",
        "Reports"
    ]
)

st.sidebar.divider()

if st.sidebar.button("Logout", width="stretch"):

    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.user_id = None
    st.session_state.user_email = None

    st.rerun()


# --------------------------------
# DASHBOARD
# --------------------------------

if page == "Dashboard":

    st.title("📊 Dashboard")

    total_expenses = len(df)
    total_spending = df["amount"].sum()

    if not df.empty:
        highest_expense = df["amount"].max()
        average_expense = df["amount"].mean()
    else:
        highest_expense = 0
        average_expense = 0

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Expenses", total_expenses)
    col2.metric("Total Spending", f"₹{total_spending:.2f}")
    col3.metric("Highest Expense", f"₹{highest_expense:.2f}")
    col4.metric("Average Expense", f"₹{average_expense:.2f}")

    st.divider()

    st.subheader("Recent Expenses")

    if not df.empty:

        recent = df.head(5).copy()

        recent["expense_date"] = (
            recent["expense_date"].dt.strftime("%d-%m-%Y")
        )

        st.dataframe(
            recent[["name", "amount", "category", "expense_date"]],
            width="stretch",
            hide_index=True
        )

    else:
        st.info("Abhi koi expense add nahi hua hai.")


# --------------------------------
# ADD EXPENSE
# --------------------------------

elif page == "Add Expense":

    st.title("➕ Add New Expense")

    with st.form("add_expense_form"):

        name = st.text_input("Expense Name")

        amount = st.number_input(
            "Amount (₹)",
            min_value=0.0,
            step=1.0
        )

        category = st.selectbox(
            "Category",
            ["Food", "Travel", "Shopping", "Education", "Other"]
        )

        expense_date = st.date_input("Expense Date")

        submit = st.form_submit_button(
            "Add Expense",
            type="primary",
            width="stretch"
        )

    if submit:

        if name.strip() and amount > 0:

            try:

                supabase.table("expenses").insert({
                    "user_id": user_id,
                    "name": name.strip(),
                    "amount": amount,
                    "category": category,
                    "expense_date": expense_date.isoformat()
                }).execute()

                st.success("Expense added successfully!")
                st.rerun()

            except Exception as e:
                st.error(f"Expense add nahi hua: {e}")

        else:
            st.warning("Expense name aur valid amount enter karo.")


# --------------------------------
# VIEW, EDIT AND DELETE EXPENSES
# --------------------------------

elif page == "View Expenses":

    st.title("📋 Your Expenses")

    if not df.empty:

        search = st.text_input("🔍 Search by Expense Name")

        view_df = df.copy()

        if search:
            view_df = view_df[
                view_df["name"].str.contains(
                    search,
                    case=False,
                    na=False
                )
            ]

        view_df["expense_date"] = (
            view_df["expense_date"].dt.strftime("%d-%m-%Y")
        )

        st.dataframe(
            view_df[["name", "amount", "category", "expense_date"]],
            width="stretch",
            hide_index=True
        )

        st.download_button(
            "⬇️ Download CSV",
            data=view_df.to_csv(index=False),
            file_name="my_expenses.csv",
            mime="text/csv"
        )

        st.divider()

        # EDIT EXPENSE

        st.subheader("✏️ Edit Expense")

        selected_id = st.selectbox(
            "Select Expense",
            df["id"].tolist(),
            format_func=lambda x: (
                f"{df.loc[df['id'] == x, 'name'].iloc[0]} - "
                f"₹{df.loc[df['id'] == x, 'amount'].iloc[0]}"
            )
        )

        selected = df[df["id"] == selected_id].iloc[0]

        with st.form("edit_expense_form"):

            edit_name = st.text_input(
                "Expense Name",
                value=selected["name"]
            )

            edit_amount = st.number_input(
                "Amount (₹)",
                min_value=0.0,
                value=float(selected["amount"]),
                step=1.0
            )

            categories = [
                "Food", "Travel", "Shopping", "Education", "Other"
            ]

            old_category = selected["category"]

            category_index = (
                categories.index(old_category)
                if old_category in categories
                else 4
            )

            edit_category = st.selectbox(
                "Category",
                categories,
                index=category_index
            )

            old_date = selected["expense_date"]

            if pd.isna(old_date):
                old_date = pd.Timestamp.today().date()
            else:
                old_date = old_date.date()

            edit_date = st.date_input(
                "Date",
                value=old_date
            )

            update_button = st.form_submit_button(
                "Update Expense",
                type="primary"
            )

        if update_button:

            if edit_name.strip() and edit_amount > 0:

                try:

                    supabase.table("expenses").update({
                        "name": edit_name.strip(),
                        "amount": edit_amount,
                        "category": edit_category,
                        "expense_date": edit_date.isoformat()
                    }).eq(
                        "id", selected_id
                    ).eq(
                        "user_id", user_id
                    ).execute()

                    st.success("Expense updated successfully!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Update failed: {e}")

            else:
                st.warning("Valid name aur amount enter karo.")

        st.divider()

        # DELETE EXPENSE

        st.subheader("🗑️ Delete Expense")

        if st.button("Delete Selected Expense"):

            st.session_state.confirm_delete = True

        if st.session_state.get("confirm_delete", False):

            st.warning("Kya tum ye expense delete karna chahte ho?")

            col1, col2 = st.columns(2)

            with col1:

                if st.button("Yes, Delete"):

                    try:

                        supabase.table("expenses").delete().eq(
                            "id", selected_id
                        ).eq(
                            "user_id", user_id
                        ).execute()

                        st.session_state.confirm_delete = False

                        st.success("Expense deleted!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Delete failed: {e}")

            with col2:

                if st.button("Cancel"):
                    st.session_state.confirm_delete = False
                    st.rerun()

    else:

        st.info("Abhi koi expense available nahi hai. Pehle expense add karo.")


# --------------------------------
# REPORTS AND PERSONAL BUDGET
# --------------------------------

elif page == "Reports":

    st.title("📊 Reports")

    # CATEGORY-WISE REPORT

    st.subheader("Category-wise Spending")

    if not df.empty:

        category_total = df.groupby("category")["amount"].sum()

        st.bar_chart(category_total)

        percentage = (
            category_total / category_total.sum() * 100
        ).round(2)

        st.dataframe(
            percentage.rename("Spending (%)").to_frame(),
            width="stretch"
        )

    else:

        st.info("Reports ke liye pehle expenses add karo.")

    st.divider()

    # PERSONAL MONTHLY BUDGET

    st.subheader("💰 Your Monthly Budget")

    budget = st.number_input(
        "Enter Monthly Budget (₹)",
        min_value=0.0,
        value=float(saved_budget),
        step=100.0
    )

    if st.button("Save Budget", type="primary"):

        try:

            save_budget(budget)

            st.success("Your personal budget saved!")
            st.rerun()

        except Exception as e:
            st.error(f"Budget save nahi hua: {e}")

    # CURRENT MONTH SPENDING

    today = pd.Timestamp.today()

    if not df.empty:

        current_month_df = df[
            (df["expense_date"].dt.month == today.month) &
            (df["expense_date"].dt.year == today.year)
        ]

        current_spending = current_month_df["amount"].sum()

    else:

        current_spending = 0

    remaining = budget - current_spending

    col1, col2, col3 = st.columns(3)

    col1.metric("Monthly Budget", f"₹{budget:.2f}")
    col2.metric("Current Month Spending", f"₹{current_spending:.2f}")
    col3.metric("Remaining Budget", f"₹{remaining:.2f}")

    if remaining < 0:
        st.error("Warning! Monthly budget cross ho gaya hai.")
    else:
        st.success("You are within your monthly budget!")

    st.divider()

    # MONTHLY SUMMARY

    st.subheader("📅 Monthly Spending Summary")

    if not df.empty:

        monthly_df = df.dropna(subset=["expense_date"]).copy()

        monthly_df["Month"] = (
            monthly_df["expense_date"].dt.to_period("M")
        )

        monthly_total = (
            monthly_df.groupby("Month")["amount"].sum()
        )

        monthly_total.index = monthly_total.index.strftime("%B %Y")

        st.bar_chart(monthly_total)

        st.dataframe(
            monthly_total.rename("Total Spending (₹)").to_frame(),
            width="stretch"
        )

    else:

        st.info("Monthly summary ke liye expenses available nahi hain.")
