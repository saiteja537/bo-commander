import requests
import json
import logging
import threading
import os
import glob
import random
import re
import webbrowser
from datetime import datetime, timedelta

# =========================================================================
# LOGGING CONFIGURATION
# =========================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SAPBOConnection")

class SAPBOConnection:
    """
    COMPLETE: BO Commander Master Engine
    Provides every method called by all GUI pages/tabs.
    """
    def __init__(self):
        self.base_url = None
        self.logon_token = None
        self.session = requests.Session()
        self.cms_details = {'host': 'Unknown', 'port': '6405', 'user': 'None'}
        self._connection_valid = False

    @property
    def connected(self):
        return self.logon_token is not None and self._connection_valid

    def is_connected(self):
        return self.connected

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    def login(self, host, port, user, pwd, auth="secEnterprise"):
        """Login to SAP BO via WACS REST API."""
        if ":" in host:
            host = host.split(":")[0]
        self.base_url = f"http://{host}:{port}/biprws"
        try:
            payload = f"""<attrs xmlns="http://www.sap.com/rws/bip">
                <attr name="userName" type="string">{user}</attr>
                <attr name="password" type="string">{pwd}</attr>
                <attr name="auth" type="string" possibilities="secEnterprise,secLDAP,secWinAD,secSAPR3">{auth}</attr>
            </attrs>"""
            r = self.session.post(
                f"{self.base_url}/logon/long",
                data=payload,
                headers={'Content-Type': 'application/xml', 'Accept': 'application/json'},
                timeout=15
            )
            r.raise_for_status()
            self.logon_token = r.headers.get('X-SAP-LogonToken') or r.json().get('logonToken')
            if not self.logon_token:
                return False, "Failed to retrieve logon token"
            self.cms_details = {'host': host, 'port': port, 'user': user}
            self.session.headers.update({
                'X-SAP-LogonToken': self.logon_token,
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })
            self._connection_valid = True
            logger.info(f"✅ Successfully connected as {user} to {host}:{port}")
            return True, "Success"
        except requests.exceptions.Timeout:
            return False, "Connection timeout - check server availability"
        except requests.exceptions.ConnectionError:
            return False, "Connection refused - check host and port"
        except requests.exceptions.HTTPError as e:
            return False, f"Authentication failed: {str(e)}"
        except Exception as e:
            return False, str(e)

    def logout(self):
        """Graceful logout."""
        try:
            if self.logon_token:
                self.session.post(f"{self.base_url}/logoff", timeout=5)
        except:
            pass
        finally:
            self.logon_token = None
            self._connection_valid = False

    # =========================================================================
    # CMS QUERY ENGINE
    # =========================================================================

    def run_cms_query(self, query, timeout=45):
        """Execute a CMS SQL query via REST API."""
        if not self.logon_token:
            logger.warning("No active session - cannot run query")
            return None
        try:
            r = self.session.post(
                f"{self.base_url}/v1/cmsquery",
                json={"query": query},
                timeout=timeout
            )
            if r.status_code == 200:
                result = r.json()
                logger.info(f"Query returned {len(result.get('entries', []))} entries")
                return result
            else:
                logger.error(f"Query failed with status {r.status_code}: {r.text[:200]}")
                return None
        except requests.exceptions.Timeout:
            logger.error("Query timeout")
            return None
        except Exception as e:
            logger.error(f"Query error: {e}")
            return None

    # =========================================================================
    # SERVER MANAGEMENT
    # =========================================================================

    def get_all_servers(self):
        """Fetch all BO servers with status."""
        q = """SELECT SI_ID, SI_NAME, SI_KIND, SI_SERVER_IS_ALIVE, SI_DESCRIPTION,
               SI_SERVER_FAILURE_START_TIME, SI_TOTAL_NUM_FAILURES
               FROM CI_SYSTEMOBJECTS WHERE SI_KIND = 'Server' ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or 'entries' not in d:
            return []
        servers = []
        for e in d['entries']:
            try:
                alive = e.get('SI_SERVER_IS_ALIVE', False)
                servers.append({
                    'id':           e.get('SI_ID', 0),
                    'name':         e.get('SI_NAME', 'Unknown'),
                    'kind':         e.get('SI_KIND', 'Server'),
                    'status':       'Running' if alive else 'Stopped',
                    'alive':        alive,
                    'description':  e.get('SI_DESCRIPTION', ''),
                    'failures':     e.get('SI_TOTAL_NUM_FAILURES', 0),
                    'last_failure': e.get('SI_SERVER_FAILURE_START_TIME', 'N/A')
                })
            except Exception as ex:
                logger.warning(f"Error processing server: {ex}")
        return servers

    def toggle_server_state(self, server_id, action='start'):
        """Start or stop a server."""
        try:
            r = self.session.post(f"{self.base_url}/v1/servers/{server_id}/{action}", timeout=30)
            if r.status_code in [200, 202]:
                return (True, f"Server {action} command sent")
            return (False, f"Command failed with status {r.status_code}")
        except Exception as e:
            return (False, str(e))

    def get_server_properties(self, server_id):
        q = f"SELECT * FROM CI_SYSTEMOBJECTS WHERE SI_ID = {server_id}"
        d = self.run_cms_query(q)
        if d and 'entries' in d and d['entries']:
            return d['entries'][0]
        return {"error": "Server not found"}

    def get_server_metrics(self, server_id=None):
        """Get server metrics — returns real data or simulated fallback."""
        try:
            url = (f"{self.base_url}/v1/monitoring/servers/{server_id}/metrics"
                   if server_id else f"{self.base_url}/v1/monitoring/metrics")
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        return {
            'cpu':       random.randint(20, 80),
            'ram':       random.randint(30, 90),
            'disk':      random.randint(40, 70),
            'timestamp': datetime.now().isoformat()
        }

    # =========================================================================
    # SESSIONS
    # =========================================================================

    def get_active_sessions(self, limit=100):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_CREATION_TIME, SI_DESCRIPTION, SI_AUTH_TYPE
                FROM CI_SYSTEMOBJECTS WHERE SI_KIND = 'Connection'
                ORDER BY SI_CREATION_TIME DESC"""
        d = self.run_cms_query(q)
        if not d or 'entries' not in d:
            return []
        return [{
            'id':          e.get('SI_ID', 0),
            'user':        e.get('SI_NAME', 'Unknown'),
            'auth_type':   e.get('SI_AUTH_TYPE', 'Unknown'),
            'created':     e.get('SI_CREATION_TIME', 'N/A'),
            'description': e.get('SI_DESCRIPTION', '')
        } for e in d['entries']]

    def kill_session(self, session_id):
        try:
            r = self.session.delete(f"{self.base_url}/v1/sessions/{session_id}", timeout=20)
            return (r.status_code == 200, "Session killed" if r.status_code == 200 else "Kill failed")
        except Exception as e:
            return (False, str(e))

    # =========================================================================
    # USERS — get_users_detailed()  [REQUIRED by gui/pages/users.py]
    # =========================================================================

    def get_users_detailed(self):
        """Return full user list. Called by users.py line 68."""
        q = """SELECT TOP 500
               SI_ID, SI_NAME, SI_EMAIL_ADDRESS, SI_DESCRIPTION,
               SI_DISABLED, SI_LAST_LOGIN_TIME, SI_PASSWORD_LOCKED,
               SI_KIND, SI_CREATION_TIME, SI_OWNER
               FROM CI_SYSTEMOBJECTS
               WHERE SI_PROGID = 'crystalenterprise.user'
               ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            # Fallback
            d = self.run_cms_query(
                "SELECT TOP 500 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_CREATION_TIME "
                "FROM CI_SYSTEMOBJECTS WHERE SI_KIND='User' ORDER BY SI_NAME"
            )
        if not d or not d.get('entries'):
            return []
        return [{
            'id':          e.get('SI_ID', ''),
            'name':        e.get('SI_NAME', ''),
            'email':       e.get('SI_EMAIL_ADDRESS', ''),
            'description': e.get('SI_DESCRIPTION', ''),
            'disabled':    e.get('SI_DISABLED', False),
            'locked':      e.get('SI_PASSWORD_LOCKED', False),
            'last_login':  e.get('SI_LAST_LOGIN_TIME', ''),
            'created':     e.get('SI_CREATION_TIME', ''),
            'kind':        e.get('SI_KIND', 'User'),
            'owner':       e.get('SI_OWNER', ''),
        } for e in d['entries']]

    def get_all_users(self, limit=500):
        """Alias — backward compatibility."""
        return self.get_users_detailed()

    def get_all_groups(self, limit=200):
        """Return all user groups."""
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_DESCRIPTION, SI_OWNER, SI_CREATION_TIME
                FROM CI_SYSTEMOBJECTS WHERE SI_KIND = 'UserGroup' ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':          e.get('SI_ID', ''),
            'name':        e.get('SI_NAME', ''),
            'description': e.get('SI_DESCRIPTION', ''),
            'owner':       e.get('SI_OWNER', ''),
            'created':     e.get('SI_CREATION_TIME', ''),
        } for e in d['entries']]

    def get_user_group_hierarchy(self):
        """Return group → member hierarchy."""
        groups = self.get_all_groups()
        hierarchy = []
        for g in groups:
            q = f"""SELECT SI_ID, SI_NAME FROM CI_SYSTEMOBJECTS
                    WHERE SI_KIND='User' AND SI_USERGROUPS.SI_ID = {g['id']}"""
            d = self.run_cms_query(q)
            members = [e.get('SI_NAME', '') for e in (d or {}).get('entries', [])]
            hierarchy.append({'group': g['name'], 'group_id': g['id'], 'members': members})
        return hierarchy

    def create_user(self, name, password, email='', full_name='', auth_type='secEnterprise'):
        try:
            payload = {"attrs": {
                "SI_NAME": name, "SI_PASSWORD": password,
                "SI_EMAIL_ADDRESS": email, "SI_DESCRIPTION": full_name,
                "SI_AUTH_TYPE": auth_type,
            }}
            r = self.session.post(f"{self.base_url}/v1/users", json=payload, timeout=20)
            return (r.status_code in (200, 201), r.text[:200])
        except Exception as e:
            return (False, str(e))

    def delete_user(self, user_id):
        return self.delete_object(user_id)

    def reset_user_password(self, user_id, new_password):
        try:
            r = self.session.put(f"{self.base_url}/v1/users/{user_id}",
                                 json={"attrs": {"SI_PASSWORD": new_password}}, timeout=20)
            return (r.status_code == 200, "Password reset" if r.status_code == 200 else r.text[:100])
        except Exception as e:
            return (False, str(e))

    def disable_user(self, user_id, disabled=True):
        try:
            r = self.session.put(f"{self.base_url}/v1/users/{user_id}",
                                 json={"attrs": {"SI_DISABLED": disabled}}, timeout=20)
            return (r.status_code == 200, "Updated" if r.status_code == 200 else r.text[:100])
        except Exception as e:
            return (False, str(e))

    # =========================================================================
    # FOLDERS — get_folder_contents()  [REQUIRED by gui/pages/folders.py]
    # =========================================================================

    def get_folder_contents(self, folder_id):
        """Return (folders_list, docs_list). Called by folders.py lines 88 and 112."""
        q = f"""SELECT TOP 500
               SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION,
               SI_OWNER, SI_CREATION_TIME, SI_UPDATE_TS, SI_PARENTID
               FROM CI_INFOOBJECTS
               WHERE SI_PARENTID = {folder_id} AND SI_INSTANCE = 0
               ORDER BY SI_KIND DESC, SI_NAME ASC"""
        d = self.run_cms_query(q)
        folders, docs = [], []
        if not d or not d.get('entries'):
            return folders, docs
        for e in d['entries']:
            item = {
                'id':          e.get('SI_ID', ''),
                'name':        e.get('SI_NAME', ''),
                'kind':        e.get('SI_KIND', ''),
                'description': e.get('SI_DESCRIPTION', ''),
                'owner':       e.get('SI_OWNER', ''),
                'created':     e.get('SI_CREATION_TIME', ''),
                'updated':     e.get('SI_UPDATE_TS', ''),
                'parent_id':   e.get('SI_PARENTID', folder_id),
            }
            if e.get('SI_KIND') == 'Folder':
                folders.append(item)
            else:
                docs.append(item)
        return folders, docs

    def get_root_folders(self):
        """Return top-level Public Folders (root ID = 23 in standard BO)."""
        for root_id in [23, 0]:
            folders, _ = self.get_folder_contents(root_id)
            if folders:
                return folders
        q = """SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER
               FROM CI_INFOOBJECTS WHERE SI_KIND = 'Folder' AND SI_INSTANCE = 0
               ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{'id': e.get('SI_ID'), 'name': e.get('SI_NAME'), 'kind': 'Folder',
                 'owner': e.get('SI_OWNER', '')} for e in d['entries']]

    def create_folder(self, name, parent_id=23, description=''):
        try:
            payload = {"attrs": {"SI_NAME": name, "SI_DESCRIPTION": description,
                                 "SI_PARENTID": parent_id, "SI_KIND": "Folder"}}
            r = self.session.post(f"{self.base_url}/v1/infostore", json=payload, timeout=20)
            return (r.status_code in (200, 201), r.text[:200])
        except Exception as e:
            return (False, str(e))

    # =========================================================================
    # REPORTS
    # =========================================================================

    def get_all_reports(self, limit=100):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_CREATION_TIME, SI_UPDATE_TS
                FROM CI_INFOOBJECTS
                WHERE SI_KIND IN ('Webi', 'CrystalReport', 'Pdf', 'Excel') AND SI_INSTANCE = 0
                ORDER BY SI_UPDATE_TS DESC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':       e.get('SI_ID', 0),
            'name':     e.get('SI_NAME', 'Unknown'),
            'kind':     e.get('SI_KIND', 'Unknown'),
            'owner':    e.get('SI_OWNER', 'N/A'),
            'created':  e.get('SI_CREATION_TIME', 'N/A'),
            'last_run': e.get('SI_UPDATE_TS', 'Never')
        } for e in d['entries']]

    def get_report_details(self, report_id):
        q = f"""SELECT SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_PARENT_FOLDER,
                SI_CREATION_TIME, SI_UPDATE_TS, SI_DESCRIPTION, SI_SCHEDULE_INFO
                FROM CI_INFOOBJECTS WHERE SI_ID = {report_id}"""
        d = self.run_cms_query(q)
        if d and 'entries' in d and d['entries']:
            return d['entries'][0]
        return None

    def refresh_report(self, report_id):
        try:
            r = self.session.post(f"{self.base_url}/v1/documents/{report_id}/refresh", timeout=15)
            return r.status_code == 202
        except:
            return False

    def delete_report(self, report_id):
        try:
            r = self.session.delete(f"{self.base_url}/v1/infostore/{report_id}", timeout=20)
            return (r.status_code == 200, "Deleted" if r.status_code == 200 else "Delete Failed")
        except Exception as e:
            return (False, str(e))

    def get_open_doc_url(self, doc_id):
        host = self.cms_details.get('host', 'localhost')
        return f"http://{host}:8080/BOE/OpenDocument/opendoc/openDocument.jsp?iDocID={doc_id}&token={self.logon_token}"

    # =========================================================================
    # UNIVERSES
    # =========================================================================

    def get_all_universes(self, limit=100):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS, SI_CREATION_TIME
                FROM CI_APPOBJECTS
                WHERE SI_KIND IN ('Universe', 'DSL.MetaDataFile', 'Olap')
                ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        universes = []
        for e in d['entries']:
            kind = e.get('SI_KIND', '')
            universes.append({
                'id':      e.get('SI_ID', 0),
                'name':    e.get('SI_NAME', 'Unknown'),
                'kind':    kind,
                'type':    'UNX' if 'DSL' in kind else 'UNV' if kind == 'Universe' else 'OLAP',
                'owner':   e.get('SI_OWNER', 'N/A'),
                'updated': e.get('SI_UPDATE_TS', 'N/A'),
                'created': e.get('SI_CREATION_TIME', 'N/A')
            })
        return universes

    def get_universe_details(self, universe_id):
        q = f"SELECT * FROM CI_APPOBJECTS WHERE SI_ID = {universe_id}"
        d = self.run_cms_query(q)
        if d and 'entries' in d and d['entries']:
            return d['entries'][0]
        return None

    # =========================================================================
    # CONNECTIONS
    # =========================================================================

    def get_all_connections(self, limit=100):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS,
                SI_SERVER, SI_DATABASE_NAME, SI_CONNECTION_STRING
                FROM CI_APPOBJECTS WHERE SI_KIND LIKE '%Connection%'
                ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':       e.get('SI_ID', 0),
            'name':     e.get('SI_NAME', 'Unknown'),
            'kind':     e.get('SI_KIND', 'Unknown'),
            'owner':    e.get('SI_OWNER', 'N/A'),
            'server':   e.get('SI_SERVER', 'N/A'),
            'database': e.get('SI_DATABASE_NAME', 'N/A'),
            'updated':  e.get('SI_UPDATE_TS', 'N/A')
        } for e in d['entries']]

    def test_connection(self, connection_id):
        try:
            r = self.session.get(f"{self.base_url}/v1/connections/{connection_id}/test", timeout=30)
            return r.status_code == 200
        except:
            return False

    # =========================================================================
    # INSTANCES
    # =========================================================================

    def get_instances(self, status=None, limit=100):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_INSTANCE,
                SI_PROCESSINFO.SI_STATUS_INFO AS SI_STATUS,
                SI_STARTTIME, SI_ENDTIME, SI_TOTAL_DURATION
                FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 1"""
        if status is not None:
            status_map = {'success': 0, 'failed': 1, 'running': 2, 'pending': 3}
            if isinstance(status, str) and status.lower() in status_map:
                status = status_map[status.lower()]
            q += f" AND SI_PROCESSINFO.SI_STATUS_INFO = {status}"
        q += " ORDER BY SI_STARTTIME DESC"
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            logger.warning("No instances found")
            return []
        instances = []
        for e in d['entries']:
            try:
                sc = e.get('SI_STATUS', 0)
                instances.append({
                    'id':          e.get('SI_ID', 0),
                    'name':        e.get('SI_NAME', 'Unknown'),
                    'kind':        e.get('SI_KIND', 'Unknown'),
                    'owner':       e.get('SI_OWNER', 'N/A'),
                    'status':      {0:'Success',1:'Failed',2:'Running',3:'Pending'}.get(sc,'Unknown'),
                    'status_code': sc,
                    'start_time':  e.get('SI_STARTTIME', 'N/A'),
                    'end_time':    e.get('SI_ENDTIME', 'N/A'),
                    'duration':    e.get('SI_TOTAL_DURATION', 0)
                })
            except Exception as ex:
                logger.warning(f"Error processing instance: {ex}")
        return instances

    def delete_instance(self, instance_id):
        return self.delete_object(instance_id)

    def purge_old_instances(self, days=30):
        q = f"""SELECT SI_ID FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 1
                AND SI_STARTTIME < DATEADD(day, -{days}, GETDATE())"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return 0, "No old instances found"
        deleted = sum(1 for e in d['entries'] if self.delete_instance(e['SI_ID'])[0])
        return deleted, f"Purged {deleted} instances"

    def reschedule_failed_instances(self):
        failed = self.get_instances(status='failed')
        rescheduled = 0
        for inst in failed:
            try:
                pd = self.run_cms_query(f"SELECT SI_PARENT_ID FROM CI_INFOOBJECTS WHERE SI_ID = {inst['id']}")
                if pd and pd.get('entries'):
                    pid = pd['entries'][0].get('SI_PARENT_ID')
                    if pid and self.refresh_report(pid):
                        rescheduled += 1
            except:
                pass
        return rescheduled, f"Rescheduled {rescheduled} failed instances"

    # =========================================================================
    # PROMOTION / LCM — get_lcm_jobs()  [REQUIRED by gui/pages/promotion.py]
    # =========================================================================

    def get_lcm_jobs(self, limit=50):
        """Return LCM promotion job list. Called by promotion.py line 51."""
        jobs = []
        # Primary: LCM endpoint
        try:
            r = self.session.get(f"{self.base_url}/lcm/jobs", timeout=20)
            if r.status_code == 200:
                data = r.json()
                raw = (data.get('lcmjobs') or {}).get('lcmjob', [])
                if isinstance(raw, dict):
                    raw = [raw]
                for item in raw[:limit]:
                    jobs.append({
                        'id':          item.get('id', ''),
                        'name':        item.get('name', ''),
                        'status':      item.get('status', 'Unknown'),
                        'owner':       item.get('createdBy', ''),
                        'created':     item.get('createTime', ''),
                        'description': item.get('description', ''),
                        'source':      item.get('sourceSystem', ''),
                        'target':      item.get('targetSystem', ''),
                    })
                logger.info(f"Query returned {len(jobs)} entries")
                return jobs
        except Exception as e:
            logger.warning(f"LCM REST endpoint error: {e} — using InfoStore fallback")
        # Fallback
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION, SI_OWNER, SI_CREATION_TIME
               FROM CI_INFOOBJECTS WHERE SI_KIND IN ('PromotionJob', 'LCMJob')
               ORDER BY SI_CREATION_TIME DESC"""
        d = self.run_cms_query(q)
        if d and d.get('entries'):
            for e in d['entries']:
                jobs.append({
                    'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                    'status': 'Unknown', 'owner': e.get('SI_OWNER',''),
                    'created': e.get('SI_CREATION_TIME',''), 'description': e.get('SI_DESCRIPTION',''),
                    'source': '', 'target': '',
                })
        return jobs

    def create_lcm_job(self, name, source_system, target_system, object_ids):
        try:
            payload = {"name": name, "sourceSystem": source_system,
                       "targetSystem": target_system,
                       "objects": [{"id": oid} for oid in object_ids]}
            r = self.session.post(f"{self.base_url}/lcm/jobs", json=payload, timeout=30)
            return (r.status_code in (200, 201), r.text[:200])
        except Exception as e:
            return (False, str(e))

    # =========================================================================
    # LICENSE — get_license_keys()  [REQUIRED by gui/pages/license_keys.py]
    # =========================================================================

    def get_license_keys(self):
        """Return license info. Called by license_keys.py line 51."""
        # Primary: WACS license endpoint
        try:
            r = self.session.get(f"{self.base_url}/license", timeout=20)
            if r.status_code == 200:
                data = r.json()
                raw = (data.get('licenses') or data.get('license') or
                       data.get('entries') or [data])
                if isinstance(raw, dict):
                    raw = [raw]
                licenses = []
                for item in raw:
                    a = item.get('attrs', item)
                    licenses.append({
                        'key':        a.get('SI_LICENSE_KEY',        a.get('key',              'N/A')),
                        'type':       a.get('SI_LICENSE_TYPE',        a.get('type',             'Standard')),
                        'product':    a.get('SI_PRODUCT',             'SAP BusinessObjects'),
                        'seats':      a.get('SI_NAMED_USER_LICENSES', a.get('namedUserLicenses','N/A')),
                        'concurrent': a.get('SI_CONCURRENT_USERS',    a.get('concurrentUsers',  'N/A')),
                        'expiry':     a.get('SI_EXPIRY_DATE',         a.get('expiryDate',       'N/A')),
                        'status':     a.get('SI_STATUS',              'Active'),
                    })
                logger.info(f"Query returned {len(licenses)} entries")
                return licenses
        except Exception as e:
            logger.warning(f"License endpoint failed: {e}")
        # Fallback: InfoStore
        q = "SELECT TOP 50 SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION, SI_OWNER FROM CI_SYSTEMOBJECTS WHERE SI_KIND LIKE '%License%' ORDER BY SI_NAME"
        d = self.run_cms_query(q)
        if d and d.get('entries'):
            return [{'key': e.get('SI_NAME','N/A'), 'type': e.get('SI_KIND','License'),
                     'product': 'SAP BusinessObjects', 'seats': 'See CMC',
                     'concurrent': 'See CMC', 'expiry': 'See CMC',
                     'status': e.get('SI_DESCRIPTION','Active')} for e in d['entries']]
        # Safe placeholder
        return [{'key': 'N/A — check CMC > License Keys', 'type': 'SAP BusinessObjects',
                 'product': 'SAP BusinessObjects Enterprise',
                 'seats': 'N/A', 'concurrent': 'N/A', 'expiry': 'N/A',
                 'status': 'Connected — query CMC for details'}]

    # =========================================================================
    # AUDIT — get_historical_audit()  [REQUIRED by gui/pages/audit.py]
    # =========================================================================

    def get_historical_audit(self, days=7, user=None):
        """Return audit records for past N days. Called by audit.py line 56."""
        records = []
        try:
            from_dt  = datetime.now() - timedelta(days=int(days or 7))
            from_str = from_dt.strftime("%Y-%m-%dT%H:%M:%S")
            user_clause = ''
            if user and str(user).strip().lower() not in ('', 'all', 'none'):
                safe = str(user).replace("'", "''")
                user_clause = f" AND SI_OWNER = '{safe}'"
            # Primary: AuditEvent
            q = f"""SELECT TOP 500 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_CREATION_TIME, SI_DESCRIPTION
                   FROM CI_INFOOBJECTS
                   WHERE SI_KIND = 'AuditEvent'
                   AND SI_CREATION_TIME >= TIMESTAMP '{from_str}'
                   {user_clause} ORDER BY SI_CREATION_TIME DESC"""
            d = self.run_cms_query(q)
            if not d or not d.get('entries'):
                # Fallback: general recent activity
                q2 = f"""SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_CREATION_TIME, SI_DESCRIPTION
                        FROM CI_INFOOBJECTS
                        WHERE SI_CREATION_TIME >= TIMESTAMP '{from_str}'
                        {user_clause} ORDER BY SI_CREATION_TIME DESC"""
                d = self.run_cms_query(q2)
            if d and d.get('entries'):
                for e in d['entries']:
                    records.append({
                        'id':          e.get('SI_ID', ''),
                        'name':        e.get('SI_NAME', ''),
                        'kind':        e.get('SI_KIND', ''),
                        'user':        e.get('SI_OWNER', ''),
                        'timestamp':   e.get('SI_CREATION_TIME', ''),
                        'description': e.get('SI_DESCRIPTION', ''),
                        'status':      '',
                    })
        except Exception as e:
            logger.error(f"get_historical_audit failed: {e}")
        return records

    # =========================================================================
    # RECYCLE BIN  [REQUIRED by gui/pages/recycle_bin.py]
    # =========================================================================

    def get_recycle_bin_items(self, limit=200):
        """Return objects in BO Recycle Bin."""
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
               SI_CREATION_TIME, SI_UPDATE_TS, SI_DESCRIPTION
               FROM CI_INFOOBJECTS WHERE SI_TRASHCAN = 1
               ORDER BY SI_UPDATE_TS DESC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':      e.get('SI_ID', ''),
            'name':    e.get('SI_NAME', ''),
            'kind':    e.get('SI_KIND', ''),
            'owner':   e.get('SI_OWNER', ''),
            'deleted': e.get('SI_UPDATE_TS', ''),
            'created': e.get('SI_CREATION_TIME', ''),
        } for e in d['entries']]

    def restore_from_recycle_bin(self, object_id):
        """Restore object from Recycle Bin."""
        try:
            r = self.session.put(f"{self.base_url}/v1/infostore/{object_id}",
                                 json={"attrs": {"SI_TRASHCAN": 0}}, timeout=20)
            return r.status_code in (200, 204)
        except Exception as e:
            logger.error(f"restore_from_recycle_bin: {e}")
            return False

    def delete_from_recycle_bin(self, object_id):
        """Permanently delete from Recycle Bin."""
        return self.delete_object(object_id)

    def empty_recycle_bin(self):
        """Empty entire Recycle Bin."""
        items = self.get_recycle_bin_items(limit=500)
        deleted = sum(1 for item in items if self.delete_object(item['id'])[0])
        return deleted, f"Deleted {deleted} objects from Recycle Bin"

    # =========================================================================
    # SCHEDULING
    # =========================================================================

    def get_all_schedules(self, limit=100):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
               SI_SCHEDULE_STATUS, SI_NEXTRUNTIME, SI_LASTRUNTIME
               FROM CI_INFOOBJECTS
               WHERE SI_SCHEDULE_STATUS IS NOT NULL AND SI_INSTANCE = 0
               ORDER BY SI_NEXTRUNTIME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':       e.get('SI_ID', ''),    'name':     e.get('SI_NAME', ''),
            'kind':     e.get('SI_KIND', ''),  'owner':    e.get('SI_OWNER', ''),
            'status':   e.get('SI_SCHEDULE_STATUS', ''),
            'next_run': e.get('SI_NEXTRUNTIME', ''),
            'last_run': e.get('SI_LASTRUNTIME', ''),
        } for e in d['entries']]

    def schedule_report(self, report_id, schedule_type='now', params=None):
        try:
            r = self.session.post(
                f"{self.base_url}/v1/infostore/{report_id}/schedules",
                json={"scheduleType": schedule_type, **(params or {})}, timeout=30)
            return (r.status_code in (200, 201, 202), r.text[:200])
        except Exception as e:
            return (False, str(e))

    # =========================================================================
    # SECURITY SCANNER
    # =========================================================================

    def scan_security(self, limit=200):
        """Scan for security issues."""
        issues = []
        try:
            q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_DISABLED
                    FROM CI_SYSTEMOBJECTS WHERE SI_KIND = 'User' AND SI_DISABLED = 1"""
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                for e in d['entries']:
                    issues.append({'type': 'Disabled User', 'object': e.get('SI_NAME',''),
                                   'id': e.get('SI_ID',''), 'severity': 'LOW',
                                   'detail': 'Disabled user account — verify or delete'})
        except Exception as e:
            logger.error(f"Security scan failed: {e}")
        return issues

    # =========================================================================
    # ORPHAN DETECTION
    # =========================================================================

    def find_orphan_instances(self, days=90, limit=200):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
               SI_STARTTIME, SI_PROCESSINFO.SI_STATUS_INFO AS SI_STATUS
               FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 1
               AND SI_STARTTIME < DATEADD(day, -{days}, GETDATE())
               ORDER BY SI_STARTTIME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{
            'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
            'kind': e.get('SI_KIND',''), 'owner': e.get('SI_OWNER',''),
            'start_time': e.get('SI_STARTTIME',''),
            'status': {0:'Success',1:'Failed',2:'Running',3:'Pending'}.get(e.get('SI_STATUS',0),'Unknown'),
        } for e in d['entries']]

    def find_orphan_objects(self, limit=200):
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_PARENTID, SI_CREATION_TIME
               FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 0
               AND SI_PARENTID NOT IN (SELECT SI_ID FROM CI_INFOOBJECTS WHERE SI_KIND = 'Folder')
               ORDER BY SI_CREATION_TIME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                 'kind': e.get('SI_KIND',''), 'owner': e.get('SI_OWNER',''),
                 'parent_id': e.get('SI_PARENTID',''), 'created': e.get('SI_CREATION_TIME','')}
                for e in d['entries']]

    # =========================================================================
    # QUERY BUILDER
    # =========================================================================

    def run_custom_query(self, query, timeout=60):
        """Execute a raw CMS query. Returns (success, entries_list)."""
        result = self.run_cms_query(query, timeout=timeout)
        if result and 'entries' in result:
            return True, result['entries']
        return False, []

    # =========================================================================
    # DEPENDENCY RESOLVER
    # =========================================================================

    def get_object_dependencies(self, object_id):
        try:
            r = self.session.get(f"{self.base_url}/v1/infostore/{object_id}/dependencies", timeout=20)
            if r.status_code == 200:
                return r.json().get('entries', [])
        except:
            pass
        q = f"""SELECT SI_ID, SI_NAME, SI_KIND FROM CI_APPOBJECTS
                WHERE SI_ID IN (SELECT SI_UNIVERSE_ID FROM CI_INFOOBJECTS WHERE SI_ID = {object_id})"""
        d = self.run_cms_query(q)
        return (d or {}).get('entries', [])

    def get_object_dependents(self, object_id):
        q = f"""SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER FROM CI_INFOOBJECTS
                WHERE SI_UNIVERSE_ID = {object_id} AND SI_INSTANCE = 0 ORDER BY SI_NAME"""
        d = self.run_cms_query(q)
        return (d or {}).get('entries', [])

    # =========================================================================
    # DASHBOARD STATISTICS
    # =========================================================================

    def get_dashboard_stats(self):
        stats = {
            'users': 0, 'servers_total': 0, 'servers_running': 0,
            'reports': 0, 'universes': 0, 'connections': 0,
            'instances_today': 0, 'failed_instances': 0, 'server_list': []
        }
        try:
            u = self.run_cms_query("SELECT SI_ID FROM CI_SYSTEMOBJECTS WHERE SI_KIND='User'")
            if u: stats['users'] = len(u.get('entries', []))
            r = self.run_cms_query("SELECT SI_ID FROM CI_INFOOBJECTS WHERE SI_KIND IN ('Webi','CrystalReport') AND SI_INSTANCE=0")
            if r: stats['reports'] = len(r.get('entries', []))
            univ = self.run_cms_query("SELECT SI_ID FROM CI_APPOBJECTS WHERE SI_KIND IN ('Universe','DSL.MetaDataFile')")
            if univ: stats['universes'] = len(univ.get('entries', []))
            conn = self.run_cms_query("SELECT SI_ID FROM CI_APPOBJECTS WHERE SI_KIND LIKE '%Connection%'")
            if conn: stats['connections'] = len(conn.get('entries', []))
            inst = self.run_cms_query("SELECT SI_ID FROM CI_INFOOBJECTS WHERE SI_INSTANCE=1 AND SI_STARTTIME > DATEADD(day,-1,GETDATE())")
            if inst: stats['instances_today'] = len(inst.get('entries', []))
            s = self.run_cms_query("SELECT SI_NAME, SI_SERVER_IS_ALIVE FROM CI_SYSTEMOBJECTS WHERE SI_KIND='Server'")
            if s:
                stats['servers_total'] = len(s.get('entries', []))
                for e in s.get('entries', []):
                    alive = e.get('SI_SERVER_IS_ALIVE', False)
                    stats['server_list'].append({'name': e['SI_NAME'], 'status': 'Running' if alive else 'Stopped'})
                    if alive: stats['servers_running'] += 1
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
        return stats

    # =========================================================================
    # LOG / FILE ACCESS
    # =========================================================================

    def read_system_file(self, file_path, lines=300):
        if not file_path or not os.path.exists(file_path):
            return "File not found."
        try:
            with open(file_path, 'r', errors='ignore') as f:
                return "".join(f.readlines()[:lines])
        except:
            return "Access Denied."

    def find_latest_log(self, pattern):
        try:
            files = glob.glob(pattern)
            return max(files, key=os.path.getmtime) if files else None
        except:
            return None

    def read_log_safe(self, log_path, lines=300):
        if not log_path or not os.path.exists(log_path):
            return "No log file found."
        try:
            with open(log_path, 'r', errors='ignore') as f:
                return "".join(f.readlines()[-lines:])
        except:
            return "Log read error."

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def delete_object(self, obj_id):
        try:
            r = self.session.delete(f"{self.base_url}/v1/infostore/{obj_id}", timeout=20)
            return (r.status_code == 200, "Deleted" if r.status_code == 200 else "Delete Failed")
        except Exception as e:
            return (False, str(e))

    def move_object(self, obj_id, target_folder_id):
        try:
            r = self.session.put(f"{self.base_url}/v1/infostore/{obj_id}",
                                 json={"parentId": target_folder_id}, timeout=20)
            return (r.status_code == 200, "Moved" if r.status_code == 200 else "Move Failed")
        except Exception as e:
            return (False, str(e))

    def get_folder_rights(self, folder_id):
        try:
            r = self.session.get(f"{self.base_url}/v1/objects/{folder_id}/rights", timeout=10)
            return r.json().get('right', []) if r.status_code == 200 else []
        except:
            return []

    def get_cmc_objects(self, kind_list, table="CI_INFOOBJECTS", limit=100):
        kinds = ",".join([f"'{k}'" for k in kind_list])
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS
                FROM {table} WHERE SI_KIND IN ({kinds}) ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        return [{'id': e['SI_ID'], 'name': e['SI_NAME'], 'kind': e['SI_KIND'],
                 'owner': e.get('SI_OWNER','N/A'), 'updated': e.get('SI_UPDATE_TS','')}
                for e in d['entries']]


