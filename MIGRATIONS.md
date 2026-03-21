# ET_CREDGEN Database Migration Guide

Follow these steps to migrate from CSV storage to PostgreSQL and set up the new authentication system.

## Prerequisites
- PostgreSQL installed and running
- Python 3.9+ installed

## Step 1: Create Database
```bash
createdb credgen
```

## Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

## Step 3: Configure Environment
Copy `.env.example` to `.env` and fill in all values.
```bash
cp .env.example .env
```
Ensure `DATABASE_URL` is correct: `postgresql://user:password@localhost:5432/credgen`

## Step 4: Initialize Migrations
```bash
flask db init
```

## Step 5: Create Initial Migration
```bash
flask db migrate -m "initial schema"
```

## Step 6: Apply Migrations
```bash
flask db upgrade
```

## Step 7: Seed Admin User
Set `SEED_ADMIN_USERNAME`, `SEED_ADMIN_EMAIL`, and `SEED_ADMIN_PASSWORD` in your `.env` file first.
```bash
python seed_admin.py
```

## Step 8: Migrate Legacy CSV Data
Only run this if you have existing data in the `csv/` directory.
```bash
python migrate_csv.py
```

## Step 9: Start Application
```bash
python app.py
```
