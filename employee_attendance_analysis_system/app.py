
import os
from datetime import date, timedelta

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import mysql.connector
from mysql.connector import Error


st.set_page_config(
    page_title="Employee Attendance Analysis",
    page_icon="📊",
    layout="wide",
)

STATUSES = ["Present", "Absent", "Leave", "Holiday"]


# --------------------------------------------------
# DATABASE CONFIGURATION
# --------------------------------------------------


def get_setting(env_name, secret_name=None, default=None):
    """Read settings from environment variables or Streamlit secrets."""

    value = os.getenv(env_name)
    if value is not None:
        return value

    secret_name = secret_name or env_name

    # Match environment variable names to TOML keys.
    mysql_key_map = {
        "DB_HOST": "host",
        "DB_PORT": "port",
        "DB_USER": "user",
        "DB_PASSWORD": "password",
        "DB_NAME": "database",
    }

    try:
        mysql_secrets = st.secrets.get("mysql", {})
        key = mysql_key_map.get(env_name, secret_name)

        value = mysql_secrets.get(key)
        if value is not None:
            return value

        value = st.secrets.get(secret_name)
        if value is not None:
            return value

    except Exception:
        pass

    return default


def get_connection():
    """Connect to the configured MySQL database."""

    try:
        host = get_setting("DB_HOST", default="localhost")
        port = int(get_setting("DB_PORT", default="3306"))
        user = get_setting("DB_USER", default="root")
        password = get_setting("DB_PASSWORD", default="")
        database = get_setting(
            "DB_NAME", default="employee_attendance"
        )

        if not password:
            raise ValueError(
                "MySQL password is missing. Set DB_PASSWORD "
                "in .streamlit/secrets.toml or your environment."
            )

        return mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connection_timeout=5,
        )

    except Exception as exc:
        if not st.session_state.get("db_error_shown", False):
            st.error("Could not connect to the MySQL database.")
            st.caption(str(exc))
            st.info(
                "Check your MySQL service, database name, "
                "username, password, and secrets.toml file."
            )
            st.session_state["db_error_shown"] = True

        return None


# --------------------------------------------------
# DATABASE TABLE INITIALIZATION
# --------------------------------------------------

