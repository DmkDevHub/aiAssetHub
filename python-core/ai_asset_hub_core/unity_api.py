"""Fixed Unity command surface. Host capabilities never include target registration."""
from .libraries import LibraryError

HOST_METHODS={
    'list_unity_targets':'unity.targets',
    'preview_unity_import':'unity.preview_import',
    'preview_unity_placement':'unity.preview_place',
    'import_assets_to_unity':'unity.import',
    'place_assets_in_unity':'unity.place',
    'get_operation_status':'unity.status',
}


def dispatch(database,method,params):
    from .unity_targets import UnityTargets
    from .unity_operations import UnityOperations
    targets=UnityTargets(database);operations=UnityOperations(database)
    actions={'unity.targets':targets.list,'unity.target.save':targets.save,'unity.target.remove':targets.remove,
        'unity.preview_import':operations.preview_import,'unity.preview_place':operations.preview_place,
        'unity.import':operations.execute_import,'unity.place':operations.execute_place,'unity.status':operations.status}
    if method not in actions:raise LibraryError('INVALID_PARAMS')
    return actions[method](params)
