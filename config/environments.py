# config/environments.py
ENVIRONMENTS = {
    'development': {
        'cms_host': 'dev-cms.company.com',
        'cms_port': '6405',
        'audit_db': 'DEV_BI4_Audit',
        'log_level': 'DEBUG'
    },
    'production': {
        'cms_host': 'prod-cms.company.com',
        'cms_port': '6405',
        'audit_db': 'PROD_BI4_Audit',
        'log_level': 'INFO'
    }
}
