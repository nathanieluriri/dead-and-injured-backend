import bcrypt


def hash_password(password: str) -> str:
    if not isinstance(password, str):
        raise TypeError("password must be a str")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    if not isinstance(password, str) or not isinstance(hashed, str):
        return False
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
