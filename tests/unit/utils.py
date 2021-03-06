from dusty.schemas.base_schema_class import DustySchema
from dusty.schemas.app_schema import app_schema
from dusty.schemas.lib_schema import lib_schema
from dusty.schemas.bundle_schema import bundle_schema

def get_app_dusty_schema(doc, name=None):
    if 'image' not in doc and 'build' not in doc:
        doc['image'] = ''
    if 'repo' not in doc:
        doc['repo'] = ''
    if 'mount' not in doc:
        doc['mount'] = ''
    return DustySchema(app_schema, doc, name, 'apps')

def get_lib_dusty_schema(doc, name=None):
    if 'mount' not in doc:
        doc['mount'] = ''
    if 'repo' not in doc:
        doc['repo'] = ''
    return DustySchema(lib_schema, doc, name, 'libs')

def get_bundle_dusty_schema(doc):
    return DustySchema(bundle_schema, doc)

def apply_required_keys(specs):
    for k, v in specs.get('apps', {}).iteritems():
        specs['apps'][k] = get_app_dusty_schema(v, k)
    for k, v in specs.get('libs', {}).iteritems():
        specs['libs'][k] = get_lib_dusty_schema(v, k)
