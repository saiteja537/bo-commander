import subprocess
import json

class JavaSDKClient:
    def __init__(self):
        self.service_jar = "services/wi-sdk-service.jar"
    
    def create_webi_report(self, name, universe_id, objects, query):
        """Call Java SDK service to create WebI report"""
        payload = json.dumps({
            'name': name,
            'universeId': universe_id,
            'objects': objects,
            'query': query
        })
        
        result = subprocess.run(
            ['java', '-jar', self.service_jar, 'create-report', payload],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return json.loads(result.stdout)