def initialize_database():
    """Create application tables if they do not exist."""

    conn = get_connection()

    if conn is None:
        return False

    cursor = None

    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                employee_id INT AUTO_INCREMENT PRIMARY KEY,
                employee_code VARCHAR(30) NOT NULL UNIQUE,
                employee_name VARCHAR(100) NOT NULL,
                department VARCHAR(100) NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                attendance_id INT AUTO_INCREMENT PRIMARY KEY,
                employee_id INT NOT NULL,
                attendance_date DATE NOT NULL,
                status ENUM(
                    'Present', 'Absent', 'Leave', 'Holiday'
                ) NOT NULL,
                UNIQUE KEY unique_employee_date (
                    employee_id, attendance_date
                ),
                CONSTRAINT fk_attendance_employee
                    FOREIGN KEY (employee_id)
                    REFERENCES employees(employee_id)
                    ON DELETE CASCADE
            )
        """)

        conn.commit()
        return True

    except Error as exc:
        st.error(f"Could not initialize database tables: {exc}")
        return False

    finally:
        if cursor:
            cursor.close()
        conn.close()


# --------------------------------------------------
# QUERY HELPER
# --------------------------------------------------

def run_query(query, params=None, fetch=False):
    conn = get_connection()

    if conn is None:
        return None if fetch else False

    cursor = None

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())

        if fetch:
            return cursor.fetchall()

        conn.commit()
        return True

    except Error as exc:
        st.error(f"Database query failed: {exc}")
        return None if fetch else False

    finally:
        if cursor:
            cursor.close()
        conn.close()


# --------------------------------------------------
# LOAD EMPLOYEES AND ATTENDANCE
# --------------------------------------------------

def load_employees():
    rows = run_query("""
        SELECT employee_id, employee_code,
               employee_name, department
        FROM employees
        ORDER BY employee_name
    """, fetch=True)

    if rows is None:
        return None

    return pd.DataFrame(
        rows,
        columns=[
            "employee_id",
            "employee_code",
            "employee_name",
            "department",
        ],
    )


def load_attendance(
    start_date=None,
    end_date=None,
    employee_id=None,
):
    query = """
        SELECT a.attendance_id,
               e.employee_id,
               e.employee_code,
               e.employee_name,
               e.department,
               a.attendance_date,
               a.status
        FROM attendance a
        JOIN employees e
          ON e.employee_id = a.employee_id
        WHERE 1=1
    """

    params = []

    if start_date:
        query += " AND a.attendance_date >= %s"
        params.append(start_date)

    if end_date:
        query += " AND a.attendance_date <= %s"
        params.append(end_date)

    if employee_id is not None:
        query += " AND e.employee_id = %s"
        params.append(int(employee_id))

    query += " ORDER BY a.attendance_date DESC, e.employee_name"

    rows = run_query(query, params, fetch=True)

    if rows is None:
        return None

    df = pd.DataFrame(rows)

    if not df.empty:
        df["attendance_date"] = pd.to_datetime(
            df["attendance_date"]
        )

    return df


def attendance_percentage(df):
    """Exclude holidays from the attendance percentage."""

    if df.empty:
        return 0.0

    working = df[
        df["status"].isin(["Present", "Absent", "Leave"])
    ]

    if working.empty:
        return 0.0

    return round(
        (working["status"].eq("Present").sum()
         / len(working)) * 100,
        2,
    )


# --------------------------------------------------
# APPLICATION HEADER AND NAVIGATION
# --------------------------------------------------

st.title("📊 Employee Attendance Analysis System")
st.write(
    "Manage employee records, record daily attendance, "
    "and analyze monthly attendance patterns."
)

with st.sidebar:
    st.header("Navigation")

    page = st.radio(
        "Choose a page",
        [
            "Dashboard",
            "Manage Employees",
            "Record Attendance",
            "Attendance Records",
            "Monthly Reports",
        ],
    )

    st.divider()
    st.caption("Employee Attendance Management")


# Initialize database tables after connecting.
if not st.session_state.get("db_initialized", False):
    st.session_state["db_initialized"] = initialize_database()

if not st.session_state["db_initialized"]:
    st.warning(
        "Database setup is incomplete. Check the database "
        "configuration below before using the application."
    )
    st.stop()


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

if page == "Dashboard":
    st.subheader("Dashboard")

    employees = load_employees()
    records = load_attendance()

    if employees is None or records is None:
        st.warning("Dashboard data could not be loaded.")
        st.stop()

    total_employees = len(employees)
    total_records = len(records)

    present_count = (
        int((records["status"] == "Present").sum())
        if not records.empty else 0
    )

    absent_count = (
        int((records["status"] == "Absent").sum())
        if not records.empty else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Employees", total_employees)
    c2.metric("Attendance entries", total_records)
    c3.metric("Present records", present_count)
    c4.metric("Absent records", absent_count)

    if records.empty:
        st.info(
            "No attendance records found. Add employees "
            "and record attendance to get started."
        )
        st.caption(
            "Charts will appear after attendance has been recorded."
        )
    else:
        records["month"] = (
            records["attendance_date"].dt.to_period("M").astype(str)
        )

        monthly = (
            records[
                records["status"].isin(
                    ["Present", "Absent", "Leave"]
                )
            ]
            .groupby(["month", "status"])
            .size()
            .unstack(fill_value=0)
        )

        st.markdown("### Monthly attendance overview")
        st.bar_chart(monthly)

        st.markdown("### Recent records")

        st.dataframe(
            records.drop(columns=["attendance_id"], errors="ignore"),
            use_container_width=True,
        )


# --------------------------------------------------
# MANAGE EMPLOYEES
# --------------------------------------------------

elif page == "Manage Employees":
    st.subheader("Manage Employees")

    with st.form("add_employee", clear_on_submit=True):
        st.markdown("#### Add a new employee")

        code = st.text_input(
            "Employee code", placeholder="EMP001"
        )
        name = st.text_input("Employee name")
        department = st.text_input(
            "Department", placeholder="Engineering"
        )

        submitted = st.form_submit_button("Add employee")

        if submitted:
            if not code.strip() or not name.strip() or not department.strip():
                st.warning("Please fill in all fields.")
            else:
                ok = run_query(
                    """
                    INSERT INTO employees
                        (employee_code, employee_name, department)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        code.strip(),
                        name.strip(),
                        department.strip(),
                    ),
                )

                if ok:
                    st.success("Employee added successfully.")
                    st.rerun()

    employees = load_employees()

    if employees is None:
        st.stop()

    st.markdown("#### Employee list")

    if employees.empty:
        st.info("No employees have been added yet.")
    else:
        st.dataframe(
            employees.drop(columns=["employee_id"]),
            use_container_width=True,
        )

        with st.form("delete_employee"):
            options = {
                f"{row.employee_code} — {row.employee_name}":
                    int(row.employee_id)
                for row in employees.itertuples()
            }

            selected = st.selectbox(
                "Select employee to delete",
                list(options.keys()),
            )

            confirm = st.checkbox(
                "I understand that deleting an employee "
                "also deletes their attendance records."
            )

            delete = st.form_submit_button("Delete employee")

            if delete:
                if not confirm:
                    st.warning("Please confirm before deleting.")
                else:
                    ok = run_query(
                        "DELETE FROM employees WHERE employee_id = %s",
                        (options[selected],),
                    )

                    if ok:
                        st.success(
                            "Employee and attendance records deleted."
                        )
                        st.rerun()


# --------------------------------------------------
# RECORD ATTENDANCE
# --------------------------------------------------

