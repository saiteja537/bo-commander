from cryptography.fernet import Fernet
import os

# We generate a key based on the machine ID or a local file
KEY_FILE = "data/secret.key"

def get_key():
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    return open(KEY_FILE, "rb").read()

cipher = Fernet(get_key())

def encrypt_password(password):
    return cipher.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    try:
        return cipher.decrypt(encrypted_password.encode()).decode()
    except:
        return ""