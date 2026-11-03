
import streamlit as st
import pandas as pd
import plotly.express as px

from supabase import create_client
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)


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

except Exception:
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

if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = False

if "pending_delete_id" not in st.session_state:
    st.session_state.pending_delete_id = None


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
# PDF REPORT GENERATOR
# --------------------------------

def create_pdf_report(report_df):

    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=25,
        textColor=colors.HexColor("#17365D"),
        alignment=TA_CENTER,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_CENTER,
        spaceAfter=15
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#17365D"),
        fontSize=14,
        spaceBefore=12,
        spaceAfter=8
    )

    cell_style = ParagraphStyle(
        "CellStyle",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10
    )

    elements = []

    # TITLE

    elements.append(
        Paragraph("MY EXPENSE TRACKER", title_style)
    )

    elements.append(
        Paragraph("PERSONAL EXPENSE REPORT", subtitle_style)
    )

    report_date = pd.Timestamp.today().strftime("%d %B %Y")

    elements.append(
        Paragraph(
            f"<b>Report Generated:</b> {report_date}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 15))

    # SUMMARY

    total_expenses = len(report_df)
    total_amount = report_df["amount"].sum()

    average_amount = (
        total_amount / total_expenses
        if total_expenses > 0 else 0
    )

    summary_data = [
        ["TOTAL EXPENSES", "TOTAL SPENDING", "AVERAGE EXPENSE"],
        [
            str(total_expenses),
            f"Rs. {total_amount:,.2f}",
            f"Rs. {average_amount:,.2f}"
        ]
    ]

    summary_table = Table(
        summary_data,
        colWidths=[85 * mm, 85 * mm, 85 * mm]
    )

    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#EAF2F8")),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#17365D")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
        ("BOX", (0, 0), (-1, -1), 1, colors.lightgrey),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white)
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 18))

    # CATEGORY-WISE SUMMARY

    elements.append(
        Paragraph("Category-wise Spending", heading_style)
    )

    if not report_df.empty:

        category_total = (
            report_df.groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
        )

        category_rows = [
            ["Category", "Amount (Rs.)", "Percentage"]
        ]

        for category, amount in category_total.items():

            percentage = (
                amount / total_amount * 100
                if total_amount > 0 else 0
            )

            category_rows.append([
                escape(str(category)),
                f"{amount:,.2f}",
                f"{percentage:.1f}%"
            ])

        category_table = Table(
            category_rows,
            colWidths=[90 * mm, 90 * mm, 75 * mm]
        )

        category_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2874A6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#EBF5FB")
            ]),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8)
        ]))

        elements.append(category_table)

    elements.append(Spacer(1, 18))

    # COMPLETE EXPENSE DETAILS

    elements.append(
        Paragraph("Complete Expense Details", heading_style)
    )

    expense_rows = [
        ["Date", "Expense Name", "Category", "Amount (Rs.)"]
    ]

    for _, row in report_df.iterrows():

        date_value = row["expense_date"]

        if pd.notna(date_value):
            date_text = date_value.strftime("%d-%m-%Y")
        else:
            date_text = "-"

        expense_rows.append([
            date_text,
            Paragraph(escape(str(row["name"])), cell_style),
            escape(str(row["category"])),
            f"{row['amount']:,.2f}"
        ])

    expense_table = Table(
        expense_rows,
        colWidths=[45 * mm, 100 * mm, 65 * mm, 45 * mm],
        repeatRows=1
    )

    expense_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#F2F6FA")
        ]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
    ]))

    elements.append(expense_table)
    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            "Thank you for using My Expense Tracker!",
            subtitle_style
        )
    )

    pdf.build(elements)

    buffer.seek(0)

    return buffer.getvalue()


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
# PREMIUM DASHBOARD
# --------------------------------

