from app import create_app
from app.extensions import db
from app.models import User, CodexStudentID
from app.security import generate_access_token

app = create_app()
with app.app_context():
    students = User.query.filter_by(role='student').all()
    print(f'Students: {len(students)}')
    for s in students:
        cid = CodexStudentID.query.filter_by(user_id=s.id).first()
        print(f'{s.full_name}: Codex ID={cid.codex_id if cid else None}')
    
    if students:
        student = students[0]
        token = generate_access_token(student)
        print(f'\nTest token for {student.full_name}:')
        print(token)
        print(f'\nTest command:')
        print(f'curl -H "Authorization: Bearer {token}" http://127.0.0.1:5000/api/student/codex-id')