elif page == "Record Attendance":
    st.subheader("Record Daily Attendance")

    employees = load_employees()

    if employees is None:
        st.stop()

    if employees.empty:
        st.warning(
            "Add an employee first using Manage Employees."
        )
    else:
        options = {
            f"{row.employee_code} — {row.employee_name} "
            f"({row.department})": int(row.employee_id)
            for row in employees.itertuples()
        }

        with st.form("record_attendance", clear_on_submit=True):
            selected = st.selectbox(
                "Employee", list(options.keys())
            )

            attendance_date = st.date_input(
                "Attendance date",
                value=date.today(),
                max_value=date.today(),
            )

            status = st.selectbox("Status", STATUSES)

            save = st.form_submit_button("Save attendance")

            if save:
                ok = run_query(
                    """
                    INSERT INTO attendance
                        (employee_id, attendance_date, status)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        status = VALUES(status)
                    """,
                    (
                        options[selected],
                        attendance_date,
                        status,
                    ),
                )

                if ok:
                    st.success(
                        "Attendance saved successfully. "
                        "An existing employee/date record was "
                        "updated if necessary."
                    )

        st.info(
            "Only one attendance entry is allowed per employee "
            "per date. Saving again updates the status."
        )


# --------------------------------------------------
# ATTENDANCE RECORDS
# --------------------------------------------------

elif page == "Attendance Records":
    st.subheader("Attendance Records")

    c1, c2 = st.columns(2)

    start = c1.date_input(
        "From date",
        value=date.today() - timedelta(days=30),
        key="record_start",
    )

    end = c2.date_input(
        "To date",
        value=date.today(),
        key="record_end",
    )

    if start > end:
        st.error("The start date must be on or before the end date.")
    else:
        records = load_attendance(start, end)

        if records is None:
            st.stop()

        if records.empty:
            st.info("No attendance records found for this date range.")
        else:
            display_records = records.drop(
                columns=["attendance_id"], errors="ignore"
            )

            st.dataframe(
                display_records,
                use_container_width=True,
            )

            st.download_button(
                "Download records as CSV",
                display_records.to_csv(index=False).encode("utf-8"),
                file_name="attendance_records.csv",
                mime="text/csv",
            )


# --------------------------------------------------
# MONTHLY REPORTS
# --------------------------------------------------

elif page == "Monthly Reports":
    st.subheader("Monthly Reports")

    employees = load_employees()

    if employees is None:
        st.stop()

    if employees.empty:
        st.info("Add employees and attendance records first.")
    else:
        today = date.today()

        month = st.date_input(
            "Choose any date in the month",
            value=today,
            key="report_month",
        )

        start = date(month.year, month.month, 1)

        if month.month == 12:
            end = date(month.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(
                month.year, month.month + 1, 1
            ) - timedelta(days=1)

        records = load_attendance(start, end)

        if records is None:
            st.stop()

        if records.empty:
            st.info("No attendance records for the selected month.")
        else:
            st.caption(
                f"Reporting period: {start:%d %b %Y} "
                f"– {end:%d %b %Y}"
            )

            working = records[
                records["status"].isin(
                    ["Present", "Absent", "Leave"]
                )
            ]

            summary = working.groupby(
                [
                    "employee_id",
                    "employee_code",
                    "employee_name",
                    "department",
                ],
                as_index=False,
            ).agg(
                working_day_records=("status", "size"),
                present_days=(
                    "status",
                    lambda s: int((s == "Present").sum()),
                ),
                absent_days=(
                    "status",
                    lambda s: int((s == "Absent").sum()),
                ),
                leave_days=(
                    "status",
                    lambda s: int((s == "Leave").sum()),
                ),
            )

            summary["attendance_percentage"] = np.where(
                summary["working_day_records"] > 0,
                np.round(
                    summary["present_days"]
                    / summary["working_day_records"] * 100,
                    2,
                ),
                0,
            )

            st.markdown("#### Employee-wise monthly summary")

            st.dataframe(
                summary.drop(columns=["employee_id"]),
                use_container_width=True,
            )

            st.download_button(
                "Download monthly summary as CSV",
                summary.drop(
                    columns=["employee_id"]
                ).to_csv(index=False).encode("utf-8"),
                file_name=f"attendance_summary_{month:%Y_%m}.csv",
                mime="text/csv",
            )

            st.markdown("#### Department summary")

            dept = summary.groupby(
                "department", as_index=False
            ).agg(
                employees=("employee_code", "nunique"),
                present_days=("present_days", "sum"),
                absent_days=("absent_days", "sum"),
                leave_days=("leave_days", "sum"),
            )

            st.dataframe(dept, use_container_width=True)

            st.markdown("#### Absenteeism chart")

            if not summary.empty:
                chart_data = (
                    summary.sort_values(
                        "absent_days", ascending=False
                    )
                    .set_index("employee_name")["absent_days"]
                )

                fig, ax = plt.subplots(figsize=(10, 4))
                chart_data.plot(kind="bar", ax=ax)

                ax.set_title("Absent days by employee")
                ax.set_xlabel("Employee")
                ax.set_ylabel("Absent days")
                ax.tick_params(axis="x", labelrotation=35)

                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
