"""Run interactively: python -m backend.app.seed_super_admin --email you@example.com --name 'Your Name'"""
from __future__ import annotations
import argparse
import getpass
import sys
import uuid
from .config import Settings
from .db import make_engine,make_session_factory
from .models import User
from .security import hash_password,audit

def main():
    parser = argparse.ArgumentParser(description="Create first Auvorent CMS Super Admin. Never pass a password on the command line.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()
    if "@" not in email or "." not in email.rsplit("@",1)[-1]:
        parser.error("Provide a valid email")
    settings=Settings.from_env()
    engine=make_engine(settings.database_url)
    with make_session_factory(engine)() as db:
        existing=db.query(User).filter(User.role=="super_admin",User.is_active.is_(True)).count()
        if existing:
            print("Active Super Admin already exists. Add more users in the dashboard.",file=sys.stderr)
            return 1
        if db.query(User).filter(User.email==email).first():
            print("Account email already exists. Refusing to overwrite.",file=sys.stderr)
            return 1
        password = getpass.getpass("New Super Admin password (12–128 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match",file=sys.stderr)
            return 1
        try: password_hash=hash_password(password)
        except ValueError as exc:
            print(str(exc),file=sys.stderr)
            return 1
        user=User(id=str(uuid.uuid4()), email=email, full_name=args.name.strip(),password_hash=password_hash,
                  role="super_admin",is_active=True,must_change_password=False)
        db.add(user)
        audit(db,"user.initial_super_admin_created",actor=user.id,target_type="user",target_id=user.id)
        db.commit()
        print("Super Admin created. Open the CMS and sign in.")
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
