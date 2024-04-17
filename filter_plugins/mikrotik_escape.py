def mikrotik_escape( str_to_escape, force=False ):
    """
    Escape string to use in Mikrotik script
    - all type bracketed and statements passed as-is
    - booleans and boolean-like strings passed using Mikrotik boolean representation yes/no
    - lists are translated to [:toarray ...]
    - others treated as string and passed doublequoted and escaped
    - if force parameter is true ANY given string is treated as string and passed doublequoted and escaped
    """
    if str_to_escape is None or len(str(str_to_escape)) == 0:
        return '""'
    if not force:
        if isinstance(str_to_escape,list):
            return f'[:toarray "{",".join(str_to_escape)}"]'
        elif isinstance(str_to_escape,bool) and str_to_escape or str_to_escape in ['yes','true','on']:
            return 'yes'
        elif isinstance(str_to_escape,bool) and not str_to_escape or str_to_escape in ['no','false','off']:
            return 'no'
        elif ( isinstance(str_to_escape,str) and str_to_escape[0] in ['(','[','{','"'] ):
            return str_to_escape
    return '"'+str(str_to_escape).replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('\n','\\r\\n')+'"'


class FilterModule( object ):
    def filters( self ):
        return { 'mikrotik_escape': mikrotik_escape }
