from cryptography.fernet import Fernet
import keyring

class CredentialVault:
    def store_credential(self, service, username, password):
        """Store encrypted credentials"""
        keyring.set_password(service, username, password)
    
    def retrieve_credential(self, service, username):
        """Retrieve encrypted credentials"""
        return keyring.get_password(service, username)