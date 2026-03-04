import os
import json
from core.sapbo_connection import bo_session

class AdminServices:
    """
    The 'Hands' of the app. Performs real CMC actions.
    """
    # --- USER OPERATIONS ---
    @staticmethod
    def set_user_status(uid, enabled=True):
        """Enable or Disable a user account."""
        return bo_session.session.put(f"{bo_session.base_url}/v1/users/{uid}", 
                                     json={"enabled": enabled}).status_code == 200

    @staticmethod
    def create_user(username, password, fullname="", email=""):
        payload = {"name": username, "password": password, "fullName": fullname, "email": email}
        return bo_session.session.post(f"{bo_session.base_url}/v1/users", json=payload).status_code in [200, 201]

    # --- SESSION OPERATIONS ---
    @staticmethod
    def get_active_sessions():
        """Fetches currently logged-in users."""
        q = "SELECT SI_ID, SI_NAME, SI_AUTH_TYPE, SI_LAST_LOGON_TIME FROM CI_SYSTEMOBJECTS WHERE SI_KIND='Connection'"
        return bo_session.run_cms_query(q)

    @staticmethod
    def kill_session(session_id):
        """Forcefully disconnects a user session."""
        return bo_session.session.delete(f"{bo_session.base_url}/v1/sessions/{session_id}").status_code == 200

    # --- INSTANCE & JOB OPERATIONS ---
    @staticmethod
    def get_instance_manager_data(status="failed"):
        """status: 1 (Success), 3 (Failed), 0 (Running), 8 (Paused)"""
        status_map = {"failed": 3, "running": 0, "success": 1}
        code = status_map.get(status, 3)
        q = f"SELECT SI_ID, SI_NAME, SI_OWNER, SI_STARTTIME FROM CI_INFOOBJECTS WHERE SI_INSTANCE=1 AND SI_SCHEDULE_STATUS={code}"
        return bo_session.run_cms_query(q)

    @staticmethod
    def retry_instance(instance_id):
        """Triggers a re-run of a failed job."""
        return bo_session.session.post(f"{bo_session.base_url}/v1/instances/{instance_id}/retry").status_code == 200

    # --- RECYCLE BIN ---
    @staticmethod
    def get_recycle_bin():
        q = "SELECT SI_ID, SI_NAME, SI_KIND, SI_OWNER FROM CI_INFOOBJECTS WHERE SI_RECYCLED=1"
        return bo_session.run_cms_query(q)
    
    @staticmethod
    def restore_object(obj_id):
        return bo_session.session.post(f"{bo_session.base_url}/v1/recyclebin/{obj_id}/restore").status_code == 200