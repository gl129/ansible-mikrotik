def selectkey( src_dict, key_list ):
    """
    Select keys from dict to return.
    Input - src_dict: the source dict, key_list: list of key names, may be single value
    Return - dict with selected keys from src_dict, no errors if key not exists
    """
    ret = {}
    for key in (key_list if isinstance(key_list,list) else [key_list]):
        if key in src_dict:
            ret[key] = src_dict[key]
    return ret

def rejectkey( src_dict, key_list ):
    """
    Reject keys from dict to return.
    Input - src_dict: the source dict, key_list: list of key names, may by single value
    Return - dict without rejected keys from src_dict, no errors if key not exists
    """
    ret = {}
    for key in src_dict:
        if key not in (key_list if isinstance(key_list,list) else [key_list]):
            ret[key] = src_dict[key]
    return ret

def rejectkeyifempty( src_dict, key_list ):
    """
    Reject keys from dict to return if its value is empty, none, etc
    Input - src_dict: the source dict, key_list: list of key names.
    Return - dict without rejected keys from src_dict, no errors if key not exists
    """
    ret = {}
    for key in src_dict:
        if ( src_dict[key] or key not in (key_list if isinstance(key_list,list) else [key_list]) ):
            ret[key] = src_dict[key]
    return ret


class FilterModule( object ):
    def filters( self ):
        return { 'selectkey': selectkey, 'rejectkey': rejectkey, 'rejectkeyifempty': rejectkeyifempty }
