import streamlit as st
import mysql.connector

config = st.secrets["database"]

try:
    conn = mysql.connector.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
    )

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM employees")
    print("Employees found:", cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM attendance")
    print("Attendance entries:", cursor.fetchone()[0])

    cursor.close()
    conn.close()

except Exception as e:
    print("Database connection failed:", e)