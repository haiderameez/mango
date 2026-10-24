"""Set an initial administrator or change a user's role from the trusted host CLI."""
import argparse

from app.database.session import SessionLocal
from app.repositories.user_repository import UserRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("role", choices=("admin", "responder", "viewer"))
    args = parser.parse_args()
    with SessionLocal() as db:
        repository = UserRepository(db)
        user = repository.get_by_email(args.email)
        if user is None:
            parser.error(f"No user found with email {args.email!r}.")
        repository.update_role(user, args.role)
    print(f"Updated {args.email} to role {args.role}.")


if __name__ == "__main__":
    main()
