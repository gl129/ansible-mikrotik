def split_filter( src, split_by ):
    """
    Ordinary split filter (is absent in Ansible 2.10)
    Input - strings, same an python split parameters
    Return - list, same as python split returns
    """
    return src.split(split_by)

class FilterModule( object ):
    def filters( self ):
        return { 'split': split_filter }
