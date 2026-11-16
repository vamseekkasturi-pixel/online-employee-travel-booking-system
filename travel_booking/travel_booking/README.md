# Online Employee Travel Booking System

A simple base project where employees raise travel requests and an admin approves or rejects them.
Built with **Flask + SQLite** (no external services needed).

## Features

**Employee**
- Register / login / logout
- Dashboard with request counts and upcoming approved trips
- Create a travel request (mode, route, dates, purpose, estimated cost, hotel needed)
- View own bookings with status and admin remarks
- Cancel a pending or approved booking

**Admin**
- Approvals dashboard with status filter tabs and counts
- Approve or reject pending requests (a remark is required when rejecting)

**Built in**
- Password hashing, session login, role-based access, CSRF tokens on every POST
- Server-side validation (dates, cost, route, mode)
- SQLite database created and seeded automatically on first run

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

| Role     | Email                 | Password      |
|----------|-----------------------|---------------|
| Admin    | admin@company.com     | admin123      |
| Employee | employee@company.com  | employee123   |

Change `SECRET_KEY` (environment variable) before any real deployment.

## Structure

```
travel_booking/
├── app.py              # routes, DB schema, validation
├── requirements.txt
├── templates/          # Jinja pages (base, login, register, dashboard, bookings, admin, error)
├── static/style.css
└── travel.db           # created on first run
```

## Ideas for extending

- Real flight/train/hotel search APIs, per-department budgets, multi-level approval
- Email notifications, PDF itineraries, expense claims after the trip
