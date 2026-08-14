# CODEx Academy

Learn Skills. Build Your Future.

CODEx Academy is an e-learning platform for learners in Northern Nigeria, with course experiences planned in Hausa and English. This repository currently contains a Vite frontend prototype and the Phase 1 Flask backend foundation.

## Phase 1 Backend

Phase 1 includes:

- Modular Flask application factory.
- PostgreSQL-ready SQLAlchemy configuration.
- Flask-Migrate migration setup.
- User model with secure Werkzeug password hashing.
- JWT authentication with token revocation on logout.
- Role-based authorization decorators for students, instructors, and admins.
- Consistent JSON success and error responses.
- Centralized error handling.

## Phase 2 Backend

Phase 2 adds the Course Management Engine:

- Categories.
- Courses with draft, pending, published, and rejected workflow.
- Modules and lessons with ordering.
- Lesson resources stored as cloud-ready URL references.
- Instructor applications with admin approval.
- Instructor-only course ownership controls.
- Public course catalog and course details APIs.
- Admin course and instructor review APIs.
- Phase 2 migration and pytest coverage.

## Backend Structure

```text
app/
  __init__.py
  extensions.py
  responses.py
  security.py
  models/
    __init__.py
    user.py
  routes/
    __init__.py
    admin.py
    auth.py
    courses.py
    errors.py
    helpers.py
    instructors.py
  services/
    __init__.py
    storage_service.py
migrations/
  versions/
    202608110001_create_users_and_token_blocklist.py
    202608110002_add_course_management_engine.py
config.py
run.py
requirements.txt
.env.example
```

## Database Relationships

Phase 1 creates `users` and `token_blocklist`.

- One `User` can have many revoked JWT records.
- `token_blocklist.user_id` references `users.id` with cascade delete.
- One `User` can have many courses as an instructor.
- One `User` can have many instructor applications.
- One `Category` can contain many courses.
- One `Course` belongs to an instructor and category.
- One `Course` can have many modules.
- One `Module` can have many lessons.
- One `Lesson` can have many lesson resources.

## Install Backend Dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configure Environment

Copy `.env.example` to `.env` and set values for your machine.

```env
SECRET_KEY=change-this-to-a-long-random-secret
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/codex_academy
PAYSTACK_SECRET_KEY=
PAYSTACK_PUBLIC_KEY=
FLASK_ENV=development
JWT_ACCESS_TOKEN_MINUTES=120
```

Use PostgreSQL for production. SQLite is only reserved for automated tests in later phases.

## Database Migration Commands

```bash
flask --app run:app db upgrade
```

For future schema changes:

```bash
flask --app run:app db migrate -m "describe change"
flask --app run:app db upgrade
```

If starting a fresh migration folder in another environment:

```bash
flask --app run:app db init
flask --app run:app db migrate -m "initial schema"
flask --app run:app db upgrade
```

## Run Backend

Development:

```bash
flask --app run:app --debug run
```

Production-style:

```bash
gunicorn "run:app"
```

## Phase 1 API

All responses use this shape:

```json
{
  "success": true,
  "message": "Action completed",
  "data": {}
}
```

Errors use:

```json
{
  "success": false,
  "message": "Request failed",
  "error": "ERROR_CODE"
}
```

### GET /api/health

Authentication: none

Checks that the backend is running.

```bash
curl http://127.0.0.1:5000/api/health
```

### POST /api/auth/register

Authentication: none

Registers a student account. Email addresses are unique and passwords are hashed before storage.

Request body:

```json
{
  "full_name": "Amina Musa",
  "email": "amina@example.com",
  "phone": "+2348012345678",
  "password": "securepass123"
}
```

Example:

```bash
curl -X POST http://127.0.0.1:5000/api/auth/register ^
  -H "Content-Type: application/json" ^
  -d "{\"full_name\":\"Amina Musa\",\"email\":\"amina@example.com\",\"password\":\"securepass123\"}"
```

Possible errors: `VALIDATION_ERROR`, `EMAIL_ALREADY_EXISTS`.

### POST /api/auth/login

Authentication: none

