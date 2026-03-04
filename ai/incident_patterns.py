import json
import os

def match_pattern(context):
    """OFFLINE ENGINE: Scans logs for keywords defined in JSON."""
    kb_path = "data/keywords.json"
    if not os.path.exists(kb_path): return None
    
    try:
        with open(kb_path, 'r') as f:
            kb = json.load(f)
            
        # Combine all log content into one search string
        search_text = str(context.get('logs', {})) + str(context.get('env', {}))
        
        for p in kb['incident_patterns']:
            if p['key'] in search_text:
                return {
                    "title": p['title'],
                    "cause": p['cause'],
                    "evidence": f"Found keyword '{p['key']}' in system logs.",
                    "risk_level": p['severity'],
                    "owner": p['owner'],
                    "fix": [] # No solutions in Strict Offline Mode
                }
    except: pass
    return None