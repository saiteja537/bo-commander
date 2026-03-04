# core/cms_session.py

import requests
import xml.etree.ElementTree as ET


class CMSSession:
    def __init__(self, host, port, username, password):
        self.cms_host = host
        self.cms_port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{host}:{port}/biprws"
        self.session_token = None

    # ---------------------------------------------------------
    # Basic connectivity check
    # ---------------------------------------------------------
    def ping(self):
        r = requests.get(self.base_url, timeout=8)
        if r.status_code not in (200, 401, 403):
            raise RuntimeError(f"Unexpected HTTP {r.status_code}")
        return True

    # ---------------------------------------------------------
    # Login (Enterprise)
    # ---------------------------------------------------------
    def logon(self):
        url = f"{self.base_url}/logon/long"
        body = f"""
        <attrs xmlns="http://www.sap.com/rws/bip">
            <attr name="userName" type="string">{self.username}</attr>
            <attr name="password" type="string">{self.password}</attr>
            <attr name="auth" type="string">secEnterprise</attr>
        </attrs>
        """
        r = requests.post(url, data=body,
                          headers={"Content-Type": "application/xml"},
                          timeout=10)

        if r.status_code != 200:
            raise RuntimeError("CMS login failed")

        root = ET.fromstring(r.text)
        ns = {"b": "http://www.sap.com/rws/bip"}
        tok = root.find(".//b:attr[@name='logonToken']", ns)
        if tok is None:
            raise RuntimeError("Logon token not returned")

        self.session_token = tok.text
        return self.session_token

    # ---------------------------------------------------------
    # Query
    # ---------------------------------------------------------
    def query(self, sql):
        if not self.session_token:
            self.logon()

        url = f"{self.base_url}/infostore"
        params = {"query": sql}

        r = requests.get(
            url,
            params=params,
            headers={"X-SAP-LogonToken": self.session_token},
            timeout=15,
        )

        if r.status_code != 200:
            raise RuntimeError(f"Query failed: HTTP {r.status_code}")

        # You may parse XML properly later
        return []

    # ---------------------------------------------------------
    # Trusted Auth token
    # ---------------------------------------------------------
    def generate_trusted_token(self, user, secret):
        url = f"{self.base_url}/logon/long"
        body = f"""
        <attrs xmlns="http://www.sap.com/rws/bip">
            <attr name="userName" type="string">{user}</attr>
            <attr name="password" type="string">{secret}</attr>
            <attr name="auth" type="string">secTrustedSitePrincipal</attr>
        </attrs>
        """
        r = requests.post(url, data=body,
                          headers={"Content-Type": "application/xml"},
                          timeout=10)

        if r.status_code != 200:
            raise RuntimeError("Trusted auth failed")

        root = ET.fromstring(r.text)
        ns = {"b": "http://www.sap.com/rws/bip"}
        tok = root.find(".//b:attr[@name='logonToken']", ns)

        if tok is None:
            raise RuntimeError("Trusted token not returned")

        return tok.text

    def validate_session(self, token):
        url = f"{self.base_url}/infostore"
        r = requests.get(url,
                         headers={"X-SAP-LogonToken": token},
                         timeout=10)
        if r.status_code != 200:
            raise RuntimeError("Session invalid")

    def logoff(self, token):
        url = f"{self.base_url}/logoff"
        requests.post(url,
                      headers={"X-SAP-LogonToken": token},
                      timeout=5)