if page == "Dashboard":

    # Custom dashboard styling

    st.markdown("""
        <style>
        .dashboard-header {
            background: linear-gradient(120deg, #101C3A, #263F70);
            padding: 28px;
            border-radius: 18px;
            margin-bottom: 25px;
            color: white;
        }

        .dashboard-header h1 {
            color: white;
            margin-bottom: 5px;
        }

        .dashboard-header p {
            color: #CBD5E1;
            margin: 0;
        }

        .stat-card {
            background: linear-gradient(145deg, #172554, #263B69);
            padding: 20px;
            border-radius: 15px;
            border: 1px solid #334B78;
            min-height: 125px;
        }

        .stat-label {
            color: #CBD5E1;
            font-size: 14px;
            margin-bottom: 12px;
        }

        .stat-value {
            color: white;
            font-size: 25px;
            font-weight: 700;
        }

        .stat-icon {
            font-size: 22px;
            margin-bottom: 8px;
        }

        .section-heading {
            font-size: 21px;
            font-weight: 650;
            margin-top: 15px;
            margin-bottom: 12px;
        }
        </style>
    """, unsafe_allow_html=True)

    # Date and monthly calculations

    today = pd.Timestamp.today()

    valid_df = df.dropna(subset=["expense_date"]).copy()

    current_month_df = valid_df[
        (valid_df["expense_date"].dt.month == today.month) &
        (valid_df["expense_date"].dt.year == today.year)
    ]

    total_expenses = len(df)
    total_spending = float(df["amount"].sum())

    current_spending = float(current_month_df["amount"].sum())

    highest_expense = (
        float(df["amount"].max()) if not df.empty else 0
    )

    remaining_budget = float(saved_budget) - current_spending

    budget_percentage = (
        current_spending / saved_budget * 100
        if saved_budget > 0 else 0
    )

    progress_value = min(budget_percentage / 100, 1.0)

    # Header

    st.markdown("""
        <div class="dashboard-header">
            <h1>Financial Overview</h1>
            <p>Welcome to your personal expense dashboard.</p>
        </div>
    """, unsafe_allow_html=True)

    st.caption(f"📅 {today.strftime('%d %B %Y')}")

    # Summary cards

    st.markdown(
        '<div class="section-heading">Your Financial Summary</div>',
        unsafe_allow_html=True
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">💸</div>
                <div class="stat-label">Total Expenses</div>
                <div class="stat-value">{total_expenses}</div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">💰</div>
                <div class="stat-label">Total Spending</div>
                <div class="stat-value">₹{total_spending:,.0f}</div>
            </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">🎯</div>
                <div class="stat-label">Monthly Budget</div>
                <div class="stat-value">₹{saved_budget:,.0f}</div>
            </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">💵</div>
                <div class="stat-label">Budget Remaining</div>
                <div class="stat-value">₹{remaining_budget:,.0f}</div>
            </div>
        """, unsafe_allow_html=True)

    st.write("")

    # Monthly budget progress

    st.markdown(
        '<div class="section-heading">Monthly Budget Usage</div>',
        unsafe_allow_html=True
    )

    st.progress(progress_value)

    budget_col1, budget_col2 = st.columns(2)

    with budget_col1:
        st.caption(
            f"Spent: ₹{current_spending:,.2f} "
            f"out of ₹{saved_budget:,.2f}"
        )

    with budget_col2:
        st.caption(f"{budget_percentage:.1f}% of budget used")

    if remaining_budget < 0:
        st.error(
            f"⚠️ You have exceeded your monthly budget by "
            f"₹{abs(remaining_budget):,.2f}."
        )

    elif budget_percentage >= 80:
        st.warning("You are close to your monthly budget limit!")

    else:
        st.success("You are within your monthly budget.")

    st.divider()

    # Spending analytics

    st.markdown(
        '<div class="section-heading">Spending Analytics</div>',
        unsafe_allow_html=True
    )

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:

        st.subheader("🍩 Category-wise Spending")

        if not df.empty:

            category_total = (
                df.groupby("category")["amount"]
                .sum()
                .reset_index()
            )

            fig = px.pie(
                category_total,
                names="category",
                values="amount",
                hole=0.55,
                template="plotly_dark"
            )

            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="white",
                margin=dict(t=20, b=20, l=10, r=10),
                legend_title_text="Categories"
            )

            fig.update_traces(
                textposition="inside",
                textinfo="percent"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        else:
            st.info("Category chart ke liye expenses add karo.")

    with chart_col2:

        st.subheader("📊 Monthly Spending")

        if not valid_df.empty:

            monthly_data = valid_df.copy()

            monthly_data["Month"] = (
                monthly_data["expense_date"].dt.strftime("%b %Y")
            )

            monthly_total = (
                monthly_data.groupby("Month")["amount"]
                .sum()
                .reset_index()
            )

            monthly_total["SortDate"] = pd.to_datetime(
                monthly_total["Month"],
                format="%b %Y"
            )

            monthly_total = monthly_total.sort_values("SortDate")

            fig2 = px.bar(
                monthly_total,
                x="Month",
                y="amount",
                template="plotly_dark",
                labels={
                    "Month": "Month",
                    "amount": "Spending (₹)"
                }
            )

            fig2.update_traces(
                marker_color="#3B82F6",
                marker_line_width=0
            )

            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="white",
                margin=dict(t=20, b=20, l=10, r=10),
                showlegend=False
            )

            st.plotly_chart(
                fig2,
                use_container_width=True
            )

        else:
            st.info("Monthly chart ke liye expenses add karo.")

    st.divider()

    # Recent transactions

    st.markdown(
        '<div class="section-heading">🧾 Recent Transactions</div>',
        unsafe_allow_html=True
    )

    if not df.empty:

        recent = df.head(5).copy()

        recent["expense_date"] = (
            recent["expense_date"].dt.strftime("%d-%m-%Y")
        )

        recent["amount"] = recent["amount"].apply(
            lambda x: f"₹{x:,.2f}"
        )

        recent = recent.rename(columns={
            "name": "Expense Name",
            "amount": "Amount",
            "category": "Category",
            "expense_date": "Date"
        })

        st.dataframe(
            recent[[
                "Expense Name",
                "Amount",
                "Category",
                "Date"
            ]],
            use_container_width=True,
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

                st.success(
                    "Your expense has been submitted successfully!"
                )

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

        display_df = view_df.copy()

        display_df["expense_date"] = (
            display_df["expense_date"].dt.strftime("%d-%m-%Y")
        )

        st.dataframe(
            display_df[[
                "name",
                "amount",
                "category",
                "expense_date"
            ]],
            width="stretch",
            hide_index=True
        )

        # PDF DOWNLOAD BUTTON

        st.subheader("📄 Download Your Expense Report")

        try:

            if not view_df.empty:

                pdf_data = create_pdf_report(view_df)

                st.download_button(
                    label="📄 Download PDF Report",
                    data=pdf_data,
                    file_name="My_Expense_Report.pdf",
                    mime="application/pdf",
                    type="primary",
                    width="stretch"
                )

            else:
                st.info(
                    "PDF report ke liye koi expense available nahi hai."
                )

        except Exception as e:
            st.error(f"PDF report generate nahi hui: {e}")

        st.divider()

        # EDIT EXPENSE

        st.subheader("✏️ Edit Expense")

        selected_id = st.selectbox(
            "Select Expense to Edit",
            df["id"].tolist(),
            format_func=lambda x: (
                f"{df.loc[df['id'] == x, 'name'].iloc[0]} - "
                f"₹{df.loc[df['id'] == x, 'amount'].iloc[0]}"
            ),
            key="edit_selected_id"
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

        delete_selected_id = st.selectbox(
            "Select Expense to Delete",
            df["id"].tolist(),
            format_func=lambda x: (
                f"{df.loc[df['id'] == x, 'name'].iloc[0]} - "
                f"₹{df.loc[df['id'] == x, 'amount'].iloc[0]}"
            ),
            key="delete_selected_id"
        )

        if st.button("Delete Selected Expense"):

            st.session_state.pending_delete_id = delete_selected_id
            st.session_state.confirm_delete = True

        if st.session_state.get("confirm_delete", False):

            pending_id = st.session_state.pending_delete_id

            if pending_id is not None:

                pending_expense = df[df["id"] == pending_id]

                if not pending_expense.empty:

                    expense_name = pending_expense.iloc[0]["name"]

                    st.warning(
                        f"Kya tum '{expense_name}' expense delete karna chahte ho?"
                    )

                    col1, col2 = st.columns(2)

                    with col1:

                        if st.button("Yes, Delete"):

                            try:
                                supabase.table("expenses").delete().eq(
                                    "id", pending_id
                                ).eq(
                                    "user_id", user_id
                                ).execute()

                                st.session_state.confirm_delete = False
                                st.session_state.pending_delete_id = None

                                st.success("Expense deleted successfully!")
                                st.rerun()

                            except Exception as e:
                                st.error(f"Delete failed: {e}")

                    with col2:

                        if st.button("Cancel"):

                            st.session_state.confirm_delete = False
                            st.session_state.pending_delete_id = None
                            st.rerun()

                else:
                    st.warning(
                        "Selected expense ab available nahi hai."
                    )

                    st.session_state.confirm_delete = False
                    st.session_state.pending_delete_id = None

            else:
                st.session_state.confirm_delete = False

    else:
        st.info(
            "Abhi koi expense available nahi hai. Pehle expense add karo."
        )


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
        st.info(
            "Monthly summary ke liye expenses available nahi hain."
        )
