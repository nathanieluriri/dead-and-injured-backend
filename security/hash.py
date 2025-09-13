import bcrypt

def hash_password(password: str|bytes) -> bytes:
    if type(password)==str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed



def check_password(password: str, hashed: str) -> bool:
    """Compare plaintext password with bcrypt hash string."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))