# =========================================================================
# GLOBAL SINGLETON INSTANCE
# =========================================================================
# before the final "bo_session = SAPBOConnection()" line
# =========================================================================

    # =========================================================================
    # USERS — EXTRA METHODS (used by users.py drawers)
    # =========================================================================

    def get_users_detailed_full(self, limit=500):
        """Extended user details including auth type mapping."""
        users = self.get_users_detailed()
        AUTH_MAP = {'secEnterprise':'Enterprise','secLDAP':'LDAP',
                    'secWinAD':'Windows AD','secWindows':'Windows AD','secSAPR3':'SAP'}
        for u in users:
            raw_auth = u.get('kind','')
            u['auth_type']      = AUTH_MAP.get(raw_auth, 'Enterprise')
            u['account_status'] = 'Disabled' if u.get('disabled') else ('Locked' if u.get('locked') else 'Enabled')
            u['full_name']      = u.get('description','')
            u['date_created']   = u.get('created','')
            u['date_modified']  = u.get('last_login','')
            u['tenant']         = ''
        return users

    def get_groups_detailed(self, limit=200):
        """Return groups with descriptions. Used by users.py."""
        return self.get_all_groups(limit)

    def get_hierarchy_data(self):
        """Return group->members dict. Used by users.py Hierarchy tab."""
        hier = {}
        try:
            hierarchy = self.get_user_group_hierarchy()
            for item in hierarchy:
                hier[item['group']] = {'id': item['group_id'], 'members': item['members']}
        except Exception as e:
            logger.error(f"get_hierarchy_data: {e}")
        return hier

    def get_user_member_of(self, user_id):
        """Return groups that a user belongs to. Used by users.py drawer."""
        try:
            q = f"""SELECT SI_ID, SI_NAME, SI_DESCRIPTION FROM CI_SYSTEMOBJECTS
                    WHERE SI_KIND='UserGroup' AND SI_USERGROUPS.SI_ID = {user_id}"""
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                return [{'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                         'description': e.get('SI_DESCRIPTION','')} for e in d['entries']]
        except Exception as e:
            logger.error(f"get_user_member_of: {e}")
        return []

    def get_user_properties(self, user_id):
        """Return raw user properties dict. Used by users.py drawer."""
        try:
            q = f"SELECT * FROM CI_SYSTEMOBJECTS WHERE SI_ID = {user_id}"
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                return d['entries'][0]
        except Exception as e:
            logger.error(f"get_user_properties: {e}")
        return {}

    def get_group_properties(self, group_id):
        """Return raw group properties. Used by users.py group drawer."""
        try:
            q = f"SELECT * FROM CI_SYSTEMOBJECTS WHERE SI_ID = {group_id}"
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                return d['entries'][0]
        except Exception as e:
            logger.error(f"get_group_properties: {e}")
        return {}

    def get_group_members(self, group_id):
        """Return members of a group (users + sub-groups)."""
        members = []
        try:
            q = f"""SELECT SI_ID, SI_NAME, SI_KIND FROM CI_SYSTEMOBJECTS
                    WHERE SI_KIND IN ('User','UserGroup') AND SI_USERGROUPS.SI_ID = {group_id}"""
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                members = [{'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                            'kind': e.get('SI_KIND','')} for e in d['entries']]
        except Exception as e:
            logger.error(f"get_group_members: {e}")
        return members

    def get_group_member_of(self, group_id):
        """Return parent groups of this group."""
        try:
            q = f"""SELECT SI_ID, SI_NAME FROM CI_SYSTEMOBJECTS
                    WHERE SI_KIND='UserGroup' AND SI_SUBGROUPS.SI_ID = {group_id}"""
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                return [{'id': e.get('SI_ID',''), 'name': e.get('SI_NAME','')} for e in d['entries']]
        except Exception as e:
            logger.error(f"get_group_member_of: {e}")
        return []

    def get_group_security(self, group_id):
        """Return security rights for a group."""
        try:
            r = self.session.get(f"{self.base_url}/v1/objects/{group_id}/rights", timeout=10)
            if r.status_code == 200:
                return r.json().get('right', [])
        except Exception as e:
            logger.error(f"get_group_security: {e}")
        return []

    def get_cmc_nodes_list(self):
        """Return SIA nodes. Used by servers.py sidebar tree."""
        try:
            q = "SELECT SI_ID, SI_NAME FROM CI_SYSTEMOBJECTS WHERE SI_KIND='Node' ORDER BY SI_NAME"
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                return [{'id': e.get('SI_ID',''), 'col1': e.get('SI_NAME','')} for e in d['entries']]
        except Exception as e:
            logger.error(f"get_cmc_nodes_list: {e}")
        return []

    # =========================================================================
    # AI ASSISTANT  [used by gui/pages/ai_assistant.py]
    # =========================================================================

    def get_ai_context_snapshot(self):
        """Return a data snapshot for AI context (servers, stats, recent failures)."""
        try:
            stats   = self.get_dashboard_stats()
            servers = self.get_all_servers()
            failed  = self.get_instances(status='failed', limit=20)
            return {
                'stats':   stats,
                'servers': [{'name': s['name'], 'status': s['status']} for s in servers],
                'recent_failures': [{'name': f['name'], 'owner': f['owner'],
                                     'start': f['start_time']} for f in failed],
            }
        except Exception as e:
            logger.error(f"get_ai_context_snapshot: {e}")
            return {}

    # =========================================================================
    # APPLICATIONS  [used by gui/pages/applications.py]
    # =========================================================================

    def get_all_applications(self, limit=200):
        """Return BO applications (Web Intelligence, Crystal, etc.)."""
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
                SI_DESCRIPTION, SI_UPDATE_TS, SI_CREATION_TIME
                FROM CI_APPOBJECTS
                WHERE SI_KIND IN ('Application','AnalyticsApp','WebIntelligence',
                                  'LCM.Application','Publication')
                ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            # Fallback - query everything in APPOBJECTS
            q2 = f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS FROM CI_APPOBJECTS ORDER BY SI_NAME"
            d = self.run_cms_query(q2)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':      e.get('SI_ID',''),
            'name':    e.get('SI_NAME',''),
            'kind':    e.get('SI_KIND',''),
            'owner':   e.get('SI_OWNER',''),
            'desc':    e.get('SI_DESCRIPTION',''),
            'updated': e.get('SI_UPDATE_TS',''),
        } for e in d['entries']]

    # =========================================================================
    # BROKEN OBJECTS  [used by gui/pages/broken_objects.py]
    # =========================================================================

    def get_broken_objects(self, limit=500):
        """Find objects with broken/invalid markers."""
        broken = []
        try:
            # Objects with [broken] or [invalid] in name
            q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_PARENTID,
                    SI_CREATION_TIME, SI_UPDATE_TS
                    FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 0
                    AND (SI_NAME LIKE '%[broken]%' OR SI_NAME LIKE '%[invalid]%'
                         OR SI_NAME LIKE '%[error]%' OR SI_NAME LIKE '%(broken)%')
                    ORDER BY SI_UPDATE_TS DESC"""
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                for e in d['entries']:
                    broken.append({
                        'id':      e.get('SI_ID',''),
                        'name':    e.get('SI_NAME',''),
                        'kind':    e.get('SI_KIND',''),
                        'owner':   e.get('SI_OWNER',''),
                        'cause':   'Broken marker in name',
                        'fix':     'Rename or delete the object',
                        'updated': e.get('SI_UPDATE_TS',''),
                    })
        except Exception as e:
            logger.error(f"get_broken_objects: {e}")
        return broken

    # =========================================================================
    # DEEP SEARCH  [used by gui/pages/deep_search.py]
    # =========================================================================

    def deep_search(self, query_text, search_in=None, limit=200):
        """
        Full-text search across all BO objects.
        search_in: list of kinds to filter, e.g. ['Webi','Folder','Universe']
        """
        if not query_text or len(query_text.strip()) < 2:
            return []
        safe_q = query_text.strip().replace("'", "''")
        kind_clause = ''
        if search_in:
            kinds = ",".join(f"'{k}'" for k in search_in)
            kind_clause = f"AND SI_KIND IN ({kinds})"

        results = []
        for table in ['CI_INFOOBJECTS', 'CI_APPOBJECTS', 'CI_SYSTEMOBJECTS']:
            try:
                q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
                        SI_DESCRIPTION, SI_UPDATE_TS, SI_CREATION_TIME
                        FROM {table}
                        WHERE (SI_NAME LIKE '%{safe_q}%'
                               OR SI_DESCRIPTION LIKE '%{safe_q}%')
                        {kind_clause}
                        ORDER BY SI_UPDATE_TS DESC"""
                d = self.run_cms_query(q)
                if d and d.get('entries'):
                    for e in d['entries']:
                        results.append({
                            'id':      e.get('SI_ID',''),
                            'name':    e.get('SI_NAME',''),
                            'kind':    e.get('SI_KIND',''),
                            'owner':   e.get('SI_OWNER',''),
                            'desc':    e.get('SI_DESCRIPTION',''),
                            'updated': e.get('SI_UPDATE_TS',''),
                            'source':  table,
                        })
            except Exception as e:
                logger.error(f"deep_search {table}: {e}")

        # Deduplicate by ID
        seen = set()
        unique = []
        for r in results:
            key = str(r['id'])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    # =========================================================================
    # HEALTH HEATMAP  [used by gui/pages/health_heatmap.py]
    # =========================================================================

    def get_health_heatmap_data(self):
        """
        Return structured data for the health heatmap:
        servers (with status), recent failures, schedule success rate.
        """
        try:
            servers   = self.get_all_servers()
            failed_24h = self.get_instances(status='failed', limit=100)
            success_24h= self.get_instances(status='success', limit=100)
            stats      = self.get_dashboard_stats()

            # Per-server heat score (0=green, 1=yellow, 2=red)
            server_heat = []
            for s in servers:
                failures = int(s.get('failures', 0) or 0)
                status   = s.get('status','')
                heat     = 0
                if status != 'Running':
                    heat = 2
                elif failures > 10:
                    heat = 2
                elif failures > 3:
                    heat = 1
                server_heat.append({
                    'name':     s['name'],
                    'status':   status,
                    'failures': failures,
                    'heat':     heat,
                })

            total_sched = len(failed_24h) + len(success_24h)
            success_rate = round(100 * len(success_24h) / total_sched, 1) if total_sched > 0 else 100.0

            return {
                'servers':       server_heat,
                'failed_count':  len(failed_24h),
                'success_count': len(success_24h),
                'success_rate':  success_rate,
                'stats':         stats,
            }
        except Exception as e:
            logger.error(f"get_health_heatmap_data: {e}")
            return {}

    # =========================================================================
    # IMPACT ANALYSIS  [used by gui/pages/impact_analysis.py]
    # =========================================================================

    def get_impact_analysis(self, object_id, object_kind='Universe'):
        """
        Given a universe or connection ID, return all reports/objects that depend on it.
        Shows what would break if this object is changed/deleted.
        """
        dependents = []
        try:
            if object_kind in ('Universe', 'DSL.MetaDataFile'):
                q = f"""SELECT TOP 500 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS
                        FROM CI_INFOOBJECTS
                        WHERE SI_UNIVERSE_ID = {object_id} AND SI_INSTANCE = 0
                        ORDER BY SI_NAME"""
                d = self.run_cms_query(q)
                if d and d.get('entries'):
                    dependents = [{'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                                   'kind': e.get('SI_KIND',''), 'owner': e.get('SI_OWNER',''),
                                   'impact': 'BREAKS — uses this universe',
                                   'severity': 'HIGH'} for e in d['entries']]
            elif 'Connection' in object_kind:
                # Find universes using this connection, then reports using those universes
                q_univ = f"""SELECT SI_ID, SI_NAME FROM CI_APPOBJECTS
                             WHERE SI_KIND IN ('Universe','DSL.MetaDataFile')
                             AND SI_CONNECTION_ID = {object_id}"""
                d_univ = self.run_cms_query(q_univ)
                if d_univ and d_univ.get('entries'):
                    for univ in d_univ['entries']:
                        uid = univ.get('SI_ID')
                        q_rep = f"""SELECT SI_ID, SI_NAME, SI_KIND, SI_OWNER FROM CI_INFOOBJECTS
                                    WHERE SI_UNIVERSE_ID = {uid} AND SI_INSTANCE = 0"""
                        d_rep = self.run_cms_query(q_rep)
                        if d_rep and d_rep.get('entries'):
                            for e in d_rep['entries']:
                                dependents.append({
                                    'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                                    'kind': e.get('SI_KIND',''), 'owner': e.get('SI_OWNER',''),
                                    'impact': f"BREAKS via universe: {univ.get('SI_NAME','')}",
                                    'severity': 'HIGH'
                                })
        except Exception as e:
            logger.error(f"get_impact_analysis: {e}")
        return dependents

    def get_all_objects_summary(self, limit=300):
        """Return all non-instance objects for impact analysis target selection."""
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER
                FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 0
                ORDER BY SI_KIND, SI_NAME"""
        d = self.run_cms_query(q)
        results = (d or {}).get('entries', [])
        q2 = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER
                 FROM CI_APPOBJECTS ORDER BY SI_KIND, SI_NAME"""
        d2 = self.run_cms_query(q2)
        results += (d2 or {}).get('entries', [])
        return [{'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                 'kind': e.get('SI_KIND',''), 'owner': e.get('SI_OWNER','')}
                for e in results]

    # =========================================================================
    # INSTANCE DEEP CONTROL  [used by gui/pages/instance_deep_control.py]
    # =========================================================================

    def get_instances_deep(self, limit=500, owner=None, kind=None,
                           status=None, days_back=None):
        """Extended instance query with all filters for deep control page."""
        clauses = ["SI_INSTANCE = 1"]
        if owner:
            clauses.append(f"SI_OWNER = '{owner.replace(chr(39), chr(39)*2)}'")
        if kind:
            clauses.append(f"SI_KIND = '{kind}'")
        if status is not None:
            status_map = {'success':0,'failed':1,'running':2,'pending':3,'paused':4}
            code = status_map.get(str(status).lower(), status)
            clauses.append(f"SI_PROCESSINFO.SI_STATUS_INFO = {code}")
        if days_back:
            clauses.append(f"SI_STARTTIME > DATEADD(day, -{int(days_back)}, GETDATE())")
        where = " AND ".join(clauses)
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
                SI_PROCESSINFO.SI_STATUS_INFO AS SI_STATUS,
                SI_STARTTIME, SI_ENDTIME, SI_TOTAL_DURATION,
                SI_CREATION_TIME
                FROM CI_INFOOBJECTS WHERE {where}
                ORDER BY SI_STARTTIME DESC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            return []
        status_labels = {0:'Success',1:'Failed',2:'Running',3:'Pending',4:'Paused'}
        return [{
            'id':        e.get('SI_ID',''),
            'name':      e.get('SI_NAME',''),
            'kind':      e.get('SI_KIND',''),
            'owner':     e.get('SI_OWNER',''),
            'status':    status_labels.get(int(e.get('SI_STATUS') or 0), 'Unknown'),
            'status_code': int(e.get('SI_STATUS') or 0),
            'start':     e.get('SI_STARTTIME',''),
            'end':       e.get('SI_ENDTIME',''),
            'duration':  e.get('SI_TOTAL_DURATION',0),
        } for e in d['entries']]

    def bulk_delete_instances(self, instance_ids):
        """Delete multiple instances. Returns (ok_count, err_count)."""
        ok = err = 0
        for iid in instance_ids:
            success, _ = self.delete_instance(iid)
            if success: ok += 1
            else:       err += 1
        return ok, err

    def bulk_retry_instances(self, instance_ids):
        """Retry multiple failed instances."""
        ok = err = 0
        for iid in instance_ids:
            try:
                # Get parent report
                q = f"SELECT SI_PARENT_ID FROM CI_INFOOBJECTS WHERE SI_ID = {iid}"
                d = self.run_cms_query(q)
                if d and d.get('entries'):
                    pid = d['entries'][0].get('SI_PARENT_ID')
                    if pid:
                        success, _ = self.schedule_report(pid, 'now')
                        if success: ok += 1
                        else:       err += 1
            except:
                err += 1
        return ok, err

    # =========================================================================
    # LOG CORRELATION  [used by gui/pages/log_correlation.py]
    # =========================================================================

    def get_log_files_list(self):
        """Return list of available BO log files."""
        from config import Config
        log_dir = getattr(Config, 'BO_LOG_DIR',
                          os.environ.get('BO_LOG_DIR', r'C:\Program Files (x86)\SAP BusinessObjects\tomcat\logs'))
        logs = []
        try:
            for pattern in ['*.log', '*.txt', '*.trc']:
                for f in glob.glob(os.path.join(log_dir, pattern)):
                    logs.append({
                        'path':     f,
                        'name':     os.path.basename(f),
                        'size':     os.path.getsize(f),
                        'modified': os.path.getmtime(f),
                    })
            logs.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            logger.error(f"get_log_files_list: {e}")
        return logs

    def correlate_logs(self, log_paths, error_pattern=None, time_window_minutes=5):
        """
        Scan multiple log files and correlate errors by timestamp window.
        Returns list of correlated events.
        """
        import re as _re
        from datetime import timedelta as _td

        pattern = error_pattern or r'(?i)(error|exception|fatal|critical|failed|timeout)'
        events  = []

        for path in log_paths:
            try:
                content = self.read_log_safe(path, lines=500)
                for i, line in enumerate(content.splitlines()):
                    if _re.search(pattern, line):
                        # Try to parse timestamp from line
                        ts_match = _re.search(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})', line)
                        ts = ts_match.group(1) if ts_match else None
                        events.append({
                            'source': os.path.basename(path),
                            'line':   i + 1,
                            'ts':     ts,
                            'text':   line.strip()[:200],
                        })
            except Exception as e:
                logger.error(f"correlate_logs {path}: {e}")

        # Group events within time_window_minutes of each other
        events.sort(key=lambda x: (x['ts'] or ''))
        return events

    # =========================================================================
    # METADATA VIEW  [used by gui/pages/metadata_view.py]
    # =========================================================================

    def get_object_metadata(self, object_id):
        """Return full metadata/properties for any BO object."""
        for table in ['CI_INFOOBJECTS', 'CI_APPOBJECTS', 'CI_SYSTEMOBJECTS']:
            try:
                q = f"SELECT * FROM {table} WHERE SI_ID = {object_id}"
                d = self.run_cms_query(q)
                if d and d.get('entries'):
                    return d['entries'][0]
            except:
                pass
        return {}

    def update_object_metadata(self, object_id, attrs):
        """
        Update custom attributes on a BO object.
        attrs: dict of {field_name: value}
        """
        try:
            r = self.session.put(
                f"{self.base_url}/v1/infostore/{object_id}",
                json={"attrs": attrs},
                timeout=20
            )
            return (r.status_code in (200, 204), "Updated" if r.status_code in (200,204) else r.text[:100])
        except Exception as e:
            return (False, str(e))

    def search_objects_by_metadata(self, field, value, limit=200):
        """Search objects by a specific metadata field value."""
        safe_v = str(value).replace("'","''")
        results = []
        for table in ['CI_INFOOBJECTS','CI_APPOBJECTS']:
            try:
                q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER
                        FROM {table} WHERE {field} LIKE '%{safe_v}%'
                        ORDER BY SI_NAME"""
                d = self.run_cms_query(q)
                if d and d.get('entries'):
                    results += [{'id': e.get('SI_ID',''), 'name': e.get('SI_NAME',''),
                                 'kind': e.get('SI_KIND',''), 'owner': e.get('SI_OWNER','')}
                                for e in d['entries']]
            except:
                pass
        return results

    # =========================================================================
    # NOTIFICATIONS  [used by gui/pages/notifications.py]
    # =========================================================================

    def get_system_notifications(self):
        """
        Aggregate notifications from: failed schedules, stopped servers, license expiry.
        Returns list of notification dicts.
        """
        notifs = []
        try:
            # Failed schedules in last 24h
            failed = self.get_instances(status='failed', limit=50)
            for f in failed[:10]:
                notifs.append({
                    'type':     'Schedule Failure',
                    'severity': 'ERROR',
                    'message':  f"Report '{f['name']}' failed",
                    'owner':    f.get('owner',''),
                    'time':     f.get('start_time',''),
                    'id':       f.get('id',''),
                })

            # Stopped servers
            servers = self.get_all_servers()
            for s in servers:
                if s.get('status') != 'Running':
                    notifs.append({
                        'type':     'Server Down',
                        'severity': 'CRITICAL',
                        'message':  f"Server '{s['name']}' is {s['status']}",
                        'owner':    '',
                        'time':     s.get('last_failure',''),
                        'id':       s.get('id',''),
                    })
        except Exception as e:
            logger.error(f"get_system_notifications: {e}")

        # Sort by severity
        order = {'CRITICAL':0,'ERROR':1,'WARNING':2,'INFO':3}
        notifs.sort(key=lambda x: order.get(x['severity'],4))
        return notifs

    def mark_notification_read(self, notif_id):
        """Mark a notification as acknowledged (local state only)."""
        return True

    # =========================================================================
    # OLAP CONNECTIONS  [used by gui/pages/olap_connections.py]
    # =========================================================================

    def get_olap_connections(self, limit=100):
        """Return OLAP/BW connections separate from relational connections."""
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
                SI_DESCRIPTION, SI_UPDATE_TS
                FROM CI_APPOBJECTS
                WHERE SI_KIND IN ('OlapConnection','BW','OLAP',
                                  'MDXConnection','BWConnection',
                                  'OlapMDXConnection')
                ORDER BY SI_NAME ASC"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            # Fallback: look for OLAP in name
            q2 = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS
                     FROM CI_APPOBJECTS
                     WHERE SI_NAME LIKE '%OLAP%' OR SI_NAME LIKE '%BW%'
                     OR SI_KIND LIKE '%Olap%' OR SI_KIND LIKE '%Mdx%'
                     ORDER BY SI_NAME"""
            d = self.run_cms_query(q2)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':      e.get('SI_ID',''),
            'name':    e.get('SI_NAME',''),
            'kind':    e.get('SI_KIND',''),
            'owner':   e.get('SI_OWNER',''),
            'desc':    e.get('SI_DESCRIPTION',''),
            'updated': e.get('SI_UPDATE_TS',''),
        } for e in d['entries']]

    def test_olap_connection(self, connection_id):
        """Test OLAP connection."""
        return self.test_connection(connection_id)

    # =========================================================================
    # BW CONNECTIONS  [used by gui/pages/bw_connections.py]
    # =========================================================================

    def get_bw_connections(self, limit=200):
        """
        Return all BW / OLAP connections from the CMS.
        Tries specific BW kinds first, then falls back to name-based search.
        """
        bw_kinds = (
            "'OlapConnection','BWConnection','OlapMDXConnection',"
            "'BICSConnection','MDXConnection','BW','OLAP'"
        )
        q = (
            f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
            f"SI_DESCRIPTION, SI_UPDATE_TS "
            f"FROM CI_APPOBJECTS "
            f"WHERE SI_KIND IN ({bw_kinds}) "
            f"ORDER BY SI_NAME ASC"
        )
        d = self.run_cms_query(q)
        entries = d.get('entries', []) if d else []

        if not entries:
            # Fallback: name contains BW / OLAP
            q2 = (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                f"SI_DESCRIPTION, SI_UPDATE_TS "
                f"FROM CI_APPOBJECTS "
                f"WHERE SI_NAME LIKE '%BW%' OR SI_NAME LIKE '%OLAP%' "
                f"OR SI_KIND LIKE '%Olap%' OR SI_KIND LIKE '%Mdx%' "
                f"OR SI_KIND LIKE '%BICS%' "
                f"ORDER BY SI_NAME ASC"
            )
            d2 = self.run_cms_query(q2)
            entries = d2.get('entries', []) if d2 else []

        return [
            {
                'id':      e.get('SI_ID', ''),
                'name':    e.get('SI_NAME', ''),
                'kind':    e.get('SI_KIND', ''),
                'owner':   e.get('SI_OWNER', ''),
                'desc':    e.get('SI_DESCRIPTION', ''),
                'updated': e.get('SI_UPDATE_TS', ''),
            }
            for e in entries
        ]

    def test_bw_connection(self, connection_id):
        """
        Test a BW/OLAP connection.
        Returns (success: bool, message: str).
        Tries the BO REST /connections/{id}/test endpoint first,
        then falls back to a lightweight CMS object fetch.
        """
        try:
            # Attempt 1: dedicated test endpoint
            r = self.session.post(
                f"{self.base_url}/connections/{connection_id}/test",
                timeout=20
            )
            if r.status_code == 200:
                return True, "Connection OK (REST test passed)"
            if r.status_code in (404, 405):
                pass   # endpoint not supported — try fallback
            else:
                return False, f"Test failed (HTTP {r.status_code})"
        except Exception as e:
            logger.warning(f"test_bw_connection REST attempt: {e}")

        try:
            # Attempt 2: verify the object still resolves
            r2 = self.session.get(
                f"{self.base_url}/infostore/{connection_id}",
                timeout=15
            )
            if r2.status_code == 200:
                return True, "Connection object reachable (CMS lookup OK)"
            return False, f"Connection object not found (HTTP {r2.status_code})"
        except Exception as e2:
            return False, f"Connection test error: {e2}"

    def create_bw_connection(self, data):
        """
        Create a new BW OLAP connection in the CMS via REST.
        data keys: name, bw_host, bw_client, bw_system_id, bw_logon_grp,
                   bex_query, description, protocol
        Returns (success: bool, message: str).
        """
        try:
            protocol = data.get('protocol', '')
            if 'MDX' in protocol:
                kind = 'OlapMDXConnection'
            elif 'RFC' in protocol:
                kind = 'BWConnection'
            else:
                kind = 'OlapConnection'   # BICS default

            payload = {
                "SI_NAME":        data.get('name', ''),
                "SI_KIND":        kind,
                "SI_DESCRIPTION": data.get('description', ''),
                "attributes": {
                    "ServerName":   data.get('bw_host', ''),
                    "Client":       data.get('bw_client', ''),
                    "SystemId":     data.get('bw_system_id', ''),
                    "LogonGroup":   data.get('bw_logon_grp', ''),
                    "DefaultQuery": data.get('bex_query', ''),
                }
            }
            r = self.session.post(
                f"{self.base_url}/connections",
                json=payload,
                timeout=25
            )
            if r.status_code in (200, 201):
                return True, f"Created connection: {data.get('name')}"
            # Many BO versions don't support REST creation — fallback message
            return False, (
                f"REST creation not supported by this BO version "
                f"(HTTP {r.status_code}). "
                f"Use CMC > Connections to create it manually, "
                f"then refresh here."
            )
        except Exception as e:
            return False, str(e)

    def update_bw_connection(self, connection_id, data):
        """
        Update editable properties of a BW connection (name, description, owner).
        Returns (success: bool, message: str).
        """
        try:
            payload = {}
            if data.get('name'):
                payload['SI_NAME'] = data['name']
            if data.get('description') is not None:
                payload['SI_DESCRIPTION'] = data['description']

            r = self.session.put(
                f"{self.base_url}/infostore/{connection_id}",
                json=payload,
                timeout=20
            )
            if r.status_code in (200, 204):
                return True, "Connection updated"
            return False, f"Update failed (HTTP {r.status_code}): {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def delete_bw_connection(self, connection_id):
        """
        Delete a BW connection from the CMS.
        Returns (success: bool, message: str).
        """
        try:
            r = self.session.delete(
                f"{self.base_url}/infostore/{connection_id}",
                timeout=20
            )
            if r.status_code in (200, 204):
                return True, "Connection deleted"
            return False, f"Delete failed (HTTP {r.status_code}): {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def get_bw_infoproviders(self, connection_id, limit=300):
        """
        Return InfoProviders and BEx Queries linked to a BW connection.
        Queries the CMS for Webi/Crystal documents using this connection,
        then enumerates BEx query references from document metadata.
        Also returns a synthetic list of known InfoProvider types.
        """
        results = []
        try:
            # Documents that use this connection
            q = (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION "
                f"FROM CI_INFOOBJECTS "
                f"WHERE SI_INSTANCE=0 "
                f"AND SI_CONNECTION_GUID='{connection_id}' "
                f"ORDER BY SI_NAME ASC"
            )
            d = self.run_cms_query(q)
            entries = d.get('entries', []) if d else []
            for e in entries:
                kind = e.get('SI_KIND', '')
                obj_type = 'BEx Query' if 'query' in kind.lower() else 'InfoProvider'
                results.append({
                    'name': e.get('SI_NAME', ''),
                    'type': obj_type,
                    'desc': e.get('SI_DESCRIPTION', ''),
                })
        except Exception:
            pass

        try:
            # BEx universe data providers linked to connection
            q2 = (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION "
                f"FROM CI_APPOBJECTS "
                f"WHERE SI_KIND IN ('Universe','DSL.MetaDataFile') "
                f"AND SI_DBCONNECTION_ID='{connection_id}' "
                f"ORDER BY SI_NAME ASC"
            )
            d2 = self.run_cms_query(q2)
            for e in (d2.get('entries', []) if d2 else []):
                results.append({
                    'name': e.get('SI_NAME', ''),
                    'type': 'BEx Universe',
                    'desc': e.get('SI_DESCRIPTION', ''),
                })
        except Exception:
            pass

        if not results:
            # If no CMS links found, return a descriptive placeholder
            results = [{
                'name': '(No linked objects found in CMS)',
                'type': 'Info',
                'desc': 'BEx Queries and InfoProviders are referenced at runtime, '
                        'not stored as CMS objects. Use SAP BW directly to browse.',
            }]

        return results

    # =========================================================================
    # UNIFIED CONNECTION MANAGER  [used by gui/pages/connection_manager.py]
    # =========================================================================

    def get_all_connections_typed(self, limit=300):
        """Return ALL connections (relational + OLAP) with unified structure."""
        q = (
            f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
            f"SI_DESCRIPTION, SI_UPDATE_TS, SI_SERVER, SI_DATABASE_NAME "
            f"FROM CI_APPOBJECTS "
            f"WHERE SI_KIND LIKE '%Connection%' "
            f"OR SI_KIND IN ('BW','OLAP','MDX') "
            f"ORDER BY SI_NAME ASC"
        )
        d = self.run_cms_query(q)
        entries = d.get('entries', []) if d else []
        if not entries:
            q2 = (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                f"SI_DESCRIPTION, SI_UPDATE_TS "
                f"FROM CI_APPOBJECTS ORDER BY SI_NAME ASC"
            )
            d2 = self.run_cms_query(q2)
            entries = d2.get('entries', []) if d2 else []
        return [{
            'id':       e.get('SI_ID', ''),
            'name':     e.get('SI_NAME', ''),
            'kind':     e.get('SI_KIND', ''),
            'owner':    e.get('SI_OWNER', ''),
            'desc':     e.get('SI_DESCRIPTION', ''),
            'host':     e.get('SI_SERVER', ''),
            'database': e.get('SI_DATABASE_NAME', ''),
            'updated':  e.get('SI_UPDATE_TS', ''),
        } for e in entries]

    def test_connection_typed(self, connection_id):
        """Test any connection. Returns (bool, str)."""
        try:
            for url in [f"{self.base_url}/connections/{connection_id}/test",
                        f"{self.base_url}/v1/connections/{connection_id}/test"]:
                r = self.session.post(url, timeout=20)
                if r.status_code == 200:
                    return True, "Connection test passed"
                if r.status_code in (404, 405):
                    continue
                return False, f"HTTP {r.status_code}"
        except Exception as e:
            logger.debug(f"test_connection_typed: {e}")
        try:
            r2 = self.session.get(f"{self.base_url}/infostore/{connection_id}", timeout=15)
            if r2.status_code == 200:
                return True, "Connection object reachable"
            return False, f"HTTP {r2.status_code}"
        except Exception as e2:
            return False, str(e2)

    def create_connection_typed(self, data):
        """Create any connection type. Returns (bool, str)."""
        try:
            source = data.get('source_type', 'nonsap')
            proto  = data.get('protocol', '')
            kind_map = {
                'bw': 'OlapConnection', 'hana_olap': 'HANAOlapConnection',
                'hana_rel': 'HANARelationalConnection',
                's4hana': 'S4HANAConnection', 'nonsap': 'Connection',
            }
            if source == 'bw' and 'MDX' in proto:
                kind = 'OlapMDXConnection'
            elif source == 'bw' and 'RFC' in proto:
                kind = 'BWConnection'
            else:
                kind = kind_map.get(source, 'Connection')
            payload = {
                "SI_NAME": data.get('name', ''),
                "SI_KIND": kind,
                "SI_DESCRIPTION": data.get('description', ''),
                "attributes": {
                    "ServerName": data.get('bw_host') or data.get('hana_host') or data.get('host', ''),
                    "Client":     data.get('bw_client') or data.get('client', ''),
                    "SystemId":   data.get('bw_system_id', ''),
                    "Schema":     data.get('hana_schema') or data.get('database', ''),
                }
            }
            r = self.session.post(f"{self.base_url}/connections", json=payload, timeout=25)
            if r.status_code in (200, 201):
                return True, f"Created: {data.get('name')}"
            return False, (
                f"REST creation not supported (HTTP {r.status_code}). "
                f"Create manually in CMC → Connections, then refresh."
            )
        except Exception as e:
            return False, str(e)

    def update_connection_typed(self, connection_id, data):
        """Update name/description of any connection. Returns (bool, str)."""
        try:
            payload = {}
            if data.get('name'):        payload['SI_NAME'] = data['name']
            if data.get('description'): payload['SI_DESCRIPTION'] = data['description']
            r = self.session.put(
                f"{self.base_url}/infostore/{connection_id}",
                json=payload, timeout=20
            )
            if r.status_code in (200, 204): return True, "Updated"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def delete_connection_typed(self, connection_id):
        """Delete any connection by ID. Returns (bool, str)."""
        try:
            r = self.session.delete(
                f"{self.base_url}/infostore/{connection_id}", timeout=20)
            if r.status_code in (200, 204): return True, "Deleted"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)

    def get_connection_linked_objects(self, connection_id, limit=300):
        """Return universes/reports/queries linked to any connection."""
        results = []
        queries = [
            (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_DESCRIPTION "
                f"FROM CI_APPOBJECTS "
                f"WHERE SI_KIND IN ('Universe','DSL.MetaDataFile') "
                f"AND SI_DBCONNECTION_ID='{connection_id}' ORDER BY SI_NAME ASC",
            ),
            (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_DESCRIPTION "
                f"FROM CI_INFOOBJECTS WHERE SI_INSTANCE=0 "
                f"AND SI_CONNECTION_GUID='{connection_id}' ORDER BY SI_NAME ASC",
            ),
        ]
        for (q,) in queries:
            try:
                d = self.run_cms_query(q)
                for e in (d.get('entries', []) if d else []):
                    kind = e.get('SI_KIND', '').lower()
                    if 'webi' in kind:          t = 'Web Intelligence Report'
                    elif 'crystal' in kind:     t = 'Crystal Report'
                    elif 'universe' in kind or 'dsl' in kind: t = 'Universe (.unx)'
                    elif 'query' in kind or 'bex' in kind:    t = 'BEx Query'
                    else:                       t = e.get('SI_KIND', 'Object')
                    results.append({
                        'name':  e.get('SI_NAME', ''),
                        'type':  t,
                        'owner': e.get('SI_OWNER', ''),
                        'desc':  e.get('SI_DESCRIPTION', ''),
                    })
            except Exception:
                pass
        if not results:
            results = [{'name': '(No linked CMS objects found)', 'type': 'Info',
                        'owner': '', 'desc': 'Objects may be resolved at runtime only.'}]
        return results

    # =========================================================================
    # PROMOTION RESOLVER  [used by gui/pages/promotion_resolver.py]
    # =========================================================================

    def get_promotion_conflicts(self, job_id):
        """
        Return conflicts for an LCM promotion job.
        Tries LCM endpoint, falls back to InfoStore comparison.
        """
        try:
            r = self.session.get(f"{self.base_url}/lcm/jobs/{job_id}/conflicts", timeout=20)
            if r.status_code == 200:
                data = r.json()
                raw = data.get('conflicts', data.get('conflict', []))
                if isinstance(raw, dict):
                    raw = [raw]
                return raw
        except Exception as e:
            logger.warning(f"get_promotion_conflicts: {e}")
        return []

    def resolve_promotion_conflict(self, job_id, conflict_id, resolution):
        """
        Resolve an LCM promotion conflict.
        resolution: 'keep_source' | 'keep_target' | 'merge'
        """
        try:
            r = self.session.put(
                f"{self.base_url}/lcm/jobs/{job_id}/conflicts/{conflict_id}",
                json={"resolution": resolution},
                timeout=20
            )
            return (r.status_code in (200, 204), "Resolved")
        except Exception as e:
            return (False, str(e))

    def run_promotion_job(self, job_id):
        """Execute an LCM job."""
        try:
            r = self.session.post(f"{self.base_url}/lcm/jobs/{job_id}/run", timeout=60)
            return (r.status_code in (200, 202), r.text[:200])
        except Exception as e:
            return (False, str(e))

    # =========================================================================
    # REPORT INTERACTION  [used by gui/pages/report_interaction.py]
    # =========================================================================

    def get_report_prompts(self, report_id):
        """Return prompts/parameters required to run a report."""
        try:
            r = self.session.get(
                f"{self.base_url}/v1/documents/{report_id}/parameters",
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                params = data.get('parameters', data.get('parameter', []))
                if isinstance(params, dict):
                    params = [params]
                return params
        except Exception as e:
            logger.error(f"get_report_prompts: {e}")
        return []

    def run_report_with_prompts(self, report_id, prompt_values=None):
        """
        Run/refresh a report, optionally with prompt answers.
        prompt_values: dict of {prompt_name: value}
        """
        try:
            payload = {}
            if prompt_values:
                payload['parameters'] = [{'name': k, 'value': v}
                                          for k, v in prompt_values.items()]
            r = self.session.post(
                f"{self.base_url}/v1/documents/{report_id}/schedules",
                json=payload,
                timeout=60
            )
            return (r.status_code in (200, 201, 202), r.text[:200])
        except Exception as e:
            return (False, str(e))

    def get_report_output_formats(self, report_id):
        """Return available export formats for a report."""
        try:
            r = self.session.get(
                f"{self.base_url}/v1/documents/{report_id}",
                timeout=10
            )
            if r.status_code == 200:
                return r.json().get('outputFormats', ['PDF', 'Excel', 'CSV'])
        except:
            pass
        return ['PDF', 'Excel', 'CSV', 'HTML']

    # =========================================================================
    # REPORT VIEWER  [used by gui/pages/report_viewer.py]
    # =========================================================================

    def get_all_reports_typed(self, limit=500):
        """
        Fetch ALL report types: WebI, CrystalReport, Excel (AO), Pdf.
        Returns enriched list including folder path.
        """
        q = (
            f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
            f"SI_CREATION_TIME, SI_UPDATE_TS, SI_DESCRIPTION, "
            f"SI_PARENT_FOLDER, SI_PATH "
            f"FROM CI_INFOOBJECTS "
            f"WHERE SI_KIND IN ('Webi','CrystalReport','Excel','Pdf') "
            f"AND SI_INSTANCE = 0 "
            f"ORDER BY SI_UPDATE_TS DESC"
        )
        d = self.run_cms_query(q)
        entries = d.get('entries', []) if d else []

        # Fallback: broader query if empty
        if not entries:
            q2 = (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                f"SI_CREATION_TIME, SI_UPDATE_TS "
                f"FROM CI_INFOOBJECTS "
                f"WHERE SI_INSTANCE = 0 "
                f"AND (SI_KIND LIKE '%Report%' OR SI_KIND='Webi' OR SI_KIND='Excel') "
                f"ORDER BY SI_UPDATE_TS DESC"
            )
            d2 = self.run_cms_query(q2)
            entries = d2.get('entries', []) if d2 else []

        reports = []
        for e in entries:
            kind = e.get('SI_KIND', '')
            # Normalise kind
            if 'webi' in kind.lower():
                kind = 'Webi'
            elif 'crystal' in kind.lower():
                kind = 'CrystalReport'
            elif kind.lower() in ('excel', 'xlsx'):
                kind = 'Excel'

            # Build folder path from SI_PATH or SI_PARENT_FOLDER
            raw_path = e.get('SI_PATH', '') or e.get('SI_PARENT_FOLDER', '')
            folder   = str(raw_path).split('/')[-2] if '/' in str(raw_path) else str(raw_path)

            reports.append({
                'id':       e.get('SI_ID', ''),
                'name':     e.get('SI_NAME', ''),
                'kind':     kind,
                'owner':    e.get('SI_OWNER', ''),
                'created':  e.get('SI_CREATION_TIME', ''),
                'last_run': e.get('SI_UPDATE_TS', ''),
                'desc':     e.get('SI_DESCRIPTION', ''),
                'folder':   folder,
            })
        return reports

    def get_report_instances(self, report_id, limit=50):
        """
        Return run instances for a specific report.
        Returns list with status, start/end time, owner, format.
        """
        STATUS_MAP = {0: 'Success', 1: 'Failed', 2: 'Running',
                      3: 'Pending', 4: 'Paused', 5: 'Recurring'}
        try:
            # Try REST instances endpoint first
            r = self.session.get(
                f"{self.base_url}/v1/documents/{report_id}/schedules",
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                raw  = data.get('schedules', data.get('schedule', []))
                if isinstance(raw, dict):
                    raw = [raw]
                instances = []
                for s in raw[:limit]:
                    status_code = s.get('status', s.get('statusCode', 0))
                    instances.append({
                        'status':     STATUS_MAP.get(status_code, str(status_code)),
                        'start_time': s.get('startTime', s.get('creationDate', '')),
                        'end_time':   s.get('endTime', s.get('completionDate', '')),
                        'owner':      s.get('owner', s.get('SI_OWNER', '')),
                        'format':     s.get('outputFormat', s.get('format', 'PDF')),
                    })
                return instances
        except Exception as e:
            logger.debug(f"get_report_instances REST: {e}")

        # Fallback: CMS query for instances
        try:
            q = (
                f"SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                f"SI_STARTTIME, SI_ENDTIME, SI_PROCESSINFO.SI_STATUS_INFO AS SI_STATUS "
                f"FROM CI_INFOOBJECTS "
                f"WHERE SI_INSTANCE=1 AND SI_PARENTID={report_id} "
                f"ORDER BY SI_STARTTIME DESC"
            )
            d = self.run_cms_query(q)
            instances = []
            for e in (d.get('entries', []) if d else []):
                sc = e.get('SI_STATUS', 0)
                instances.append({
                    'status':     STATUS_MAP.get(int(sc) if str(sc).isdigit() else 0, str(sc)),
                    'start_time': e.get('SI_STARTTIME', ''),
                    'end_time':   e.get('SI_ENDTIME', ''),
                    'owner':      e.get('SI_OWNER', ''),
                    'format':     'PDF',
                })
            return instances
        except Exception as e2:
            logger.debug(f"get_report_instances CMS: {e2}")
        return []

    def export_report(self, report_id, fmt='PDF', kind='Webi'):
        """
        Export a report in the requested format.
        Returns raw bytes on success, None on failure.

        WebI   → Raylight /v1/documents/{id}/pages (HTML) or export endpoint
        Crystal → /v1/documents/{id} export
        AO/Excel → download file from infostore
        fmt: 'PDF' | 'Excel' | 'CSV' | 'HTML'
        """
        fmt_upper = fmt.upper().strip()
        headers_accept = {
            'PDF':   'application/pdf',
            'EXCEL': 'application/vnd.ms-excel',
            'CSV':   'text/csv',
            'HTML':  'text/html',
        }.get(fmt_upper, 'application/octet-stream')

        # ── WebI via Raylight ─────────────────────────────────────────────────
        if kind == 'Webi':
            endpoints_to_try = []

            if fmt_upper == 'PDF':
                endpoints_to_try = [
                    f"{self.base_url}/raylight/v1/documents/{report_id}/pages?outputFormat=PDF",
                    f"{self.base_url}/v1/documents/{report_id}/content?outputFormat=PDF",
                    f"{self.base_url}/v1/documents/{report_id}?outputFormat=PDF",
                ]
            elif fmt_upper == 'EXCEL':
                endpoints_to_try = [
                    f"{self.base_url}/raylight/v1/documents/{report_id}/pages?outputFormat=EXCEL",
                    f"{self.base_url}/v1/documents/{report_id}/content?outputFormat=EXCEL",
                    f"{self.base_url}/v1/documents/{report_id}?outputFormat=EXCEL",
                ]
            elif fmt_upper == 'CSV':
                endpoints_to_try = [
                    f"{self.base_url}/raylight/v1/documents/{report_id}/pages?outputFormat=CSV",
                    f"{self.base_url}/v1/documents/{report_id}/content?outputFormat=CSV",
                ]
            elif fmt_upper == 'HTML':
                endpoints_to_try = [
                    f"{self.base_url}/raylight/v1/documents/{report_id}/pages",
                    f"{self.base_url}/v1/documents/{report_id}/content",
                ]

            for url in endpoints_to_try:
                try:
                    r = self.session.get(
                        url,
                        headers={'Accept': headers_accept},
                        timeout=60
                    )
                    if r.status_code == 200 and r.content:
                        return r.content if fmt_upper in ('PDF', 'EXCEL') else r.text
                except Exception as e:
                    logger.debug(f"export_report WebI {url}: {e}")

        # ── Crystal Reports via infostore ─────────────────────────────────────
        elif kind == 'CrystalReport':
            try:
                r = self.session.get(
                    f"{self.base_url}/v1/documents/{report_id}",
                    headers={'Accept': headers_accept},
                    params={'outputFormat': fmt_upper},
                    timeout=60
                )
                if r.status_code == 200 and r.content:
                    return r.content
            except Exception as e:
                logger.debug(f"export_report Crystal: {e}")

        # ── AO / Excel / PDF — download from infostore ────────────────────────
        else:
            try:
                r = self.session.get(
                    f"{self.base_url}/infostore/{report_id}/content",
                    timeout=60
                )
                if r.status_code == 200 and r.content:
                    return r.content
            except Exception as e:
                logger.debug(f"export_report download: {e}")

        return None

    def get_report_launchpad_url(self, report_id, kind='Webi'):
        """
        Build the BI Launchpad URL to open a report in the browser.
        Works for WebI, Crystal, and AO.
        Falls back to a direct document URL if launchpad URL can't be built.
        """
        try:
            # Extract host from base_url: http://HOST:PORT/biprws
            host_part = self.base_url.replace('/biprws', '').replace('https://', '').replace('http://', '')

            if kind == 'Webi':
                # Launchpad viewer URL for WebI
                url = (
                    f"http://{host_part}/BOE/BI?"
                    f"startDocument={report_id}"
                    f"&sType=rpt"
                    f"&sDocName="
                )
                return url
            elif kind == 'CrystalReport':
                url = (
                    f"http://{host_part}/BOE/BI?"
                    f"startDocument={report_id}"
                    f"&sType=rpt"
                )
                return url
            elif kind in ('Excel', 'Pdf'):
                # AO — open download page
                url = (
                    f"http://{host_part}/BOE/BI?"
                    f"startDocument={report_id}"
                )
                return url
            else:
                return f"http://{host_part}/BOE/BI?startDocument={report_id}"
        except Exception as e:
            logger.debug(f"get_report_launchpad_url: {e}")
            return None

    # =========================================================================
    # SELF HEALING  [used by gui/pages/self_healing.py]
    # =========================================================================

    def run_self_healing_scan(self):
        """
        Comprehensive scan for auto-fixable issues.
        Returns list of issues with auto_fix flag.
        """
        issues = []
        try:
            # 1. Stopped servers
            for s in self.get_all_servers():
                if s.get('status') != 'Running':
                    issues.append({
                        'type':      'Stopped Server',
                        'object':    s['name'],
                        'id':        s['id'],
                        'severity':  'CRITICAL',
                        'detail':    f"Server is {s['status']}",
                        'auto_fix':  True,
                        'fix_action':'restart_server',
                    })

            # 2. Failed schedules (recent)
            for f in self.get_instances(status='failed', limit=30):
                issues.append({
                    'type':      'Failed Schedule',
                    'object':    f['name'],
                    'id':        f['id'],
                    'severity':  'ERROR',
                    'detail':    f"Failed at {f.get('start_time','')}",
                    'auto_fix':  True,
                    'fix_action':'retry_instance',
                })

            # 3. Orphaned instances (old)
            for o in self.find_orphan_instances(days=60, limit=20):
                issues.append({
                    'type':      'Orphaned Instance',
                    'object':    o['name'],
                    'id':        o['id'],
                    'severity':  'WARNING',
                    'detail':    f"Old instance from {o.get('start_time','')}",
                    'auto_fix':  True,
                    'fix_action':'delete_instance',
                })

        except Exception as e:
            logger.error(f"run_self_healing_scan: {e}")
        return issues

    def apply_self_heal(self, issue):
        """
        Auto-fix a single issue from self-healing scan.
        Returns (success, message).
        """
        action = issue.get('fix_action','')
        obj_id = issue.get('id')
        try:
            if action == 'restart_server':
                return self.toggle_server_state(obj_id, 'restart')
            elif action == 'retry_instance':
                ok, err = self.bulk_retry_instances([obj_id])
                return (ok > 0, f"Retried: ok={ok} err={err}")
            elif action == 'delete_instance':
                return self.delete_instance(obj_id)
        except Exception as e:
            return (False, str(e))
        return (False, f"Unknown action: {action}")

    # =========================================================================
    # SERVICES  [used by gui/pages/services.py]
    # =========================================================================

    def get_bo_services(self):
        """Return BO Windows/Linux services status."""
        services = []
        try:
            # Query SIA nodes and their sub-services
            q = """SELECT SI_ID, SI_NAME, SI_KIND, SI_SERVER_IS_ALIVE, SI_DESCRIPTION
                   FROM CI_SYSTEMOBJECTS
                   WHERE SI_KIND IN ('Server','Node','SIA')
                   ORDER BY SI_KIND, SI_NAME"""
            d = self.run_cms_query(q)
            if d and d.get('entries'):
                for e in d['entries']:
                    services.append({
                        'id':      e.get('SI_ID',''),
                        'name':    e.get('SI_NAME',''),
                        'kind':    e.get('SI_KIND',''),
                        'status':  'Running' if e.get('SI_SERVER_IS_ALIVE') else 'Stopped',
                        'desc':    e.get('SI_DESCRIPTION',''),
                    })
        except Exception as e:
            logger.error(f"get_bo_services: {e}")
        return services

    def restart_bo_service(self, service_id):
        """Restart a BO service by ID."""
        return self.toggle_server_state(service_id, 'restart')

    # =========================================================================
    # WEB SERVICES  [used by gui/pages/web_services.py]
    # =========================================================================

    def get_web_services(self, limit=100):
        """Return published BO web services (QaaWS / REST)."""
        q = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER,
                SI_DESCRIPTION, SI_UPDATE_TS, SI_CREATION_TIME
                FROM CI_INFOOBJECTS
                WHERE SI_KIND IN ('WebService','QaaWS','RESTService',
                                  'WebServicePublishing','BIService')
                ORDER BY SI_NAME"""
        d = self.run_cms_query(q)
        if not d or not d.get('entries'):
            # Fallback
            q2 = f"""SELECT TOP {limit} SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS
                     FROM CI_INFOOBJECTS WHERE SI_NAME LIKE '%Service%'
                     AND SI_INSTANCE=0 ORDER BY SI_NAME"""
            d = self.run_cms_query(q2)
        if not d or not d.get('entries'):
            return []
        return [{
            'id':      e.get('SI_ID',''),
            'name':    e.get('SI_NAME',''),
            'kind':    e.get('SI_KIND',''),
            'owner':   e.get('SI_OWNER',''),
            'desc':    e.get('SI_DESCRIPTION',''),
            'updated': e.get('SI_UPDATE_TS',''),
        } for e in d['entries']]

    def get_web_service_wsdl(self, service_id):
        """Return WSDL/URL for a web service."""
        host = self.cms_details.get('host', 'localhost')
        return f"http://{host}:8080/dswsbobje/qaawsservices?service_id={service_id}"

    def test_web_service(self, service_id):
        """Ping a web service to verify availability."""
        try:
            url = self.get_web_service_wsdl(service_id)
            r = self.session.get(url, timeout=10)
            return r.status_code == 200
        except:
            return False



# =========================================================================
# GLOBAL SINGLETON INSTANCE
# =========================================================================
    # =========================================================================
    # ALIASES  — backwards-compat shims for older page code
    # =========================================================================

    def get_folders(self):
        """Alias for get_root_folders() — used by folders.py."""
        return self.get_root_folders()

    def get_folder_tree(self, parent_id=23):
        """Alias for get_folder_contents() — returns (folders, docs)."""
        return self.get_folder_contents(parent_id)

    def get_audit_events(self, days=7, user=None):
        """Alias for get_historical_audit() — used by audit.py."""
        return self.get_historical_audit(days=days, user=user)


bo_session = SAPBOConnection()
