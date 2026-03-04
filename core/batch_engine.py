class BatchOperationEngine:
    """
    Optimized batch processor for bulk operations
    Uses threading and connection pooling
    """
    
    def __init__(self, max_workers=10):
        self.max_workers = max_workers
        self.session_pool = [bo_session.session for _ in range(max_workers)]
        self.results = []
    
    def batch_move_objects(self, object_ids, target_folder_id, progress_callback=None):
        """
        Move multiple objects efficiently
        Current implementation: Sequential (slow)
        New implementation: Parallel with progress tracking
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        total = len(object_ids)
        completed = 0
        
        def move_single(obj_id):
            try:
                r = bo_session.session.put(
                    f"{bo_session.base_url}/v1/infostore/{obj_id}",
                    json={"parentId": target_folder_id},
                    timeout=10
                )
                return {'id': obj_id, 'status': r.status_code == 200}
            except Exception as e:
                return {'id': obj_id, 'status': False, 'error': str(e)}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(move_single, oid): oid for oid in object_ids}
            
            for future in as_completed(futures):
                result = future.result()
                self.results.append(result)
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total)
        
        return self.results
    
    def batch_update_rights(self, object_ids, principal_id, rights_type, grant=True):
        """
        Bulk security updates
        Essential for mass permission changes
        """
        from concurrent.futures import ThreadPoolExecutor
        
        def update_single_right(obj_id):
            try:
                endpoint = f"{bo_session.base_url}/v1/objects/{obj_id}/rights"
                
                # Get current rights
                current = bo_session.session.get(endpoint, timeout=5).json()
                
                # Modify rights
                rights_payload = {
                    'right': current.get('right', [])
                }
                
                # Add/Remove principal rights
                found = False
                for right in rights_payload['right']:
                    if right['principalID'] == principal_id:
                        right[rights_type] = grant
                        found = True
                        break
                
                if not found and grant:
                    rights_payload['right'].append({
                        'principalID': principal_id,
                        rights_type: True
                    })
                
                # Apply changes
                r = bo_session.session.put(endpoint, json=rights_payload, timeout=10)
                return {'id': obj_id, 'success': r.status_code == 200}
            
            except Exception as e:
                return {'id': obj_id, 'success': False, 'error': str(e)}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(update_single_right, object_ids))
        
        return results
    
    def batch_refresh_reports(self, report_ids, wait_for_completion=False):
        """
        Trigger multiple report refreshes
        Useful for nightly refresh operations
        """
        results = []
        
        for rid in report_ids:
            try:
                r = bo_session.session.post(
                    f"{bo_session.base_url}/v1/documents/{rid}/refresh",
                    timeout=5
                )
                
                instance_id = r.headers.get('Location', '').split('/')[-1]
                
                results.append({
                    'report_id': rid,
                    'status': 'triggered' if r.status_code == 202 else 'failed',
                    'instance_id': instance_id
                })
                
            except Exception as e:
                results.append({'report_id': rid, 'status': 'error', 'error': str(e)})
        
        if wait_for_completion:
            self._monitor_instances([r['instance_id'] for r in results if 'instance_id' in r])
        
        return results