Validates credentials, checks account status, and returns a Bearer token plus the role dashboard path.

Request body:

```json
{
  "email": "amina@example.com",
  "password": "securepass123"
}
```

Example:

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"amina@example.com\",\"password\":\"securepass123\"}"
```

Possible errors: `MISSING_CREDENTIALS`, `INVALID_CREDENTIALS`, `ACCOUNT_INACTIVE`.

### GET /api/auth/me

Authentication: Bearer token

Returns the authenticated user without exposing the password hash.

```bash
curl http://127.0.0.1:5000/api/auth/me ^
  -H "Authorization: Bearer YOUR_TOKEN"
```

Possible errors: `AUTHENTICATION_REQUIRED`, `TOKEN_EXPIRED`, `INVALID_TOKEN`, `TOKEN_REVOKED`, `USER_NOT_FOUND`, `ACCOUNT_INACTIVE`.

### POST /api/auth/logout

Authentication: Bearer token

Revokes the current JWT by storing its unique token ID in `token_blocklist`.

```bash
curl -X POST http://127.0.0.1:5000/api/auth/logout ^
  -H "Authorization: Bearer YOUR_TOKEN"
```

Possible errors: `AUTHENTICATION_REQUIRED`, `TOKEN_EXPIRED`, `INVALID_TOKEN`, `TOKEN_REVOKED`.

### POST /api/auth/forgot-password

Authentication: none

Accepts an email address and returns a generic response to avoid account enumeration.

Request body:

```json
{
  "email": "amina@example.com"
}
```

Example:

```bash
curl -X POST http://127.0.0.1:5000/api/auth/forgot-password ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"amina@example.com\"}"
```

Possible errors: `VALIDATION_ERROR`.

## Phase 2 API

### Public Catalog

- `GET /api/categories`
- `GET /api/categories/<id>/courses`
- `GET /api/courses`
- `GET /api/courses/<id>`
- `GET /api/courses/<id>/lessons`

`GET /api/courses` supports `search`, `category`, `language`, `level`, `min_price`, `max_price`, `page`, and `per_page`.

Only published courses are returned publicly. Non-preview lesson video URLs are hidden from public course responses.

### Instructor

Authentication: Bearer token.

Only users whose role has been changed to `instructor` by admin approval can manage courses.

- `POST /api/instructor/apply`
- `GET /api/instructor/application`
- `POST /api/instructor/courses`
- `GET /api/instructor/courses`
- `GET /api/instructor/courses/<id>`
- `PUT /api/instructor/courses/<id>`
- `DELETE /api/instructor/courses/<id>`
- `POST /api/instructor/courses/<id>/submit`
- `POST /api/instructor/courses/<course_id>/modules`
- `PUT /api/instructor/modules/<id>`
- `DELETE /api/instructor/modules/<id>`
- `POST /api/instructor/modules/<module_id>/lessons`
- `PUT /api/instructor/lessons/<id>`
- `DELETE /api/instructor/lessons/<id>`
- `POST /api/instructor/lessons/<lesson_id>/resources`

All course, module, lesson, and resource mutation endpoints verify ownership before changing data.

### Admin

Authentication: Bearer token with `admin` role.

- `POST /api/admin/categories`
- `GET /api/admin/instructor-applications`
- `PATCH /api/admin/instructor-applications/<id>/approve`
- `PATCH /api/admin/instructor-applications/<id>/reject`
- `GET /api/admin/courses/pending`
- `PATCH /api/admin/courses/<id>/approve`
- `PATCH /api/admin/courses/<id>/reject`

Approving an instructor application changes the applicant role to `instructor`. Approving a pending course publishes it. Rejecting a course stores `admin_note` and lets the instructor edit and resubmit.

## Frontend Prototype

The existing frontend remains a Vite prototype.

```bash
npm install
npm run dev
```

Included prototype flows:

- Landing page.
- Registration and login screens.
- Student dashboard.
- Course catalog and details.
- Checkout simulation.
- Lesson and progress screens.
- Instructor application screen.
- Admin dashboard mockup.

The production frontend should call the Flask REST APIs as backend phases are completed.
