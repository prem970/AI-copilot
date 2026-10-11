"""Invite-only account provisioning. Passwords never appear in command arguments."""
import argparse
import getpass
from sqlalchemy import select, delete
from app.db import transaction
from app.models import User, Patient, AuthSession
from app.security import hasher, audit

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['create-user', 'reset-password', 'disable-user'])
    parser.add_argument('--email', required=True)
    parser.add_argument('--name')
    args = parser.parse_args()
    email = args.email.strip().lower()
    if '@' not in email or len(email) > 254:
        parser.error('Provide a valid email address')
    password = None
    if args.action != 'disable-user':
        password = getpass.getpass('Password (12+ characters): ')
        if len(password) < 12 or len(password) > 200 or password != getpass.getpass('Confirm password: '):
            parser.error('Passwords must match and contain 12–200 characters')
    with transaction() as db:
        user = db.scalar(select(User).where(User.email == email))
        if args.action == 'create-user':
            if user:
                parser.error('Account already exists')
            if not args.name or not args.name.strip() or len(args.name) > 160:
                parser.error('--name is required (1–160 characters)')
            user = User(email=email, password_hash=hasher.hash(password))
            db.add(user)
            db.flush()
            patient = Patient(user_id=user.id, full_name=args.name.strip(), email=email)
            db.add(patient)
            audit(db, patient, 'account_created', user.id)
        else:
            if not user:
                parser.error('Account does not exist')
            if password:
                user.password_hash = hasher.hash(password)
            else:
                user.enabled = False
            db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    print('Account updated successfully.')

if __name__ == '__main__':
    main()
