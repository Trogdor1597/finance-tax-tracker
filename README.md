# Lesson Finance Tracker

A lightweight, secure Flask web application for private music teachers (or tutors) to track income, mileage, and expenses.

## Features
* **Income Logging:** Automatically calculates 20% tax set-aside and net revenue.
* **Secure:** Admin-only "Manage" area requires a secondary password to delete entries.
* **Customizable:** Configure payment methods and expense accounts via environment variables.
* **Privacy First:** Self-hosted, local CSV storage (no external database required).
* **Mobile Friendly:** Designed for quick entry on mobile browsers.

## Installation

1.  Clone the repository.
2.  Create a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Create a `.env` file based on `env.example` and configure your `PAYMENT_SOURCES` and `EXPENSE_ACCOUNTS`.
5.  Run the app:
    ```bash
    python app.py
    ```

## Deployment Strategy
This application is designed to be self-hosted on a Linux server. 

In my production environment, I use a **Cloudflare Tunnel** to securely expose the local Flask application to the web. This allows the app to be accessible via a public domain while keeping the server's firewall ports closed for security.
